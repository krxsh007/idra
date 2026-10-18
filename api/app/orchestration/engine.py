from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx
import structlog
from app.core.config import settings
from app.core.errors import AppException, ErrorCode
from app.db.models.enums import AgentName, AgentStatus, RunStatus, VerificationStatus
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.runs import (
    AgentOutput,
    AgentRun,
    Recommendation,
    RecommendationCitation,
    ResourceAllocation,
    Route,
)
from app.llm.client import LLMClient
from app.orchestration.graph import create_orchestrator_graph
from app.orchestration.state import OrchestratorState
from geoalchemy2.functions import ST_GeomFromText, ST_MakePoint, ST_SetSRID
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def fetch_weather_context(lon: float, lat: float) -> dict[str, Any] | None:
    """Fetch current weather from Open-Meteo with strict 3s timeout; return None on failure."""
    if not settings.WEATHER_ENABLED:
        return None
    try:
        url = (
            f"{settings.OPEN_METEO_BASE_URL}/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true"
        )
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            cw = data.get("current_weather", {})
            return {
                "windspeed_kph": cw.get("windspeed", 0),
                "temperature_c": cw.get("temperature", 0),
                "weathercode": cw.get("weathercode", 0),
            }
    except Exception as e:
        logger.warning("open_meteo_unavailable", error=str(e))
        return None


def serialize_event(event: DisasterEvent) -> dict[str, Any]:
    shape = to_shape(event.epicenter)
    return {
        "id": str(event.id),
        "name": event.name,
        "disaster_type": event.disaster_type.value,
        "status": event.status.value,
        "epicenter": {"lon": shape.x, "lat": shape.y},
        "radius_m": event.radius_m,
        "declared_at": event.declared_at.isoformat(),
        "description": event.description,
        "created_at": event.created_at.isoformat(),
    }


def serialize_report(report: IncidentReport) -> dict[str, Any]:
    shape = to_shape(report.location)
    return {
        "id": str(report.id),
        "event_id": str(report.event_id) if report.event_id else None,
        "source": report.source.value,
        "body": report.body,
        "location": {"lon": shape.x, "lat": shape.y},
        "casualties_reported": report.casualties_reported,
        "people_affected": report.people_affected,
        "data_provenance": report.data_provenance.value,
        "reported_at": report.reported_at.isoformat(),
        "created_at": report.created_at.isoformat(),
    }


def serialize_hazard(hazard: HazardZone) -> dict[str, Any]:
    shape = to_shape(hazard.geom)
    geo_dict = mapping(shape)
    return {
        "id": str(hazard.id),
        "event_id": str(hazard.event_id),
        "label": hazard.label,
        "hazard_type": hazard.hazard_type.value,
        "severity": hazard.severity.value,
        "geometry": geo_dict,
        "is_impassable": hazard.is_impassable,
        "active_from": hazard.active_from.isoformat(),
        "created_at": hazard.created_at.isoformat(),
    }


class OrchestrationEngine:
    """Coordinates multi-agent state machine execution, database persistence, and timeout limits."""

    def __init__(self) -> None:
        self._run_events: dict[str, list[dict[str, Any]]] = {}
        # Outputs of agents that have finished in a run still in progress (persisted at the end).
        self._live_outputs: dict[str, list[dict[str, Any]]] = {}

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._run_events.get(run_id, []))

    def get_live_outputs(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._live_outputs.get(run_id, []))

    async def run_pipeline(
        self,
        event_id: uuid.UUID,
        triggered_by: uuid.UUID | None,
        db: AsyncSession,
        llm: LLMClient,
    ) -> AgentRun:
        log = logger.bind(event_id=str(event_id))
        log.info("pipeline_started")
        start_time = time.perf_counter()

        try:
            # 1. Fetch domain context
            stmt_ev = select(DisasterEvent).where(DisasterEvent.id == event_id)
            res_ev = await db.execute(stmt_ev)
            event = res_ev.scalar_one_or_none()
        except (OperationalError, SQLAlchemyError, OSError, ConnectionError) as db_err:
            raise AppException(
                code=ErrorCode.DB_UNAVAILABLE,
                message=f"Database unavailable: {db_err}",
                status_code=503,
            ) from db_err

        if not event:
            raise ValueError(f"DisasterEvent {event_id} not found")

        stmt_rep = select(IncidentReport).where(IncidentReport.event_id == event_id)
        res_rep = await db.execute(stmt_rep)
        reports = list(res_rep.scalars().all())

        stmt_haz = select(HazardZone).where(HazardZone.event_id == event_id)
        res_haz = await db.execute(stmt_haz)
        hazards = list(res_haz.scalars().all())

        # 2. Create AgentRun entry in DB
        agent_run = AgentRun(
            event_id=event_id,
            status=RunStatus.RUNNING,
            triggered_by=triggered_by,
            llm_backend=settings.LLM_BACKEND,
            llm_model=settings.GEMINI_MODEL,
        )
        db.add(agent_run)
        try:
            await db.commit()
            await db.refresh(agent_run)
        except (OperationalError, SQLAlchemyError, OSError, ConnectionError) as db_err:
            raise AppException(
                code=ErrorCode.DB_UNAVAILABLE,
                message=f"Database unavailable during run initialization: {db_err}",
                status_code=503,
            ) from db_err

        run_id_str = str(agent_run.id)
        self._run_events[run_id_str] = [
            {"event": "run_started", "run_id": run_id_str, "status": "RUNNING"}
        ]
        self._live_outputs[run_id_str] = []

        ep_shape = to_shape(event.epicenter)
        weather_ctx = await fetch_weather_context(ep_shape.x, ep_shape.y)

        # 3. Setup Initial State
        initial_state: OrchestratorState = {
            "run_id": run_id_str,
            "event_id": str(event_id),
            "event_data": serialize_event(event),
            "reports_data": [serialize_report(r) for r in reports],
            "hazards_data": [serialize_hazard(h) for h in hazards],
            "weather_data": weather_ctx,
            "outputs": [],
            "errors": [],
            "needs_human_review": False,
            "is_terminal": False,
        }

        compiled_graph = create_orchestrator_graph(db=db, llm=llm)

        # 4. Execute StateGraph with total timeout
        final_state: dict[str, Any] = {}

        async def execute_with_progress() -> dict[str, Any]:
            # Stream the state after every node so each agent's result is visible while the
            # rest of the pipeline is still running.
            state: dict[str, Any] = {}
            async for state in compiled_graph.astream(initial_state, stream_mode="values"):
                live = self._live_outputs[run_id_str]
                for rec in state.get("outputs", [])[len(live) :]:
                    live.append(rec)
                    self._run_events[run_id_str].append(
                        {
                            "event": "agent_completed",
                            "run_id": run_id_str,
                            "agent": rec["agent"],
                            "status": (
                                rec["status"].value
                                if hasattr(rec["status"], "value")
                                else str(rec["status"])
                            ),
                            "latency_ms": rec.get("latency_ms"),
                            "error_code": rec.get("error_code"),
                        }
                    )
            return state

        try:
            final_state = await asyncio.wait_for(
                execute_with_progress(),
                timeout=float(settings.RUN_TOTAL_TIMEOUT_S),
            )
        except TimeoutError:
            log.error("pipeline_total_timeout", timeout_s=settings.RUN_TOTAL_TIMEOUT_S)
            agent_run.status = RunStatus.PARTIAL
            agent_run.error_code = "PIPELINE_TOTAL_TIMEOUT"
            agent_run.total_latency_ms = int((time.perf_counter() - start_time) * 1000)
            await db.commit()
            self._run_events[run_id_str].append(
                {
                    "event": "run_completed",
                    "run_id": run_id_str,
                    "status": "PARTIAL",
                    "error_code": "PIPELINE_TOTAL_TIMEOUT",
                }
            )
            return agent_run
        except (OperationalError, SQLAlchemyError, OSError, ConnectionError) as db_err:
            raise AppException(
                code=ErrorCode.DB_UNAVAILABLE,
                message=f"Database connection lost mid-run: {db_err}",
                status_code=503,
            ) from db_err
        except Exception as e:
            log.exception("pipeline_failed", error=str(e))
            agent_run.status = RunStatus.FAILED
            agent_run.error_code = "PIPELINE_EXECUTION_ERROR"
            agent_run.total_latency_ms = int((time.perf_counter() - start_time) * 1000)
            await db.commit()
            self._run_events[run_id_str].append(
                {
                    "event": "run_completed",
                    "run_id": run_id_str,
                    "status": "FAILED",
                    "error_code": "PIPELINE_EXECUTION_ERROR",
                }
            )
            return agent_run

        # 5. Persist AgentOutputs
        raw_outputs = final_state.get("outputs", [])
        for rec in raw_outputs:
            agent_output = AgentOutput(
                run_id=agent_run.id,
                agent=AgentName(rec["agent"]),
                status=rec["status"],
                payload=rec.get("payload"),
                latency_ms=rec.get("latency_ms"),
                error_code=rec.get("error_code"),
                error_message=rec.get("error_message"),
            )
            db.add(agent_output)

        # 6. Persist Prioritized Recommendations & Citations from Synthesis
        # Confidence is only shown for AI-written items, and is the situation assessment's own
        # confidence (the model's score, or the degraded baseline's) - never a made-up constant.
        # Deterministic computations carry no confidence score.
        assessment = final_state.get("assessment_output") or {}
        assessment_confidence = assessment.get("confidence")

        def confidence_for(origin: str) -> float | None:
            return assessment_confidence if origin == "AI_GENERATED" else None

        synth_out = final_state.get("synthesis_output")
        if synth_out and isinstance(synth_out, dict) and synth_out.get("recommendations"):
            for rec_item in synth_out.get("recommendations", []):
                agent_val = rec_item.get("agent")
                try:
                    agent_enum = AgentName(agent_val)
                except Exception:
                    agent_enum = AgentName.SYNTHESIS

                rec_db = Recommendation(
                    run_id=agent_run.id,
                    event_id=event_id,
                    agent=agent_enum,
                    priority=rec_item.get("priority", 3),
                    title=rec_item.get("title", "Recommendation"),
                    body=rec_item.get("body", ""),
                    origin=rec_item.get("origin", "AI_GENERATED"),
                    confidence=confidence_for(rec_item.get("origin", "AI_GENERATED")),
                    structured_ref=rec_item.get("structured_ref"),
                    verification_status=VerificationStatus.PENDING,
                )
                db.add(rec_db)
                await db.flush()

                for cit in rec_item.get("citations", []):
                    c_id = cit.get("chunk_id")
                    chunk_uuid = None
                    if c_id:
                        try:
                            chunk_uuid = uuid.UUID(str(c_id))
                        except Exception:
                            chunk_uuid = None

                    cit_db = RecommendationCitation(
                        recommendation_id=rec_db.id,
                        chunk_id=chunk_uuid,
                        document_title=cit.get("document_title", "Official SOP Document"),
                        source_url=cit.get("source_url"),
                        quoted_span=cit.get("quoted_span"),
                        relevance_score=cit.get("relevance_score"),
                    )
                    db.add(cit_db)
        else:
            # Fallback: persist individual facility recommendations if synthesis output empty
            fac_out = final_state.get("facilities_output")
            if fac_out and isinstance(fac_out, dict):
                for hosp in fac_out.get("recommended_hospitals", []):
                    rec_h = Recommendation(
                        run_id=agent_run.id,
                        event_id=event_id,
                        agent=AgentName.HOSPITAL_RECOMMENDATION,
                        priority=1,
                        title=f"Hospital Routing: {hosp.get('name')}",
                        body=(
                            f"Recommended hospital with {hosp.get('available_capacity')} beds. "
                            f"Distance: {hosp.get('distance_m')}m."
                        ),
                        origin="DETERMINISTIC_COMPUTATION",
                        confidence=None,
                        structured_ref={"facility_id": hosp.get("facility_id")},
                        verification_status=VerificationStatus.PENDING,
                    )
                    db.add(rec_h)

                for sh in fac_out.get("recommended_shelters", []):
                    rec_s = Recommendation(
                        run_id=agent_run.id,
                        event_id=event_id,
                        agent=AgentName.SHELTER_ALLOCATION,
                        priority=2,
                        title=f"Evacuation Shelter: {sh.get('name')}",
                        body=(
                            f"Recommended shelter with {sh.get('available_capacity')} capacity. "
                            f"Distance: {sh.get('distance_m')}m."
                        ),
                        origin="DETERMINISTIC_COMPUTATION",
                        confidence=None,
                        structured_ref={"facility_id": sh.get("facility_id")},
                        verification_status=VerificationStatus.PENDING,
                    )
                    db.add(rec_s)

        # 7. Persist Resource Allocations
        res_out = final_state.get("resources_output")
        if res_out and isinstance(res_out, dict):
            for alloc_item in res_out.get("allocations", []):
                target_loc = alloc_item.get("target_location", {})
                ep_shape = to_shape(event.epicenter)
                t_lon = target_loc.get("lon", ep_shape.x)
                t_lat = target_loc.get("lat", ep_shape.y)
                alloc_db = ResourceAllocation(
                    run_id=agent_run.id,
                    resource_id=uuid.UUID(alloc_item["resource_id"]),
                    target_zone_label=alloc_item.get("target_zone_label", "Impact Area"),
                    target_location=ST_SetSRID(ST_MakePoint(t_lon, t_lat), 4326),
                    quantity=alloc_item["quantity"],
                    priority=alloc_item["priority"],
                    rationale=alloc_item.get("rationale"),
                    is_committed=False,
                )
                db.add(alloc_db)

        # 8. Persist Evacuation Routes
        rout_out = final_state.get("routing_output")
        if rout_out and isinstance(rout_out, dict):
            for route_item in rout_out.get("routes", []):
                coords = route_item.get("geometry", {}).get("coordinates", [])
                if len(coords) >= 2:
                    wkt_linestring = (
                        f"SRID=4326;LINESTRING({', '.join(f'{c[0]} {c[1]}' for c in coords)})"
                    )
                    orig = route_item.get("origin", {})
                    dest = route_item.get("destination", {})
                    o_lon, o_lat = orig.get("lon", 80.2), orig.get("lat", 13.0)
                    d_lon, d_lat = dest.get("lon", 80.2), dest.get("lat", 13.0)
                    fac_id_raw = route_item.get("destination_facility_id")
                    route_db = Route(
                        run_id=agent_run.id,
                        event_id=event_id,
                        origin=ST_SetSRID(ST_MakePoint(o_lon, o_lat), 4326),
                        destination=ST_SetSRID(ST_MakePoint(d_lon, d_lat), 4326),
                        destination_facility_id=uuid.UUID(fac_id_raw) if fac_id_raw else None,
                        path_geom=ST_GeomFromText(wkt_linestring),
                        distance_m=route_item.get("distance_m", 0.0),
                        duration_s=route_item.get("duration_s", 0.0),
                        hazard_avoided=route_item.get("hazard_avoided", True),
                        traverses_hazard=route_item.get("traverses_hazard", False),
                        blocked_edge_count=route_item.get("blocked_edges_avoided", 0),
                        algorithm=route_item.get("algorithm", "astar_hazard_penalty"),
                    )
                    db.add(route_db)

        # 9. Update Run metadata
        total_latency = int((time.perf_counter() - start_time) * 1000)
        agent_run.total_latency_ms = total_latency
        agent_run.needs_human_review = final_state.get("needs_human_review", False)
        agent_run.assessed_severity = final_state.get("assessed_severity")

        # Determine overall RunStatus
        has_insufficient = any(
            rec.get("status") == AgentStatus.INSUFFICIENT_EVIDENCE for rec in raw_outputs
        )
        has_failed = any(
            rec.get("status") in (AgentStatus.FAILED, AgentStatus.TIMEOUT) for rec in raw_outputs
        )
        has_succeeded = any(rec.get("status") == AgentStatus.SUCCESS for rec in raw_outputs)

        if has_insufficient or (agent_run.needs_human_review and not has_failed):
            agent_run.status = RunStatus.PARTIAL
        elif has_failed and has_succeeded:
            agent_run.status = RunStatus.PARTIAL
        elif has_failed:
            agent_run.status = RunStatus.FAILED
        else:
            agent_run.status = RunStatus.COMPLETED

        await db.commit()
        await db.refresh(agent_run)
        self._live_outputs.pop(run_id_str, None)
        self._run_events[run_id_str].append(
            {
                "event": "run_completed",
                "run_id": run_id_str,
                "status": agent_run.status.value,
                "total_latency_ms": total_latency,
            }
        )
        log.info("pipeline_completed", status=agent_run.status.value, latency_ms=total_latency)
        return agent_run


orchestration_engine = OrchestrationEngine()
