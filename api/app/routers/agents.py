from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assessment import DisasterAssessmentAgent
from app.agents.base import AgentFailure, RunContext
from app.core.config import settings
from app.core.security import require_responder
from app.db.models.enums import AgentName
from app.db.models.users import User
from app.db.session import get_db
from app.llm.client import get_llm_client
from app.schemas.agents.assessment import AssessmentInput, AssessmentOutput

router = APIRouter(prefix="/agents", tags=["Agents"])

assessment_agent = DisasterAssessmentAgent()


@router.post(
    "/assessment",
    response_model=AssessmentOutput,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Disaster Assessment Agent directly",
)
async def run_assessment_endpoint(
    input_data: AssessmentInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    """Execute Disaster Assessment Agent directly on provided disaster telemetry.

    Available to responders and admins for immediate evaluation and verification.
    """
    llm = get_llm_client()
    ctx = RunContext(
        event_id=input_data.event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        db=db,
        llm=llm,
        timeout_s=float(settings.AGENT_TIMEOUT_ASSESSMENT_S),
    )

    result = await assessment_agent.run(ctx, input_data)
    if isinstance(result, AgentFailure):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        if result.code == "AGENT_TIMEOUT":
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        elif result.code == "INSUFFICIENT_EVIDENCE":
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.code,
                "message": result.message,
                "details": result.details,
            },
        )

    return result
