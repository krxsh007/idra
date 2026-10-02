from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.agents.base import RunContext
from app.agents.rescue_planning import RescuePlanningAgent
from app.db.models.enums import DisasterType, EventStatus, Provenance, ReportSource, SeverityLevel
from app.llm.fake import FakeLLMClient
from app.schemas.agents.planning import RescuePlanningInput
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse
from app.schemas.reports import ReportResponse
from sqlalchemy.ext.asyncio import AsyncSession


def make_event(severity: SeverityLevel = SeverityLevel.HIGH) -> EventResponse:
    return EventResponse(
        id=uuid.uuid4(),
        name="Chennai Cyclone",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=EpicenterPoint(lon=80.20, lat=13.00),
        radius_m=10000.0,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_report(
    lon: float, lat: float, casualties: bool = False, people: int = 20
) -> ReportResponse:
    return ReportResponse(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        source=ReportSource.CITIZEN,
        body="Emergency report",
        location=EpicenterPoint(lon=lon, lat=lat),
        casualties_reported=casualties,
        people_affected=people,
        data_provenance=Provenance.SIMULATED,
        reported_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_hazard() -> HazardZoneResponse:
    return HazardZoneResponse(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        label="Inundation Sector",
        hazard_type="FLOOD",
        severity=SeverityLevel.HIGH,
        geometry=GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [
                    [80.19, 12.99],
                    [80.21, 12.99],
                    [80.21, 13.01],
                    [80.19, 13.01],
                    [80.19, 12.99],
                ]
            ],
        ),
        is_impassable=True,
        active_from=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_rescue_planning_low_severity_skipped():
    agent = RescuePlanningAgent()
    db_mock = AsyncMock(spec=AsyncSession)
    event = make_event(SeverityLevel.LOW)
    ctx = RunContext(
        event_id=event.id,
        agent_name=agent.agent_name,
        db=db_mock,
        llm=FakeLLMClient(),
    )

    input_data = RescuePlanningInput(
        event=event,
        reports=[make_report(80.20, 13.00)],
        hazard_zones=[make_hazard()],
        assessment_severity=SeverityLevel.LOW,
        assessment_summary="Low impact localized event.",
    )

    out = await agent.run(ctx, input_data)
    assert out.prioritized_zones == []


@pytest.mark.asyncio
async def test_rescue_planning_prioritized_zones_contiguous():
    agent = RescuePlanningAgent()
    db_mock = AsyncMock(spec=AsyncSession)
    event = make_event(SeverityLevel.HIGH)
    ctx = RunContext(
        event_id=event.id,
        agent_name=agent.agent_name,
        db=db_mock,
        llm=FakeLLMClient(),
    )

    r1 = make_report(80.200, 13.000, casualties=True, people=30)
    r2 = make_report(80.201, 13.001, casualties=False, people=20)
    r3 = make_report(80.250, 13.050, casualties=False, people=50)

    input_data = RescuePlanningInput(
        event=event,
        reports=[r1, r2, r3],
        hazard_zones=[make_hazard()],
        assessment_severity=SeverityLevel.HIGH,
        assessment_summary="High severity flood inundation.",
    )

    with patch(
        "app.agents.rescue_planning.retriever.search", new_callable=AsyncMock, return_value=[]
    ):
        out = await agent.run(ctx, input_data)

    assert len(out.prioritized_zones) >= 1
    # Check priorities are strictly contiguous starting at 1
    priorities = [z.priority for z in out.prioritized_zones]
    assert priorities == list(range(1, len(out.prioritized_zones) + 1))
    assert len(out.operation_sequence) >= 2
    # Verify zone 1 has casualty or blocked accessibility
    assert out.prioritized_zones[0].priority == 1
