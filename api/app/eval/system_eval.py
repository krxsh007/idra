from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from geoalchemy2.elements import WKTElement
from scripts.seed.seed_scenarios import get_scenario_definitions
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AgentName,
    AgentStatus,
    EventStatus,
    FacilityType,
    Provenance,
    ReportSource,
    ResourceKind,
    RunStatus,
    SeverityLevel,
    VerificationStatus,
)
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.facilities import Facility, Resource
from app.db.models.runs import AgentOutput, Recommendation, ResourceAllocation
from app.gis.graph import road_graph_manager
from app.gis.routing import hazard_router
from app.gis.spatial import FacilityDistanceResult
from app.llm.fake import FakeLLMClient
from app.orchestration.engine import orchestration_engine
from app.rag.retriever import RetrievedChunk
from app.schemas.agents.assessment import AssessmentOutput, Citation, CitationSourceType


def _build_eval_scenario_objects(
    sc: dict[str, Any],
) -> tuple[
    DisasterEvent,
    list[IncidentReport],
    list[HazardZone],
    list[FacilityDistanceResult],
    list[FacilityDistanceResult],
    list[Resource],
]:
    now = datetime.now(UTC)
    ep = sc["epicenter"]
    ev = DisasterEvent(
        id=uuid.uuid4(),
        name=sc["name"],
        disaster_type=sc["disaster_type"],
        status=EventStatus.ACTIVE,
        epicenter=WKTElement(f"POINT({ep['lon']} {ep['lat']})", srid=4326),
        radius_m=sc["radius_m"],
        description=sc["description"],
        declared_at=now,
        created_at=now,
    )
    reports = [
        IncidentReport(
            id=uuid.uuid4(),
            event_id=ev.id,
            source=ReportSource.SEED,
            reporter_name="Private Citizen Name",
            reporter_phone="9876543210",
            body=rep["body"],
            location=WKTElement(f"POINT({rep['lon']} {rep['lat']})", srid=4326),
            people_affected=rep["people_affected"],
            casualties_reported=rep["casualties_reported"],
            data_provenance=Provenance.SYNTHETIC,
            reported_at=now,
            created_at=now,
        )
        for rep in sc["reports"]
    ]
    hazards: list[HazardZone] = []
    for hz in sc["hazard_zones"]:
        ring = hz["coordinates"][0]
        wkt_coords = ", ".join(f"{pt[0]} {pt[1]}" for pt in ring)
        hazards.append(
            HazardZone(
                id=uuid.uuid4(),
                event_id=ev.id,
                label=hz["label"],
                hazard_type=hz["hazard_type"],
                severity=hz["severity"],
                geom=WKTElement(f"POLYGON(({wkt_coords}))", srid=4326),
                is_impassable=hz["is_impassable"],
                active_from=now,
                created_at=now,
            )
        )
    hosp = Facility(
        id=uuid.uuid4(),
        external_ref="EVAL-HOSP-1",
        name="Rajiv Gandhi Government General Hospital",
        facility_type=FacilityType.HOSPITAL,
        location=WKTElement("POINT(80.2750 13.0815)", srid=4326),
        total_capacity=500,
        current_occupancy=200,
        has_generator=True,
        wheelchair_access=True,
        specializations=["trauma", "icu"],
        is_operational=True,
        capacity_provenance=Provenance.SIMULATED,
    )
    shelter = Facility(
        id=uuid.uuid4(),
        external_ref="EVAL-SHELTER-1",
        name="Corporation Relief Center Kotturpuram",
        facility_type=FacilityType.SHELTER,
        location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
        total_capacity=600,
        current_occupancy=100,
        has_generator=True,
        wheelchair_access=True,
        specializations=[],
        is_operational=True,
        capacity_provenance=Provenance.SIMULATED,
    )
    resources = [
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.RESCUE_BOAT,
            label="SDRF Boat",
            quantity_total=15,
            quantity_free=10,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.AMBULANCE,
            label="108 Ambulance",
            quantity_total=20,
            quantity_free=12,
            depot_facility_id=hosp.id,
            depot_location=WKTElement("POINT(80.2750 13.0815)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.FOOD_KIT,
            label="Ration Kit",
            quantity_total=500,
            quantity_free=300,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.WATER_TANKER,
            label="Water Tanker",
            quantity_total=10,
            quantity_free=8,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
    ]
    return (
        ev,
        reports,
        hazards,
        [FacilityDistanceResult(facility=hosp, distance_m=1800.0)],
        [FacilityDistanceResult(facility=shelter, distance_m=1200.0)],
        resources,
    )


def _make_eval_mock_db(
    event: DisasterEvent,
    reports: list[IncidentReport],
    hazards: list[HazardZone],
    resources: list[Resource],
) -> tuple[AsyncMock, list[Any]]:
    mock_db = AsyncMock(spec=AsyncSession)
    added: list[Any] = []

    def add_fn(obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        added.append(obj)

    mock_db.add = MagicMock(side_effect=add_fn)

    res_ev = MagicMock()
    res_ev.scalar_one_or_none.return_value = event
    res_rep = MagicMock()
    res_rep.scalars.return_value.all.return_value = reports
    res_haz = MagicMock()
    res_haz.scalars.return_value.all.return_value = hazards
    res_res = MagicMock()
    res_res.scalars.return_value.all.return_value = resources
    res_blk = MagicMock()
    res_blk.all.return_value = []

    async def exec_fn(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(stmt)
        if "FROM disaster_events" in sql:
            return res_ev
        if "FROM incident_reports" in sql:
            return res_rep
        if "FROM hazard_zones" in sql and "road_edges" not in sql:
            return res_haz
        if "FROM resources" in sql:
            return res_res
        return res_blk

    mock_db.execute.side_effect = exec_fn
    return mock_db, added


async def run_system_evaluation() -> dict[str, Any]:
    """Run the System, Orchestration, and Reliability evaluation suite."""
    road_graph_manager.load_graph()
    G = road_graph_manager.get_graph()
    scenarios = get_scenario_definitions()

    e2e_passed = 0
    tier_b_survival_passed = 0
    verification_gate_passed = 0
    verification_gate_total = 0
    run_latencies_ms: list[float] = []

    for sc in scenarios:
        ev, reports, hazards, hosp_res, shelter_res, resources = _build_eval_scenario_objects(sc)
        mock_db, added = _make_eval_mock_db(ev, reports, hazards, resources)

        chunk = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            doc_title="NDMA & TNSDMA SOP",
            source_type="SOP",
            hazard_types=[sc["disaster_type"]],
            section_path="Section 3.1",
            content="Immediate evacuation and medical triage take highest priority.",
            vector_score=0.88,
            lexical_score=0.75,
            hybrid_score=0.84,
            published_at=datetime.now(UTC).date(),
        )
        cite = Citation(
            source_type=CitationSourceType.SOP,
            source_id=str(chunk.chunk_id),
            snippet="Immediate evacuation and medical triage take highest priority.",
        )
        ass_out = AssessmentOutput(
            severity=SeverityLevel.SEVERE,
            confidence=0.88,
            affected_area_summary=f"Impact across {sc['name']} requiring immediate response.",
            estimated_people_affected=300,
            casualties_reported=True,
            evacuation_recommended=True,
            key_factors=["High water/structural hazard", "Verified casualties"],
            citations=[cite],
        )
        fake_llm = FakeLLMClient(fixture_responses=[ass_out])

        async def fake_nearby(
            db: Any,
            lon: float,
            lat: float,
            radius_m: float = 10000.0,
            facility_type: FacilityType | None = None,
            _hosp: list[FacilityDistanceResult] = hosp_res,
            _shelter: list[FacilityDistanceResult] = shelter_res,
            **kwargs: Any,
        ) -> list[FacilityDistanceResult]:
            return _hosp if facility_type == FacilityType.HOSPITAL else _shelter

        t0 = time.perf_counter()
        with (
            patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as m_ass,
            patch("app.agents.rescue_planning.retriever.search", new_callable=AsyncMock) as m_plan,
            patch("app.agents.facilities.get_nearby_facilities", side_effect=fake_nearby),
        ):
            m_ass.return_value = [chunk]
            m_plan.return_value = [chunk]
            run_rec = await orchestration_engine.run_pipeline(
                event_id=ev.id,
                triggered_by=uuid.uuid4(),
                db=mock_db,
                llm=fake_llm,
            )
        run_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        if run_rec.status == RunStatus.COMPLETED:
            e2e_passed += 1

        recs = [o for o in added if isinstance(o, Recommendation)]
        allocs = [o for o in added if isinstance(o, ResourceAllocation)]
        verification_gate_total += 1
        if (
            recs
            and all(r.verification_status == VerificationStatus.PENDING for r in recs)
            and all(a.is_committed is False for a in allocs)
        ):
            verification_gate_passed += 1

        # Now run with LLM disabled to verify Tier B survival
        mock_db_b, added_b = _make_eval_mock_db(ev, reports, hazards, resources)
        dead_llm = FakeLLMClient(error_to_raise=RuntimeError("LLM_UNAVAILABLE"))
        with (
            patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as m_ass2,
            patch("app.agents.rescue_planning.retriever.search", new_callable=AsyncMock) as m_plan2,
            patch("app.agents.facilities.get_nearby_facilities", side_effect=fake_nearby),
        ):
            m_ass2.return_value = [chunk]
            m_plan2.return_value = [chunk]
            run_b = await orchestration_engine.run_pipeline(
                event_id=ev.id,
                triggered_by=uuid.uuid4(),
                db=mock_db_b,
                llm=dead_llm,
            )
        outputs_b = {o.agent: o for o in added_b if isinstance(o, AgentOutput)}
        if (
            run_b.status == RunStatus.PARTIAL
            and outputs_b[AgentName.HOSPITAL_RECOMMENDATION].status == AgentStatus.SUCCESS
            and outputs_b[AgentName.EVACUATION].status == AgentStatus.SUCCESS
            and outputs_b[AgentName.RESOURCE_COORDINATION].status == AgentStatus.SUCCESS
        ):
            tier_b_survival_passed += 1

    # Concurrent graph immutability check (10 parallel route computations)
    initial_nodes = G.number_of_nodes()
    initial_edges = G.number_of_edges()

    async def _route_worker(idx: int) -> dict[str, Any] | None:
        return hazard_router.compute_route(
            origin_lon=80.22,
            origin_lat=13.025,
            dest_lon=80.255,
            dest_lat=13.068,
            blocked_edges={(1003 + (idx % 3), 1004 + (idx % 3))},
        )

    concurrent_results = await asyncio.gather(*[_route_worker(i) for i in range(10)])
    graph_unchanged = (
        G.number_of_nodes() == initial_nodes
        and G.number_of_edges() == initial_edges
        and all(r is not None for r in concurrent_results)
    )
    immutability_rate = 1.0 if graph_unchanged else 0.0

    lat_sorted = sorted(run_latencies_ms)
    p50_ms = lat_sorted[len(lat_sorted) // 2] if lat_sorted else 0.0
    p95_ms = lat_sorted[-1] if lat_sorted else 0.0

    e2e_rate = round(e2e_passed / len(scenarios), 4)
    tier_b_rate = round(tier_b_survival_passed / len(scenarios), 4)
    gate_rate = round(verification_gate_passed / max(verification_gate_total, 1), 4)

    return {
        "suite": "system_eval",
        "scenarios_evaluated": len(scenarios),
        "metrics": {
            "e2e_scenario_completion_rate": {
                "value": e2e_rate,
                "target": 1.00,
                "operator": "==",
                "passed": e2e_rate == 1.00,
            },
            "tier_b_llm_disabled_survival_rate": {
                "value": tier_b_rate,
                "target": 1.00,
                "operator": "==",
                "passed": tier_b_rate == 1.00,
            },
            "verification_gate_enforcement_rate": {
                "value": gate_rate,
                "target": 1.00,
                "operator": "==",
                "passed": gate_rate == 1.00,
            },
            "concurrent_graph_immutability_rate": {
                "value": immutability_rate,
                "target": 1.00,
                "operator": "==",
                "passed": immutability_rate == 1.00,
            },
            "orchestration_run_latency_p50_ms": {
                "value": round(p50_ms, 2),
                "target": 5000.0,
                "operator": "<=",
                "passed": p50_ms <= 5000.0,
            },
            "orchestration_run_latency_p95_ms": {
                "value": round(p95_ms, 2),
                "target": 15000.0,
                "operator": "<=",
                "passed": p95_ms <= 15000.0,
            },
        },
    }
