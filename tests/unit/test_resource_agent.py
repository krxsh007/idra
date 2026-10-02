from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.base import RunContext
from app.agents.resources import ResourceAllocationAgent
from app.db.models.enums import AgentName, DisasterType, ResourceKind, SeverityLevel
from app.db.models.facilities import Resource
from app.llm.fake import FakeLLMClient
from app.schemas.agents.resources import ResourceAllocationInput
from app.schemas.events import EpicenterPoint, EventResponse
from geoalchemy2.shape import from_shape
from shapely.geometry import Point


def make_sample_resource(
    kind: ResourceKind,
    label: str,
    qty_total: int,
    qty_free: int,
) -> Resource:
    pt = from_shape(Point(80.25, 13.04), srid=4326)
    r = Resource(
        id=uuid.uuid4(),
        resource_kind=kind,
        label=label,
        quantity_total=qty_total,
        quantity_free=qty_free,
        depot_location=pt,
        depot_facility_id=uuid.uuid4(),
    )
    return r


@pytest.mark.asyncio
async def test_resource_agent_allocates_and_clamps():
    agent = ResourceAllocationAgent()
    event = EventResponse(
        id=uuid.uuid4(),
        name="Adyar Flooding",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.25, lat=13.01),
        radius_m=2000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    input_data = ResourceAllocationInput(
        event=event,
        severity=SeverityLevel.SEVERE,
        assessment_summary="Heavy inundation in Adyar basin with casualties",
        estimated_people_affected=400,
        casualties_reported=True,
    )

    # Free stock: Ambulance only has 2 free (demanded 4), Rescue boat has 10 (demanded 3)
    amb = make_sample_resource(ResourceKind.AMBULANCE, "Ambulance Unit 1", 10, 2)
    med = make_sample_resource(ResourceKind.MEDICAL_TEAM, "Disaster Medics", 5, 5)
    boat = make_sample_resource(ResourceKind.RESCUE_BOAT, "Inflatable Boats", 15, 10)
    food = make_sample_resource(ResourceKind.FOOD_KIT, "Ration Packs", 100, 100)
    water = make_sample_resource(ResourceKind.WATER_TANKER, "Water Tankers", 5, 5)

    from sqlalchemy.ext.asyncio import AsyncSession

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [amb, med, boat, food, water]
    mock_db.execute.return_value = mock_res

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.RESOURCE_COORDINATION,
        db=mock_db,
        llm=FakeLLMClient(),
    )

    out = await agent.run(ctx, input_data)

    # Clamping test: Ambulance allocation must be clamped to 2 (free stock) instead of 4 requested
    amb_alloc = [a for a in out.allocations if a.resource_kind == ResourceKind.AMBULANCE]
    assert len(amb_alloc) == 1
    assert amb_alloc[0].quantity == 2
    assert any("Partial allocation for AMBULANCE" in s for s in out.shortages_identified)

    # Boat test: Requested 3, free 10 -> allocated 3
    boat_alloc = [a for a in out.allocations if a.resource_kind == ResourceKind.RESCUE_BOAT]
    assert len(boat_alloc) == 1
    assert boat_alloc[0].quantity == 3


@pytest.mark.asyncio
async def test_resource_agent_reports_shortages_when_stock_exhausted():
    agent = ResourceAllocationAgent()
    event = EventResponse(
        id=uuid.uuid4(),
        name="Adyar Flooding",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.25, lat=13.01),
        radius_m=2000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    input_data = ResourceAllocationInput(
        event=event,
        severity=SeverityLevel.SEVERE,
        assessment_summary="Heavy inundation in Adyar basin with casualties",
        estimated_people_affected=400,
        casualties_reported=True,
    )

    # Zero resources in stock
    from sqlalchemy.ext.asyncio import AsyncSession

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.RESOURCE_COORDINATION,
        db=mock_db,
        llm=FakeLLMClient(),
    )

    out = await agent.run(ctx, input_data)
    assert len(out.allocations) == 0
    assert len(out.shortages_identified) >= 3
    assert any("Insufficient stock for AMBULANCE" in s for s in out.shortages_identified)
