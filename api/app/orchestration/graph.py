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
from app.agents.rescue_planning import RescuePlanningAgent
from app.agents.resources import ResourceAllocationAgent
from app.agents.routing import RoutingAgent
from app.db.models.enums import AgentName, AgentStatus, SeverityLevel
from app.llm.client import LLMClient
from app.orchestration.conflicts import ConflictResolver
from app.orchestration.selection import evaluate_agent_activation
from app.orchestration.state import OrchestratorState
from app.orchestration.synthesis import SynthesisAgent
from app.schemas.agents.assessment import AssessmentInput
from app.schemas.agents.facilities import FacilityCandidate, FacilityRecommendationInput
from app.schemas.agents.planning import PrioritizedZone, RescuePlanningInput
from app.schemas.agents.resources import ResourceAllocationInput
from app.schemas.agents.routing import RoutingInput
from app.schemas.agents.synthesis import SynthesisInput
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse
from app.schemas.reports import ReportResponse

logger = structlog.get_logger(__name__)

assessment_agent = DisasterAssessmentAgent()
planning_agent = RescuePlanningAgent()
facility_agent = FacilityRecommendationAgent()
resource_agent = ResourceAllocationAgent()
routing_agent = RoutingAgent()
conflict_resolver = ConflictResolver()
synthesis_agent = SynthesisAgent()


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

    # 1. Assessment Node
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
        )

        assessment_in = parse_state_into_assessment_input(state)
        result = await assessment_agent.run(ctx, assessment_in)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.DISASTER_ASSESSMENT.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "assessment_output": None,
                "assessment_status": result.status,
                "assessed_severity": None,
                "needs_human_review": True,
                "is_terminal": True,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.DISASTER_ASSESSMENT.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "assessment_output": result.model_dump(mode="json"),
            "assessment_status": AgentStatus.SUCCESS,
            "assessed_severity": result.severity,
            "needs_human_review": result.confidence < 0.5,
            "is_terminal": result.confidence < 0.5,
            "outputs": existing_outputs,
        }

    # 2. Rescue Planning Node
    async def planning_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        assessment_in = parse_state_into_assessment_input(state)
        as_out = state.get("assessment_output") or {}
        sev = state.get("assessed_severity") or SeverityLevel.MODERATE

        activation = evaluate_agent_activation(as_out)
        if not activation.get(AgentName.RESCUE_PLANNING, False):
            return {
                "planning_output": None,
                "planning_status": AgentStatus.SKIPPED,
            }

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.RESCUE_PLANNING,
            db=db,
            llm=llm,
        )

        planning_in = RescuePlanningInput(
            event=assessment_in.event,
            reports=assessment_in.reports,
            hazard_zones=assessment_in.hazard_zones,
            assessment_severity=sev,
            assessment_summary=as_out.get("affected_area_summary", ""),
        )

        result = await planning_agent.run(ctx, planning_in)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.RESCUE_PLANNING.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "planning_output": None,
                "planning_status": result.status,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.RESCUE_PLANNING.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "planning_output": result.model_dump(mode="json"),
            "planning_status": AgentStatus.SUCCESS,
            "outputs": existing_outputs,
        }

    # 3. Facilities Node
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
        )

        assessment_in = parse_state_into_assessment_input(state)
        as_out = state.get("assessment_output") or {}
        sev = state.get("assessed_severity") or SeverityLevel.MODERATE

        facility_in = FacilityRecommendationInput(
            event=assessment_in.event,
            assessment_summary=as_out.get("affected_area_summary", ""),
            severity=sev,
            casualties_reported=as_out.get("casualties_reported", False),
            estimated_people_affected=as_out.get("estimated_people_affected", 0),
            epicenter=assessment_in.event.epicenter,
        )

        result = await facility_agent.run(ctx, facility_in)
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

    # 4. Routing Node
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

    # 5. Resources Node
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
        )

        assessment_in = parse_state_into_assessment_input(state)
        as_out = state.get("assessment_output") or {}
        sev = state.get("assessed_severity") or SeverityLevel.MODERATE

        planning_out = state.get("planning_output") or {}
        prioritized_zones = [
            PrioritizedZone.model_validate(z) for z in planning_out.get("prioritized_zones", [])
        ]

        resource_in = ResourceAllocationInput(
            event=assessment_in.event,
            severity=sev,
            assessment_summary=as_out.get("affected_area_summary", ""),
            estimated_people_affected=as_out.get("estimated_people_affected", 0),
            casualties_reported=as_out.get("casualties_reported", False),
            prioritized_zones=prioritized_zones,
            reports=assessment_in.reports,
            hazard_zones=assessment_in.hazard_zones,
        )

        result = await resource_agent.run(ctx, resource_in)
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

    # 6. Conflicts Resolution Node
    async def conflicts_node(state: OrchestratorState) -> dict[str, Any]:
        conf_res = conflict_resolver.resolve(state)
        return {
            "conflicts_output": conf_res,
            "facilities_output": conf_res.get(
                "updated_facilities_output", state.get("facilities_output")
            ),
            "routing_output": conf_res.get("updated_routing_output", state.get("routing_output")),
            "needs_human_review": conf_res.get(
                "needs_human_review", state.get("needs_human_review", False)
            ),
        }

    # 7. Synthesis Node
    async def synthesis_node(state: OrchestratorState) -> dict[str, Any]:
        start = time.perf_counter()
        event_id_val = uuid.UUID(state["event_id"])
        run_id_val = uuid.UUID(state["run_id"]) if "run_id" in state else uuid.uuid4()

        ctx = RunContext(
            event_id=event_id_val,
            run_id=run_id_val,
            agent_name=AgentName.SYNTHESIS,
            db=db,
            llm=llm,
        )

        assessment_in = parse_state_into_assessment_input(state)
        synth_in = SynthesisInput(
            event=assessment_in.event,
            assessment_output=state.get("assessment_output"),
            planning_output=state.get("planning_output"),
            facilities_output=state.get("facilities_output"),
            resources_output=state.get("resources_output"),
            routing_output=state.get("routing_output"),
            conflicts_output=state.get("conflicts_output"),
        )

        result = await synthesis_agent.run(ctx, synth_in)
        latency_ms = int((time.perf_counter() - start) * 1000)
        existing_outputs = list(state.get("outputs", []))

        if isinstance(result, AgentFailure):
            existing_outputs.append(
                {
                    "agent": AgentName.SYNTHESIS.value,
                    "status": result.status,
                    "payload": None,
                    "latency_ms": latency_ms,
                    "error_code": result.code,
                    "error_message": result.message,
                }
            )
            return {
                "synthesis_output": None,
                "synthesis_status": result.status,
                "outputs": existing_outputs,
            }

        existing_outputs.append(
            {
                "agent": AgentName.SYNTHESIS.value,
                "status": AgentStatus.SUCCESS,
                "payload": result.model_dump(mode="json"),
                "latency_ms": latency_ms,
                "error_code": None,
                "error_message": None,
            }
        )
        return {
            "synthesis_output": result.model_dump(mode="json"),
            "synthesis_status": AgentStatus.SUCCESS,
            "outputs": existing_outputs,
        }

    def check_assessment_branch(state: OrchestratorState) -> str:
        if state.get("assessment_status") != AgentStatus.SUCCESS:
            return END
        if state.get("needs_human_review", False):
            return END
        return "planning"

    workflow.add_node("assessment", assessment_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("facilities", facilities_node)
    workflow.add_node("routing", routing_node)
    workflow.add_node("resources", resources_node)
    workflow.add_node("conflicts", conflicts_node)
    workflow.add_node("synthesis", synthesis_node)

    workflow.set_entry_point("assessment")
    workflow.add_conditional_edges(
        "assessment",
        check_assessment_branch,
        {
            "planning": "planning",
            END: END,
        },
    )
    workflow.add_edge("planning", "facilities")
    workflow.add_edge("facilities", "routing")
    workflow.add_edge("routing", "resources")
    workflow.add_edge("resources", "conflicts")
    workflow.add_edge("conflicts", "synthesis")
    workflow.add_edge("synthesis", END)

    return workflow.compile()
