from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.assessment import DisasterAssessmentAgent
from app.agents.base import AgentFailure, RunContext
from app.agents.facilities import FacilityRecommendationAgent
from app.agents.resources import ResourceAllocationAgent
from app.agents.routing import RoutingAgent
from app.core.config import settings
from app.db.models.enums import AgentName, AgentStatus
from app.llm.client import LLMClient
from app.orchestration.state import AgentExecutionRecord, OrchestratorState
from app.schemas.agents.assessment import AssessmentInput
from app.schemas.agents.facilities import FacilityCandidate, FacilityRecommendationInput
from app.schemas.agents.resources import ResourceAllocationInput
from app.schemas.agents.routing import RoutingInput
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse
from app.schemas.reports import ReportResponse

logger = structlog.get_logger(__name__)

assessment_agent = DisasterAssessmentAgent()
facility_agent = FacilityRecommendationAgent()
resource_agent = ResourceAllocationAgent()
routing_agent = RoutingAgent()


def parse_state_into_assessment_input(state: OrchestratorState) -> AssessmentInput:
    e_dict = state["event_data"]
    event_resp = EventResponse(
        id=uuid.UUID(e_dict["id"]),
        name=e_dict["name"],
        disaster_type=e_dict["disaster_type"],
        status=e_dict["status"],
        epicenter=EpicenterPoint(lon=e_dict["epicenter"]["lon"], lat=e_dict["epicenter"]["lat"]),
        radius_m=e_dict["radius_m"],
        declared_at=e_dict["declared_at"],
        description=e_dict.get("description"),
        created_at=e_dict["created_at"],
    )

    reports = []
    for r in state.get("reports_data", []):
        reports.append(
            ReportResponse(
                id=uuid.UUID(r["id"]),
                event_id=uuid.UUID(r["event_id"]) if r.get("event_id") else None,
                source=r["source"],
                body=r["body"],
                location=EpicenterPoint(lon=r["location"]["lon"], lat=r["location"]["lat"]),
                casualties_reported=r.get("casualties_reported", False),
                people_affected=r.get("people_affected"),
                data_provenance=r["data_provenance"],
                reported_at=r["reported_at"],
                created_at=r["created_at"],
            )
        )

    hazards = []
    for h in state.get("hazards_data", []):
        hazards.append(
            HazardZoneResponse(
                id=uuid.UUID(h["id"]),
                event_id=uuid.UUID(h["event_id"]),
                label=h["label"],
                hazard_type=h["hazard_type"],
                severity=h["severity"],
                geometry=GeoJSONPolygon(type="Polygon", coordinates=h["geometry"]["coordinates"]),
                is_impassable=h.get("is_impassable", False),
                active_from=h["active_from"],
                created_at=h["created_at"],
            )
        )

    return AssessmentInput(
        event=event_resp,
        reports=reports,
        hazard_zones=hazards,
        weather_context=state.get("weather_data"),
    )


def create_orchestrator_graph(
    db: AsyncSession | None,
    llm: LLMClient,
) -> Any:
    workflow = StateGraph(OrchestratorState)

    async def assessment_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.DISASTER_ASSESSMENT,
            db=db,
            llm=llm,
            timeout_s=float(settings.AGENT_TIMEOUT_ASSESSMENT_S),
        )

        input_data = parse_state_into_assessment_input(state)
        result = await assessment_agent.run(ctx, input_data)
        latency_ms = int((time.perf_counter() - start) * 1000)

        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            record: AgentExecutionRecord = {
                "agent": AgentName.DISASTER_ASSESSMENT.value,
                "status": result.status,
                "payload": None,
                "latency_ms": latency_ms,
                "error_code": result.code,
                "error_message": result.message,
            }
            existing_outputs.append(record)
            return {
                "assessment_output": None,
                "assessment_status": result.status,
                "needs_human_review": True,
                "is_terminal": True,
                "outputs": existing_outputs,
            }

        record = {
            "agent": AgentName.DISASTER_ASSESSMENT.value,
            "status": AgentStatus.SUCCESS,
            "payload": result.model_dump(mode="json"),
            "latency_ms": latency_ms,
            "error_code": None,
            "error_message": None,
        }
        existing_outputs.append(record)

        needs_review = result.confidence < settings.ASSESSMENT_CONFIDENCE_FLOOR

        return {
            "assessment_output": result.model_dump(mode="json"),
            "assessment_status": AgentStatus.SUCCESS,
            "assessed_severity": result.severity,
            "needs_human_review": needs_review,
            "is_terminal": needs_review,
            "outputs": existing_outputs,
        }

    async def facilities_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.HOSPITAL_RECOMMENDATION,
            db=db,
            llm=llm,
            timeout_s=float(settings.AGENT_TIMEOUT_FACILITY_S),
        )

        assessment_in = parse_state_into_assessment_input(state)
        ass_out = state.get("assessment_output") or {}

        fac_input = FacilityRecommendationInput(
            event=assessment_in.event,
            assessment_summary=ass_out.get("affected_area_summary", "Disaster impact area"),
            severity=state.get("assessed_severity", assessment_in.event.disaster_type),  # type: ignore[arg-type]
            casualties_reported=ass_out.get("casualties_reported", False),
            estimated_people_affected=ass_out.get("estimated_people_affected", 0),
            epicenter=assessment_in.event.epicenter,
        )

        result = await facility_agent.run(ctx, fac_input)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.HOSPITAL_RECOMMENDATION.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "facilities_output": None,
                "facilities_status": result.status,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.HOSPITAL_RECOMMENDATION.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "facilities_output": result.model_dump(mode="json"),
            "facilities_status": AgentStatus.SUCCESS,
            "outputs": existing_outputs,
        }

    async def resources_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.RESOURCE_COORDINATION,
            db=db,
            llm=llm,
            timeout_s=float(settings.AGENT_TIMEOUT_RESOURCE_S),
        )

        assessment_in = parse_state_into_assessment_input(state)
        ass_out = state.get("assessment_output") or {}

        res_input = ResourceAllocationInput(
            event=assessment_in.event,
            severity=state.get("assessed_severity", assessment_in.event.disaster_type),  # type: ignore[arg-type]
            assessment_summary=ass_out.get("affected_area_summary", "Disaster impact area"),
            estimated_people_affected=ass_out.get("estimated_people_affected", 0),
            casualties_reported=ass_out.get("casualties_reported", False),
            reports=assessment_in.reports,
            hazard_zones=assessment_in.hazard_zones,
        )

        result = await resource_agent.run(ctx, res_input)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.RESOURCE_COORDINATION.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "resources_output": None,
                "resources_status": result.status,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.RESOURCE_COORDINATION.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "resources_output": result.model_dump(mode="json"),
            "resources_status": AgentStatus.SUCCESS,
            "outputs": existing_outputs,
        }

    async def routing_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.EVACUATION,
            db=db,
            llm=llm,
            timeout_s=float(settings.AGENT_TIMEOUT_EVACUATION_S),
        )

        assessment_in = parse_state_into_assessment_input(state)
        fac_out = state.get("facilities_output") or {}

        shelters = [
            FacilityCandidate.model_validate(s) for s in fac_out.get("recommended_shelters", [])
        ]
        hospitals = [
            FacilityCandidate.model_validate(h) for h in fac_out.get("recommended_hospitals", [])
        ]

        routing_input = RoutingInput(
            event=assessment_in.event,
            reports=assessment_in.reports,
            recommended_shelters=shelters,
            recommended_hospitals=hospitals,
            hazard_zones=assessment_in.hazard_zones,
        )

        result = await routing_agent.run(ctx, routing_input)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.EVACUATION.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "routing_output": None,
                "routing_status": result.status,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.EVACUATION.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "routing_output": result.model_dump(mode="json"),
            "routing_status": AgentStatus.SUCCESS,
            "outputs": existing_outputs,
        }

    def check_assessment_branch(state: OrchestratorState) -> str:
        if state.get("assessment_status") != AgentStatus.SUCCESS:
            return END
        if state.get("needs_human_review", False):
            return END
        return "facilities"

    workflow.add_node("assessment", assessment_node)
    workflow.add_node("facilities", facilities_node)
    workflow.add_node("resources", resources_node)
    workflow.add_node("routing", routing_node)

    workflow.set_entry_point("assessment")
    workflow.add_conditional_edges(
        "assessment",
        check_assessment_branch,
        {
            "facilities": "facilities",
            END: END,
        },
    )
    workflow.add_edge("facilities", "resources")
    workflow.add_edge("resources", "routing")
    workflow.add_edge("routing", END)

    return workflow.compile()
