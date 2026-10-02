from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assessment import DisasterAssessmentAgent
from app.agents.base import AgentFailure, RunContext
from app.agents.facilities import FacilityRecommendationAgent
from app.agents.resources import ResourceAllocationAgent
from app.agents.routing import RoutingAgent
from app.core.config import settings
from app.core.security import require_responder
from app.db.models.enums import AgentName
from app.db.models.users import User
from app.db.session import get_db
from app.llm.client import get_llm_client
from app.schemas.agents.assessment import AssessmentInput, AssessmentOutput
from app.schemas.agents.facilities import (
    FacilityRecommendationInput,
    FacilityRecommendationOutput,
)
from app.schemas.agents.resources import (
    ResourceAllocationInput,
    ResourceAllocationOutput,
)
from app.schemas.agents.routing import (
    RoutingInput,
    RoutingOutput,
)

router = APIRouter(prefix="/agents", tags=["Agents"])

assessment_agent = DisasterAssessmentAgent()
facility_agent = FacilityRecommendationAgent()
resource_agent = ResourceAllocationAgent()
routing_agent = RoutingAgent()


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


@router.post(
    "/facilities",
    response_model=FacilityRecommendationOutput,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Facility Recommendation Agent directly",
)
async def run_facilities_endpoint(
    input_data: FacilityRecommendationInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    llm = get_llm_client()
    ctx = RunContext(
        event_id=input_data.event.id,
        agent_name=AgentName.HOSPITAL_RECOMMENDATION,
        db=db,
        llm=llm,
        timeout_s=float(settings.AGENT_TIMEOUT_FACILITY_S),
    )

    result = await facility_agent.run(ctx, input_data)
    if isinstance(result, AgentFailure):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": result.code,
                "message": result.message,
                "details": result.details,
            },
        )

    return result


@router.post(
    "/resources",
    response_model=ResourceAllocationOutput,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Resource Allocation Agent directly",
)
async def run_resources_endpoint(
    input_data: ResourceAllocationInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    llm = get_llm_client()
    ctx = RunContext(
        event_id=input_data.event.id,
        agent_name=AgentName.RESOURCE_COORDINATION,
        db=db,
        llm=llm,
        timeout_s=float(settings.AGENT_TIMEOUT_RESOURCE_S),
    )

    result = await resource_agent.run(ctx, input_data)
    if isinstance(result, AgentFailure):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": result.code,
                "message": result.message,
                "details": result.details,
            },
        )

    return result


@router.post(
    "/routing",
    response_model=RoutingOutput,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Evacuation & Rescue Routing Agent directly",
)
async def run_routing_endpoint(
    input_data: RoutingInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    llm = get_llm_client()
    ctx = RunContext(
        event_id=input_data.event.id,
        agent_name=AgentName.EVACUATION,
        db=db,
        llm=llm,
        timeout_s=float(settings.AGENT_TIMEOUT_EVACUATION_S),
    )

    result = await routing_agent.run(ctx, input_data)
    if isinstance(result, AgentFailure):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": result.code,
                "message": result.message,
                "details": result.details,
            },
        )

    return result
