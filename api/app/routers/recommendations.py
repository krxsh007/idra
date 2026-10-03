from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException, ErrorCode
from app.core.security import require_admin, require_responder
from app.db.models.audit import AuditLog
from app.db.models.base import utc_now
from app.db.models.enums import VerificationStatus
from app.db.models.runs import Recommendation
from app.db.models.users import User
from app.db.session import get_db
from app.schemas.recommendations import (
    RecommendationListResponse,
    RecommendationResponse,
    VerifyRecommendationRequest,
)

router = APIRouter(tags=["Recommendations"])


@router.get(
    "/recommendations",
    response_model=RecommendationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List prioritized recommendations with verification status and citations",
)
async def list_recommendations(
    event_id: uuid.UUID | None = Query(None, description="Filter by disaster event ID"),
    verification_status: VerificationStatus | None = Query(
        None, description="Filter by verification status"
    ),
    current_user: User = Depends(require_responder),
    db: AsyncSession = Depends(get_db),
) -> RecommendationListResponse:
    stmt = (
        select(Recommendation)
        .options(selectinload(Recommendation.citations))
        .order_by(Recommendation.priority.asc())
    )

    if event_id is not None:
        stmt = stmt.where(Recommendation.event_id == event_id)
    if verification_status is not None:
        stmt = stmt.where(Recommendation.verification_status == verification_status)

    res = await db.execute(stmt)
    recs = res.scalars().all()
    items = [RecommendationResponse.model_validate(r) for r in recs]
    return RecommendationListResponse(items=items, total=len(items))


@router.post(
    "/recommendations/{rec_id}/verify",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Human-in-the-loop verification gate (Approve, Override, or Reject)",
)
async def verify_recommendation(
    rec_id: uuid.UUID,
    req: VerifyRecommendationRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Recommendation:
    # 1. Enforce allowed actions
    allowed_actions = {
        VerificationStatus.VERIFIED,
        VerificationStatus.OVERRIDDEN,
        VerificationStatus.REJECTED,
    }
    if req.action not in allowed_actions:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Action must be one of: {', '.join(a.value for a in allowed_actions)}",
        )

    # 2. Require note for Override and Reject
    if req.action in (VerificationStatus.OVERRIDDEN, VerificationStatus.REJECTED):
        if not req.note or not req.note.strip():
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ErrorCode.VALIDATION_ERROR,
                message="Note is required when overriding or rejecting a recommendation.",
            )

    # 3. Fetch recommendation with citations
    stmt = (
        select(Recommendation)
        .options(selectinload(Recommendation.citations))
        .where(Recommendation.id == rec_id)
    )
    res = await db.execute(stmt)
    rec = res.scalar_one_or_none()

    if rec is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Recommendation {rec_id} not found.",
        )

    # 4. Prevent duplicate verification (ALREADY_VERIFIED conflict)
    if rec.verification_status != VerificationStatus.PENDING:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.ALREADY_VERIFIED,
            message=f"Recommendation {rec_id} has already been verified.",
        )

    # 5. Capture before state
    before_state: dict[str, Any] = {
        "verification_status": rec.verification_status.value,
        "verified_by": str(rec.verified_by) if rec.verified_by else None,
        "verified_at": rec.verified_at.isoformat() if rec.verified_at else None,
        "override_note": rec.override_note,
    }

    # 6. Apply state transition
    rec.verification_status = req.action
    rec.override_note = req.note.strip() if req.note else None
    rec.verified_by = current_user.id
    rec.verified_at = utc_now()

    after_state: dict[str, Any] = {
        "verification_status": rec.verification_status.value,
        "verified_by": str(rec.verified_by),
        "verified_at": rec.verified_at.isoformat() if rec.verified_at else None,
        "override_note": rec.override_note,
    }

    # 7. Write immutable audit log
    audit_entry = AuditLog(
        actor_id=current_user.id,
        action=req.action.value,
        entity_type="recommendation",
        entity_id=str(rec.id),
        before_state=before_state,
        after_state=after_state,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(rec)
    return rec
