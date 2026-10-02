from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.base import RunContext
from app.agents.resources import ResourceAllocationAgent
from app.db.models.enums import AgentName, DisasterType, ResourceKind, SeverityLevel
from app.db.models.facilities import Resource
from app.llm.fake import FakeLLMClient
from app.schemas.agents.planning import PrioritizedZone
from app.schemas.agents.resources import ResourceAllocationInput
from app.schemas.events import EpicenterPoint, EventResponse
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession


def make_mock_resource(kind: ResourceKind, qty_total: int, qty_free: int) -> Resource:
    r = Resource(
        id=uuid.uuid4(),
        resource_kind=kind,
        label=f"{kind.value} Stock",
        quantity_total=qty_total,
        quantity_free=qty_free,
        depot_location=from_shape(Point(80.20, 13.00), srid=4326),
    )
    return r


@pytest.mark.asyncio
async def test_resource_coordination_never_exceeds_quantity_free_randomized():
    """Property test over randomized inventories asserting no resource is ever over-allocated."""
    agent = ResourceAllocationAgent()
    rng = random.Random(42)

    for trial in range(10):
        # Generate random stock for all resource kinds
        sample_resources = []
        initial_free_map = {}
        for kind in ResourceKind:
            total = rng.randint(5, 100)
            free = rng.randint(0, total)
            res_obj = make_mock_resource(kind, total, free)
            sample_resources.append(res_obj)
            initial_free_map[res_obj.id] = free

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = list(sample_resources)
        mock_db.execute.return_value = mock_result

        event = EventResponse(
            id=uuid.uuid4(),
            name=f"Trial Event {trial}",
            disaster_type=DisasterType.FLOOD,
            status="ACTIVE",  # type: ignore[arg-type]
            epicenter=EpicenterPoint(lon=80.20, lat=13.00),
            radius_m=5000,
            declared_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        zones = [
            PrioritizedZone(
                zone_label=f"Zone {i}",
                centroid=EpicenterPoint(lon=80.20 + i * 0.01, lat=13.00 + i * 0.01),
                priority=i,
                people_estimate=rng.randint(20, 200),
                accessibility="BLOCKED" if i == 1 else "ACCESSIBLE",
                rationale="Emergency response required",
            )
            for i in range(1, 4)
        ]

        input_data = ResourceAllocationInput(
            event=event,
            severity=SeverityLevel.HIGH,
            assessment_summary="Multi-zone flood impact",
            prioritized_zones=zones,
        )

        ctx = RunContext(
            event_id=event.id,
            agent_name=AgentName.RESOURCE_COORDINATION,
            db=mock_db,
            llm=FakeLLMClient(),
        )

        out = await agent.run(ctx, input_data)

        # Invariant 1: Allocated quantity per resource <= initial quantity_free
        alloc_per_resource: dict[uuid.UUID, int] = {}
        for a in out.allocations:
            alloc_per_resource[a.resource_id] = (
                alloc_per_resource.get(a.resource_id, 0) + a.quantity
            )

        for res_id, allocated in alloc_per_resource.items():
            assert (
                allocated <= initial_free_map[res_id]
            ), f"Resource {res_id} over-allocated: {allocated} > {initial_free_map[res_id]}"

        # Invariant 2: Total shortfalls requested == allocated + deficit
        for sf in out.shortfalls:
            assert sf.requested == sf.allocated + sf.deficit
            assert sf.deficit > 0
