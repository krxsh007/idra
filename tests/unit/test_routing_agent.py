from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.agents.base import RunContext
from app.agents.routing import RoutingAgent
from app.db.models.enums import AgentName, DisasterType, FacilityType, Provenance, ReportSource
from app.gis.graph import road_graph_manager
from app.llm.fake import FakeLLMClient
from app.schemas.agents.facilities import FacilityCandidate
from app.schemas.agents.routing import RoutingInput
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.reports import ReportResponse


@pytest.fixture(autouse=True)
def ensure_graph():
    road_graph_manager.load_graph()


@pytest.mark.asyncio
async def test_routing_agent_computes_routes_for_reports():
    agent = RoutingAgent()
    event = EventResponse(
        id=uuid.uuid4(),
        name="Adyar Floods",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.25, lat=13.0),
        radius_m=3000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    shelter = FacilityCandidate(
        facility_id=uuid.uuid4(),
        name="Velachery Relief Center",
        facility_type=FacilityType.SHELTER,
        distance_m=1200.0,
        total_capacity=500,
        current_occupancy=50,
        available_capacity=450,
        has_generator=True,
        wheelchair_access=True,
    )

    hospital = FacilityCandidate(
        facility_id=uuid.uuid4(),
        name="Apollo Hospital",
        facility_type=FacilityType.HOSPITAL,
        distance_m=1800.0,
        total_capacity=800,
        current_occupancy=400,
        available_capacity=400,
        has_generator=True,
        wheelchair_access=True,
    )

    report1 = ReportResponse(
        id=uuid.uuid4(),
        event_id=event.id,
        source=ReportSource.CITIZEN,
        body="Water rising on 100 Feet Road, need evacuation",
        location=EpicenterPoint(lon=80.252, lat=13.002),
        casualties_reported=False,
        people_affected=20,
        data_provenance=Provenance.REAL,
        reported_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    report2 = ReportResponse(
        id=uuid.uuid4(),
        event_id=event.id,
        source=ReportSource.RESPONDER,
        body="Elderly citizen injured in collapsed wall",
        location=EpicenterPoint(lon=80.255, lat=13.005),
        casualties_reported=True,
        people_affected=2,
        data_provenance=Provenance.REAL,
        reported_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )

    routing_input = RoutingInput(
        event=event,
        reports=[report1, report2],
        recommended_shelters=[shelter],
        recommended_hospitals=[hospital],
    )

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.EVACUATION,
        db=None,
        llm=FakeLLMClient(),
    )

    out = await agent.run(ctx, routing_input)
    assert out.total_routes_computed >= 2
    # Verify primary corridor and individual report routes exist
    assert any("Primary civilian evacuation" in r.rationale for r in out.routes)
    assert any("Medical rescue" in r.rationale for r in out.routes)


def _zone(event_id: uuid.UUID, lon: float, lat: float, half: float, impassable: bool):
    from app.db.models.enums import SeverityLevel
    from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse

    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]
    return HazardZoneResponse(
        id=uuid.uuid4(),
        event_id=event_id,
        label="Flooded block",
        hazard_type=DisasterType.FLOOD,
        severity=SeverityLevel.SEVERE,
        geometry=GeoJSONPolygon(coordinates=[ring]),
        is_impassable=impassable,
        active_from=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def _shelter_route_input(hazard_zones):
    event = EventResponse(
        id=uuid.uuid4(),
        name="Adyar Floods",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.25, lat=13.0),
        radius_m=3000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    shelter = FacilityCandidate(
        facility_id=uuid.uuid4(),
        name="Adyar Relief Camp",
        facility_type=FacilityType.SHELTER,
        distance_m=1500.0,
        total_capacity=500,
        current_occupancy=0,
        available_capacity=500,
        has_generator=True,
        wheelchair_access=True,
    )
    zones = [z(event.id) for z in hazard_zones]
    return event, RoutingInput(event=event, recommended_shelters=[shelter], hazard_zones=zones)


async def _primary_route(hazard_zones):
    event, routing_input = _shelter_route_input(hazard_zones)
    ctx = RunContext(
        event_id=event.id, agent_name=AgentName.EVACUATION, db=None, llm=FakeLLMClient()
    )
    out = await RoutingAgent().run(ctx, routing_input)
    return out.routes[0]


@pytest.mark.asyncio
async def test_routing_detours_around_hazard_zone_on_the_shortest_path():
    baseline = await _primary_route([])
    mid_lon, mid_lat = baseline.geometry.coordinates[len(baseline.geometry.coordinates) // 2]

    zone = lambda eid: _zone(eid, mid_lon, mid_lat, 0.0015, impassable=False)  # noqa: E731
    detour = await _primary_route([zone])

    assert detour.hazard_avoided is True
    assert detour.traverses_hazard is False
    assert detour.starts_in_hazard is False
    assert detour.distance_m > baseline.distance_m


@pytest.mark.asyncio
async def test_routing_exits_impassable_zone_that_contains_the_origin():
    # The epicenter sits inside an impassable zone: the route must still get people out.
    zone = lambda eid: _zone(eid, 80.25, 13.0, 0.002, impassable=True)  # noqa: E731
    route = await _primary_route([zone])

    assert route.starts_in_hazard is True
    assert route.hazard_avoided is True  # no *other* hazard zone is crossed
    assert "shortest way out" in route.rationale
