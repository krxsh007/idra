from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_responder
from app.db.models.runs import AgentRun
from app.db.models.users import User
from app.db.session import get_db
from app.llm.client import get_llm_client
from app.orchestration.engine import orchestration_engine
from app.schemas.runs import RunDetailResponse, RunListResponse

router = APIRouter(tags=["Orchestration Runs"])


@router.post(
    "/events/{event_id}/runs",
    response_model=RunDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger multi-agent orchestration pipeline for an event",
)
async def trigger_event_run(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    llm = get_llm_client()
    try:
        run_record = await orchestration_engine.run_pipeline(
            event_id=event_id,
            triggered_by=current_user.id,
            db=db,
            llm=llm,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    # Re-fetch with loaded outputs
    stmt = (
        select(AgentRun)
        .options(selectinload(AgentRun.outputs))
        .where(AgentRun.id == run_record.id)
    )
    res = await db.execute(stmt)
    full_run = res.scalar_one()
    return full_run


@router.get(
    "/events/{event_id}/runs",
    response_model=RunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all orchestration runs for a disaster event",
)
async def list_event_runs(
    event_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    count_stmt = select(func.count(AgentRun.id)).where(AgentRun.event_id == event_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AgentRun)
        .options(selectinload(AgentRun.outputs))
        .where(AgentRun.event_id == event_id)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/runs/{run_id}",
    response_model=RunDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed results and agent outputs for a specific run",
)
async def get_run_detail(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = (
        select(AgentRun)
        .options(selectinload(AgentRun.outputs))
        .where(AgentRun.id == run_id)
    )
    res = await db.execute(stmt)
    run_record = res.scalar_one_or_none()
    if not run_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )
    return run_record
