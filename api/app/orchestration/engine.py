from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.enums import AgentName, AgentStatus, RunStatus
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.runs import AgentOutput, AgentRun
from app.llm.client import LLMClient
from app.orchestration.graph import create_orchestrator_graph
from app.orchestration.state import OrchestratorState

logger = structlog.get_logger(__name__)


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

        # 1. Fetch domain context
        stmt_ev = select(DisasterEvent).where(DisasterEvent.id == event_id)
        res_ev = await db.execute(stmt_ev)
        event = res_ev.scalar_one_or_none()
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
        await db.commit()
        await db.refresh(agent_run)

        # 3. Setup Initial State
        initial_state: OrchestratorState = {
            "run_id": str(agent_run.id),
            "event_id": str(event_id),
            "event_data": serialize_event(event),
            "reports_data": [serialize_report(r) for r in reports],
            "hazards_data": [serialize_hazard(h) for h in hazards],
            "weather_data": None,
            "outputs": [],
            "errors": [],
            "needs_human_review": False,
            "is_terminal": False,
        }

        compiled_graph = create_orchestrator_graph(db=db, llm=llm)

        # 4. Execute StateGraph with total timeout
        final_state: dict[str, Any] = {}
        try:
            final_state = await asyncio.wait_for(
                compiled_graph.ainvoke(initial_state),
                timeout=float(settings.RUN_TOTAL_TIMEOUT_S),
            )
        except TimeoutError:
            log.error("pipeline_total_timeout", timeout_s=settings.RUN_TOTAL_TIMEOUT_S)
            agent_run.status = RunStatus.FAILED
            agent_run.error_code = "PIPELINE_TOTAL_TIMEOUT"
            agent_run.total_latency_ms = int((time.perf_counter() - start_time) * 1000)
            await db.commit()
            return agent_run
        except Exception as e:
            log.exception("pipeline_failed", error=str(e))
            agent_run.status = RunStatus.FAILED
            agent_run.error_code = "PIPELINE_EXECUTION_ERROR"
            agent_run.total_latency_ms = int((time.perf_counter() - start_time) * 1000)
            await db.commit()
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

        # 6. Update Run metadata
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

        if has_insufficient or (agent_run.needs_human_review and not has_failed):
            agent_run.status = RunStatus.PARTIAL
        elif has_failed:
            agent_run.status = RunStatus.FAILED
        else:
            agent_run.status = RunStatus.COMPLETED

        await db.commit()
        await db.refresh(agent_run)
        log.info("pipeline_completed", status=agent_run.status.value, latency_ms=total_latency)
        return agent_run


orchestration_engine = OrchestrationEngine()
