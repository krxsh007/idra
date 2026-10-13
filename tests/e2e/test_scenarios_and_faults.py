from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.agents.assessment import DisasterAssessmentAgent
from app.agents.base import AgentFailure, RunContext
from app.core.config import settings
from app.core.logging import filter_secrets
from app.core.security import get_current_user
from app.db.models.enums import (
    AgentName,
    AgentStatus,
    DisasterType,
    EventStatus,
    FacilityType,
    Provenance,
    ReportSource,
    ResourceKind,
    RunStatus,
    SeverityLevel,
    UserRole,
    VerificationStatus,
)
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.facilities import Facility, Resource
from app.db.models.runs import (
    AgentOutput,
    AgentRun,
    Recommendation,
    ResourceAllocation,
    Route,
)
from app.db.models.users import User
from app.db.session import get_db
from app.gis.graph import road_graph_manager
from app.gis.spatial import FacilityDistanceResult
from app.llm.fake import FakeLLMClient
from app.main import app
from app.orchestration.engine import (
    fetch_weather_context,
    orchestration_engine,
    serialize_report,
)
from app.rag.retriever import RetrievedChunk
from app.schemas.agents.assessment import (
    AssessmentInput,
    AssessmentOutput,
    Citation,
    CitationSourceType,
)
from app.schemas.events import EpicenterPoint, EventResponse
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_scenarios import get_scenario_definitions


def _build_scenario_orm_objects(
    scenario_def: dict[str, Any],
) -> tuple[DisasterEvent, list[IncidentReport], list[HazardZone]]:
    now = datetime.now(UTC)
    ev_id = uuid.uuid4()
    ep = scenario_def["epicenter"]
    event = DisasterEvent(
        id=ev_id,
        name=scenario_def["name"],
        disaster_type=scenario_def["disaster_type"],
        status=EventStatus.ACTIVE,
        epicenter=WKTElement(f"POINT({ep['lon']} {ep['lat']})", srid=4326),
        radius_m=scenario_def["radius_m"],
        declared_at=now,
        description=scenario_def["description"],
        created_at=now,
    )

    reports: list[IncidentReport] = []
    for rep in scenario_def["reports"]:
        reports.append(
            IncidentReport(
                id=uuid.uuid4(),
                event_id=ev_id,
                source=ReportSource.SEED,
                reporter_name="Private Citizen Name",
                reporter_phone="9876543210",
                body=rep["body"],
                location=WKTElement(f"POINT({rep['lon']} {rep['lat']})", srid=4326),
                casualties_reported=rep["casualties_reported"],
                people_affected=rep["people_affected"],
                data_provenance=Provenance.SYNTHETIC,
                reported_at=now,
                created_at=now,
            )
        )

    hazards: list[HazardZone] = []
    for hz in scenario_def["hazard_zones"]:
        ring = hz["coordinates"][0]
        wkt_coords = ", ".join(f"{pt[0]} {pt[1]}" for pt in ring)
        hazards.append(
            HazardZone(
                id=uuid.uuid4(),
                event_id=ev_id,
                label=hz["label"],
                hazard_type=hz["hazard_type"],
                severity=hz["severity"],
                geom=WKTElement(f"POLYGON(({wkt_coords}))", srid=4326),
                is_impassable=hz["is_impassable"],
                active_from=now,
                created_at=now,
            )
        )

    return event, reports, hazards


def _build_mock_facilities_and_resources() -> (
    tuple[list[FacilityDistanceResult], list[FacilityDistanceResult], list[Resource]]
):
    hosp = Facility(
        id=uuid.uuid4(),
        name="Rajiv Gandhi Government General Hospital",
        facility_type=FacilityType.HOSPITAL,
        location=WKTElement("POINT(80.2750 13.0815)", srid=4326),
        total_capacity=500,
        current_occupancy=200,
        has_generator=True,
        wheelchair_access=True,
        specializations=["Trauma", "ICU", "Burn Unit"],
        is_operational=True,
        capacity_provenance=Provenance.SIMULATED,
    )
    shelter = Facility(
        id=uuid.uuid4(),
        name="Corporation Higher Secondary School Relief Center",
        facility_type=FacilityType.SHELTER,
        location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
        total_capacity=800,
        current_occupancy=150,
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
            label="SDRF Zodiac Motorboat Unit",
            quantity_total=15,
            quantity_free=10,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.AMBULANCE,
            label="108 Emergency ALS Ambulance",
            quantity_total=20,
            quantity_free=12,
            depot_facility_id=hosp.id,
            depot_location=WKTElement("POINT(80.2750 13.0815)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.FOOD_KIT,
            label="Emergency 3-Day Dry Ration Pack",
            quantity_total=500,
            quantity_free=300,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
        Resource(
            id=uuid.uuid4(),
            resource_kind=ResourceKind.WATER_TANKER,
            label="Metro Water Mobile Tanker",
            quantity_total=10,
            quantity_free=8,
            depot_facility_id=shelter.id,
            depot_location=WKTElement("POINT(80.2420 13.0250)", srid=4326),
            data_provenance=Provenance.SIMULATED,
        ),
    ]
    return (
        [FacilityDistanceResult(facility=hosp, distance_m=1850.0)],
        [FacilityDistanceResult(facility=shelter, distance_m=1240.0)],
        resources,
    )


def _make_mock_db_for_scenario(
    event: DisasterEvent,
    reports: list[IncidentReport],
    hazards: list[HazardZone],
    resources: list[Resource],
) -> tuple[AsyncMock, list[Any]]:
    mock_db = AsyncMock(spec=AsyncSession)
    added_objects: list[Any] = []

    def add_side_effect(obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        added_objects.append(obj)

    mock_db.add = MagicMock(side_effect=add_side_effect)

    res_ev = MagicMock()
    res_ev.scalar_one_or_none.return_value = event

    res_rep = MagicMock()
    res_rep.scalars.return_value.all.return_value = reports

    res_haz = MagicMock()
    res_haz.scalars.return_value.all.return_value = hazards

    res_resources = MagicMock()
    res_resources.scalars.return_value.all.return_value = resources

    res_blocked = MagicMock()
    res_blocked.all.return_value = []

    async def execute_side_effect(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(stmt)
        if "FROM disaster_events" in sql:
            return res_ev
        if "FROM incident_reports" in sql:
            return res_rep
        if "FROM hazard_zones" in sql and "road_edges" not in sql:
            return res_haz
        if "FROM resources" in sql:
            return res_resources
        return res_blocked

    mock_db.execute.side_effect = execute_side_effect
    return mock_db, added_objects


def _make_sop_chunk(hazard_type: DisasterType) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_title="NDMA & TNSDMA Standard Operating Procedure",
        source_type="SOP",
        hazard_types=[hazard_type],
        section_path="Section 3.1 / Life Safety & Evacuation",
        content=(
            "Life safety and immediate extraction of trapped or injured persons take "
            "absolute priority. Pre-emptive evacuation to verified shelters must avoid "
            "all active impassable hazard zones."
        ),
        vector_score=0.91,
        lexical_score=0.84,
        hybrid_score=0.88,
        published_at=datetime.now(UTC).date(),
    )


# ============================================================================
# 1. END-TO-END SCENARIO SUITE (ALL 3 SEEDED SCENARIOS)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_idx", [0, 1, 2])
async def test_e2e_all_three_scenarios_and_invariants(scenario_idx: int) -> None:
    """Run full orchestration pipeline on each of the 3 seeded scenarios and verify invariants."""
    scenarios = get_scenario_definitions()
    assert len(scenarios) == 3
    sc = scenarios[scenario_idx]

    # Verify scenario definition meets M13 requirements (4-6 hazards, 15-25 reports)
    assert 4 <= len(sc["hazard_zones"]) <= 6
    assert 15 <= len(sc["reports"]) <= 25

    event, reports, hazards = _build_scenario_orm_objects(sc)
    hosp_results, shelter_results, resources = _build_mock_facilities_and_resources()
    initial_free_snapshot = {r.id: r.quantity_free for r in resources}

    mock_db, added_objects = _make_mock_db_for_scenario(event, reports, hazards, resources)
    chunk = _make_sop_chunk(sc["disaster_type"])

    assessment_fixture = AssessmentOutput(
        severity=SeverityLevel.SEVERE,
        confidence=0.89,
        affected_area_summary=f"Severe multi-sector impact for {sc['name']}.",
        estimated_people_affected=320,
        casualties_reported=True,
        evacuation_recommended=True,
        key_factors=[
            "Multiple citizen and responder reports confirm casualties.",
            "Active impassable hazard zones obstructing primary corridors.",
        ],
        citations=[
            Citation(
                source_type=CitationSourceType.SOP,
                source_id=str(chunk.chunk_id),
                snippet="Life safety and immediate extraction take absolute priority.",
            )
        ],
    )
    fake_llm = FakeLLMClient(fixture_responses=[assessment_fixture])

    async def fake_nearby_facilities(
        db: Any,
        lon: float,
        lat: float,
        radius_m: int = 10000,
        facility_type: FacilityType | None = None,
        is_operational: bool = True,
        min_free_capacity: int = 0,
        limit: int = 10,
    ) -> list[FacilityDistanceResult]:
        if facility_type == FacilityType.HOSPITAL:
            return hosp_results
        return shelter_results

    with (
        patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_ass_ret,
        patch(
            "app.agents.rescue_planning.retriever.search", new_callable=AsyncMock
        ) as mock_plan_ret,
        patch("app.agents.facilities.get_nearby_facilities", side_effect=fake_nearby_facilities),
    ):
        mock_ass_ret.return_value = [chunk]
        mock_plan_ret.return_value = [chunk]

        run_record = await orchestration_engine.run_pipeline(
            event_id=event.id,
            triggered_by=uuid.uuid4(),
            db=mock_db,
            llm=fake_llm,
        )

    assert run_record.status == RunStatus.COMPLETED

    persisted_outputs = [o for o in added_objects if isinstance(o, AgentOutput)]
    persisted_recs = [o for o in added_objects if isinstance(o, Recommendation)]
    persisted_allocs = [o for o in added_objects if isinstance(o, ResourceAllocation)]
    persisted_routes = [o for o in added_objects if isinstance(o, Route)]

    assert len(persisted_outputs) == 6
    assert len(persisted_recs) >= 3
    assert len(persisted_allocs) >= 1
    assert len(persisted_routes) >= 1

    # Invariant 1: Every recommendation starts PENDING with a valid origin
    for rec in persisted_recs:
        assert rec.verification_status == VerificationStatus.PENDING
        assert rec.origin in ("AI_GENERATED", "DETERMINISTIC_COMPUTATION", "HUMAN_ENTERED")
        assert 1 <= rec.priority <= 5

    # Invariant 2: No resource over-commitment & operational DB state never mutated
    alloc_sums_by_res: dict[uuid.UUID, int] = {}
    for alloc in persisted_allocs:
        assert alloc.is_committed is False
        assert alloc.quantity > 0
        alloc_sums_by_res[alloc.resource_id] = (
            alloc_sums_by_res.get(alloc.resource_id, 0) + alloc.quantity
        )

    for r in resources:
        # Operational state on Resource ORM instance was NOT mutated in-place
        assert r.quantity_free == initial_free_snapshot[r.id]
        # Total proposed across all zones never exceeds initial quantity_free
        assert alloc_sums_by_res.get(r.id, 0) <= initial_free_snapshot[r.id]

    # Invariant 3: No facility over-booking (occupancy untouched)
    assert hosp_results[0].facility.current_occupancy == 200
    assert shelter_results[0].facility.current_occupancy == 150

    # Invariant 4: Every persisted route has valid positive distance and duration
    for rt in persisted_routes:
        assert rt.distance_m > 0
        assert rt.duration_s > 0


# ============================================================================
# 2. FAULT INJECTION SUITE (ALL 9 ROWS OF SECTION 12.8 FAILURE TABLE)
# ============================================================================


@pytest.mark.asyncio
async def test_fault_row1_llm_disabled_tier_b_agents_continue() -> None:
    """Row 1 (12.8): With LLM completely unavailable, Tier A fails with LLM_UNAVAILABLE
    while Tier B (facilities, routing, resources, synthesis fallback) still succeed!"""
    sc = get_scenario_definitions()[0]
    event, reports, hazards = _build_scenario_orm_objects(sc)
    hosp_results, shelter_results, resources = _build_mock_facilities_and_resources()
    mock_db, added_objects = _make_mock_db_for_scenario(event, reports, hazards, resources)
    chunk = _make_sop_chunk(sc["disaster_type"])

    class DisabledLLM(FakeLLMClient):
        async def structured(self, *args: Any, **kwargs: Any) -> Any:
            raise ConnectionError("LLM_UNAVAILABLE: LLM backend is disabled")

    disabled_llm = DisabledLLM()

    async def fake_nearby_facilities(
        db: Any,
        lon: float,
        lat: float,
        radius_m: int = 10000,
        facility_type: FacilityType | None = None,
        **kwargs: Any,
    ) -> list[FacilityDistanceResult]:
        return hosp_results if facility_type == FacilityType.HOSPITAL else shelter_results

    with (
        patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_ass_ret,
        patch(
            "app.agents.rescue_planning.retriever.search", new_callable=AsyncMock
        ) as mock_plan_ret,
        patch("app.agents.facilities.get_nearby_facilities", side_effect=fake_nearby_facilities),
    ):
        mock_ass_ret.return_value = [chunk]
        mock_plan_ret.return_value = [chunk]

        run_record = await orchestration_engine.run_pipeline(
            event_id=event.id,
            triggered_by=uuid.uuid4(),
            db=mock_db,
            llm=disabled_llm,
        )

    # Run degrades gracefully to PARTIAL rather than crashing
    assert run_record.status == RunStatus.PARTIAL

    persisted_outputs = {o.agent: o for o in added_objects if isinstance(o, AgentOutput)}
    # Tier A agents failed with LLM_UNAVAILABLE
    assert persisted_outputs[AgentName.DISASTER_ASSESSMENT].status == AgentStatus.FAILED
    assert persisted_outputs[AgentName.DISASTER_ASSESSMENT].error_code == "LLM_UNAVAILABLE"

    # Tier B agents succeeded deterministically without LLM!
    assert persisted_outputs[AgentName.HOSPITAL_RECOMMENDATION].status == AgentStatus.SUCCESS
    assert persisted_outputs[AgentName.EVACUATION].status == AgentStatus.SUCCESS
    assert persisted_outputs[AgentName.RESOURCE_COORDINATION].status == AgentStatus.SUCCESS
    assert persisted_outputs[AgentName.SYNTHESIS].status == AgentStatus.SUCCESS

    persisted_routes = [o for o in added_objects if isinstance(o, Route)]
    persisted_recs = [o for o in added_objects if isinstance(o, Recommendation)]
    assert len(persisted_routes) >= 1
    assert len(persisted_recs) >= 2


@pytest.mark.asyncio
async def test_fault_row2_llm_invalid_json_repair_then_failure() -> None:
    """Row 2 (12.8): Invalid JSON triggers 1 repair retry, then returns LLM_INVALID_OUTPUT."""
    agent = DisasterAssessmentAgent()
    now = datetime.now(UTC)
    ev = EventResponse(
        id=uuid.uuid4(),
        name="Invalid JSON Test Event",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=EpicenterPoint(lon=80.24, lat=13.02),
        radius_m=2000,
        declared_at=now,
        created_at=now,
    )
    chunk = _make_sop_chunk(DisasterType.FLOOD)

    broken_llm = FakeLLMClient(
        fixture_responses=[
            {"corrupted": "not_an_assessment"},
            {"still_corrupted": 123},
        ]
    )
    ctx = RunContext(
        event_id=ev.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=broken_llm,
        max_repair_retries=1,
    )

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_ret:
        mock_ret.return_value = [chunk]
        result = await agent.run(ctx, AssessmentInput(event=ev))

    assert isinstance(result, AgentFailure)
    assert result.status == AgentStatus.FAILED
    assert result.code == "LLM_INVALID_OUTPUT"
    assert broken_llm.call_count == 2


@pytest.mark.asyncio
async def test_fault_row3_database_unavailable_returns_503(async_client: AsyncClient) -> None:
    """Row 3 (12.8): Database connection failure mid-request returns 503 DB_UNAVAILABLE."""
    responder = User(
        id=uuid.uuid4(),
        email="resp@idra.test",
        password_hash="hash",
        full_name="Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    mock_db = AsyncMock()
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("Connection refused"))

    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        res = await async_client.post(
            "/api/v1/runs",
            json={"event_id": str(uuid.uuid4()), "force": True},
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "DB_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fault_row4_road_graph_missing_degrades_gracefully(
    async_client: AsyncClient,
) -> None:
    """Row 4 (12.8): Missing road graph marks /health/deep degraded and /agents/routing 503."""
    responder = User(
        id=uuid.uuid4(),
        email="resp@idra.test",
        password_hash="hash",
        full_name="Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    mock_db = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db

    road_graph_manager.set_unavailable(True)
    try:
        # 1. /health/deep reports degraded
        health_res = await async_client.get("/api/v1/health/deep")
        assert health_res.status_code == 200
        h_data = health_res.json()
        assert h_data["status"] == "degraded"
        assert h_data["components"]["road_graph"]["status"] == "unavailable"

        # 2. /agents/routing returns 503 ROAD_GRAPH_UNAVAILABLE
        now_iso = datetime.now(UTC).isoformat()
        route_res = await async_client.post(
            "/api/v1/agents/routing",
            json={
                "event": {
                    "id": str(uuid.uuid4()),
                    "name": "Test Flood",
                    "disaster_type": "FLOOD",
                    "status": "ACTIVE",
                    "epicenter": {"lon": 80.24, "lat": 13.02},
                    "radius_m": 2000,
                    "declared_at": now_iso,
                    "created_at": now_iso,
                },
                "reports": [],
                "recommended_shelters": [],
                "recommended_hospitals": [],
                "hazard_zones": [],
            },
        )
        assert route_res.status_code == 503
        assert route_res.json()["detail"]["code"] == "ROAD_GRAPH_UNAVAILABLE"
    finally:
        road_graph_manager.set_unavailable(False)
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fault_row5_open_meteo_timeout_omitted_without_blocking() -> None:
    """Row 5 (12.8): Open-Meteo 3s timeout returns None and never blocks assessment."""
    with (
        patch.object(settings, "WEATHER_ENABLED", True),
        patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("3s timeout")),
    ):
        weather = await fetch_weather_context(80.25, 13.02)
        assert weather is None


@pytest.mark.asyncio
async def test_fault_row6_no_route_found_when_origin_outside_snap_distance() -> None:
    """Row 6 (12.8): Origin outside snap radius records unreachable without crashing."""
    from app.agents.routing import RoutingAgent
    from app.schemas.agents.facilities import FacilityCandidate
    from app.schemas.agents.routing import RoutingInput

    agent = RoutingAgent()
    now = datetime.now(UTC)
    # Coordinate far outside road network snap threshold
    ev = EventResponse(
        id=uuid.uuid4(),
        name="Offshore Cyclone",
        disaster_type=DisasterType.CYCLONE,
        status=EventStatus.ACTIVE,
        epicenter=EpicenterPoint(lon=80.15, lat=12.95),
        radius_m=2000,
        declared_at=now,
        created_at=now,
    )
    shelter = FacilityCandidate(
        facility_id=uuid.uuid4(),
        name="Central Shelter",
        facility_type=FacilityType.SHELTER,
        distance_m=1500.0,
        total_capacity=300,
        current_occupancy=50,
        available_capacity=250,
        has_generator=True,
        wheelchair_access=True,
    )
    ctx = RunContext(event_id=ev.id, agent_name=AgentName.EVACUATION, llm=FakeLLMClient())

    with patch("app.gis.routing.hazard_router.compute_route", return_value=None):
        out = await agent.run(
            ctx,
            RoutingInput(event=ev, recommended_shelters=[shelter]),
        )
    assert not isinstance(out, AgentFailure)
    assert out.total_routes_computed == 0
    assert len(out.unreachable_locations) == 1


@pytest.mark.asyncio
async def test_fault_row7_retrieval_below_floor_makes_zero_llm_calls() -> None:
    """Row 7 (12.8): Retrieval returning nothing above floor returns INSUFFICIENT_EVIDENCE
    with 0 LLM calls."""
    sc = get_scenario_definitions()[0]
    event, reports, hazards = _build_scenario_orm_objects(sc)
    mock_db, added_objects = _make_mock_db_for_scenario(event, reports, hazards, [])
    fake_llm = FakeLLMClient()

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_ret:
        mock_ret.return_value = []
        run_record = await orchestration_engine.run_pipeline(
            event_id=event.id,
            triggered_by=uuid.uuid4(),
            db=mock_db,
            llm=fake_llm,
        )

    assert fake_llm.call_count == 0
    assert run_record.status == RunStatus.PARTIAL
    persisted_outputs = [o for o in added_objects if isinstance(o, AgentOutput)]
    assert len(persisted_outputs) == 1
    assert persisted_outputs[0].status == AgentStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.asyncio
async def test_fault_row8_single_agent_timeout_continues_as_partial() -> None:
    """Row 8 (12.8): Single downstream agent exceeding budget records AGENT_TIMEOUT
    and run continues as PARTIAL."""
    sc = get_scenario_definitions()[0]
    event, reports, hazards = _build_scenario_orm_objects(sc)
    hosp_results, shelter_results, resources = _build_mock_facilities_and_resources()
    mock_db, added_objects = _make_mock_db_for_scenario(event, reports, hazards, resources)
    chunk = _make_sop_chunk(sc["disaster_type"])

    assessment_fixture = AssessmentOutput(
        severity=SeverityLevel.HIGH,
        confidence=0.85,
        affected_area_summary="High flood waters in Kotturpuram.",
        estimated_people_affected=200,
        casualties_reported=True,
        evacuation_recommended=True,
        key_factors=["Active flood hazard zones reported."],
        citations=[
            Citation(
                source_type=CitationSourceType.SOP,
                source_id=str(chunk.chunk_id),
                snippet="Evacuation priority.",
            )
        ],
    )
    fake_llm = FakeLLMClient(fixture_responses=[assessment_fixture])

    async def fake_nearby_facilities(
        db: Any,
        lon: float,
        lat: float,
        radius_m: int = 10000,
        facility_type: FacilityType | None = None,
        **kwargs: Any,
    ) -> list[FacilityDistanceResult]:
        return hosp_results if facility_type == FacilityType.HOSPITAL else shelter_results

    async def timeout_planning_run(*args: Any, **kwargs: Any) -> AgentFailure:
        return AgentFailure(
            status=AgentStatus.TIMEOUT,
            code="AGENT_TIMEOUT",
            message="RescuePlanningAgent timed out.",
        )

    with (
        patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_ass_ret,
        patch(
            "app.orchestration.graph.planning_agent.run",
            side_effect=timeout_planning_run,
        ),
        patch("app.agents.facilities.get_nearby_facilities", side_effect=fake_nearby_facilities),
    ):
        mock_ass_ret.return_value = [chunk]
        run_record = await orchestration_engine.run_pipeline(
            event_id=event.id,
            triggered_by=uuid.uuid4(),
            db=mock_db,
            llm=fake_llm,
        )

    assert run_record.status == RunStatus.PARTIAL
    persisted_outputs = {o.agent: o for o in added_objects if isinstance(o, AgentOutput)}
    assert persisted_outputs[AgentName.RESCUE_PLANNING].status == AgentStatus.TIMEOUT
    assert persisted_outputs[AgentName.RESCUE_PLANNING].error_code == "AGENT_TIMEOUT"
    assert persisted_outputs[AgentName.HOSPITAL_RECOMMENDATION].status == AgentStatus.SUCCESS
    assert persisted_outputs[AgentName.EVACUATION].status == AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_fault_row9_whole_run_budget_timeout_marks_partial() -> None:
    """Row 9 (12.8): Outer run timeout marks run PARTIAL with PIPELINE_TOTAL_TIMEOUT."""
    sc = get_scenario_definitions()[0]
    event, reports, hazards = _build_scenario_orm_objects(sc)
    mock_db, _ = _make_mock_db_for_scenario(event, reports, hazards, [])

    async def slow_graph_stream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        await asyncio.sleep(0.5)
        yield {}

    mock_compiled = MagicMock()
    mock_compiled.astream = slow_graph_stream

    with (
        patch.object(settings, "RUN_TOTAL_TIMEOUT_S", 0.02),
        patch(
            "app.orchestration.engine.create_orchestrator_graph",
            return_value=mock_compiled,
        ),
    ):
        run_record = await orchestration_engine.run_pipeline(
            event_id=event.id,
            triggered_by=uuid.uuid4(),
            db=mock_db,
            llm=FakeLLMClient(),
        )

    assert run_record.status == RunStatus.PARTIAL
    assert run_record.error_code == "PIPELINE_TOTAL_TIMEOUT"


# ============================================================================
# 3. SSE PROGRESS STREAMING, CONCURRENT RUN GUARD, SMOKE SCRIPT, SECURITY PASS
# ============================================================================


@pytest.mark.asyncio
async def test_sse_run_progress_streaming(async_client: AsyncClient) -> None:
    """Verify GET /api/v1/runs/{run_id}/stream emits valid SSE data frames."""
    run_id = uuid.uuid4()
    orchestration_engine._run_events[str(run_id)] = [
        {"event": "run_started", "run_id": str(run_id), "status": "RUNNING"},
        {
            "event": "agent_completed",
            "run_id": str(run_id),
            "agent": "DISASTER_ASSESSMENT",
            "status": "SUCCESS",
            "latency_ms": 120,
        },
        {
            "event": "run_completed",
            "run_id": str(run_id),
            "status": "COMPLETED",
            "total_latency_ms": 450,
        },
    ]

    res = await async_client.get(f"/api/v1/runs/{run_id}/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    lines = [ln for ln in res.text.splitlines() if ln.startswith("data: ")]
    assert len(lines) == 3
    first_frame = json.loads(lines[0].removeprefix("data: "))
    last_frame = json.loads(lines[-1].removeprefix("data: "))
    assert first_frame["event"] == "run_started"
    assert last_frame["event"] == "run_completed"
    assert last_frame["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_concurrent_run_returns_409_unless_force(async_client: AsyncClient) -> None:
    """Verify POST /api/v1/runs returns 409 CONFLICT when an active run is in progress."""
    responder = User(
        id=uuid.uuid4(),
        email="resp@idra.test",
        password_hash="hash",
        full_name="Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    event_id = uuid.uuid4()
    active_run = AgentRun(
        id=uuid.uuid4(),
        event_id=event_id,
        status=RunStatus.RUNNING,
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = active_run
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        res = await async_client.post(
            "/api/v1/runs",
            json={"event_id": str(event_id), "force": False},
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "CONFLICT"
    finally:
        app.dependency_overrides.clear()


def test_smoke_script_exits_nonzero_when_api_down() -> None:
    """Verify scripts/smoke.sh exits non-zero when pointing to an unreachable port."""
    proc = subprocess.run(
        ["bash", "scripts/smoke.sh"],
        env={"API_URL": "http://127.0.0.1:59999/api/v1", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "FAIL" in proc.stderr or "FAIL" in proc.stdout


def test_security_pass_no_secrets_logged_and_pii_stripped() -> None:
    """Verify structlog filter redacts secrets and serialize_report strips PII."""
    # 1. Secret redaction in logs
    log_event: dict[str, Any] = {
        "event": "auth_check",
        "jwt_secret": "super_secret_jwt_123",
        "gemini_api_key": "AIzaSySecretKey",
        "user_password": "plain_password",
        "authorization_header": "Bearer secret_token",
        "safe_field": "visible_value",
    }
    redacted = filter_secrets(None, "info", log_event)
    assert redacted["jwt_secret"] == "[REDACTED]"
    assert redacted["gemini_api_key"] == "[REDACTED]"
    assert redacted["user_password"] == "[REDACTED]"
    assert redacted["authorization_header"] == "[REDACTED]"
    assert redacted["safe_field"] == "visible_value"

    # 2. PII stripped before reaching LLM state
    sc = get_scenario_definitions()[0]
    _, reports, _ = _build_scenario_orm_objects(sc)
    serialized = serialize_report(reports[0])
    assert "reporter_name" not in serialized
    assert "reporter_phone" not in serialized
    assert "Private Citizen Name" not in json.dumps(serialized)
    assert "9876543210" not in json.dumps(serialized)
