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
        name="Velachery Floods",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.22, lat=12.98),
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
        location=EpicenterPoint(lon=80.222, lat=12.982),
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
        location=EpicenterPoint(lon=80.225, lat=12.985),
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
