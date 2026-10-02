from __future__ import annotations

import structlog
from sqlalchemy import select

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, ResourceKind
from app.db.models.facilities import Resource
from app.schemas.agents.resources import (
    AllocatedItem,
    ResourceAllocationInput,
    ResourceAllocationOutput,
)
from app.schemas.events import EpicenterPoint

logger = structlog.get_logger(__name__)


class ResourceAllocationAgent(BaseAgent[ResourceAllocationInput, ResourceAllocationOutput]):
    """Allocates emergency resources to incident sectors based on need and free capacity."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.RESOURCE_COORDINATION,
            response_schema=ResourceAllocationOutput,
        )

    async def _execute(
        self,
        ctx: RunContext,
        input_data: ResourceAllocationInput,
    ) -> ResourceAllocationOutput | AgentFailure:
        log = logger.bind(agent=self.agent_name.value, event_id=str(input_data.event.id))
        log.info("resource_allocation_started")

        if ctx.db is None:
            return ResourceAllocationOutput(
                allocations=[],
                total_items_allocated=0,
                shortages_identified=["No active database session to query resource depots."],
                operational_summary="Resource allocation could not connect to inventory depot.",
            )

        # 1. Query available resources from depot database
        stmt = select(Resource).where(Resource.quantity_free > 0)
        res = await ctx.db.execute(stmt)
        available_resources = list(res.scalars().all())

        allocations: list[AllocatedItem] = []
        shortages: list[str] = []

        # Triage needed resources based on disaster telemetry (kind, qty, prio, rationale)
        needed_kinds: list[tuple[ResourceKind, int, int, str]] = []
        if input_data.casualties_reported:
            needed_kinds.append(
                (ResourceKind.AMBULANCE, 4, 1, "Dispatched for casualties and urgent triage.")
            )
            needed_kinds.append(
                (ResourceKind.MEDICAL_TEAM, 2, 1, "Dispatched for onsite trauma triage.")
            )

        # Flood / water search & rescue
        needed_kinds.append(
            (ResourceKind.RESCUE_BOAT, 3, 2, "Dispatched for high water evacuation and rescue.")
        )
        needed_kinds.append(
            (ResourceKind.FOOD_KIT, 50, 3, "Essential provisions for inundated clusters.")
        )
        needed_kinds.append((ResourceKind.WATER_TANKER, 2, 3, "Potable drinking water supply."))

        for kind, req_qty, prio, rat in needed_kinds:
            matching = [
                r for r in available_resources if r.resource_kind == kind and r.quantity_free > 0
            ]
            if not matching:
                shortages.append(
                    f"Insufficient stock for {kind.value}: requested {req_qty}, available 0"
                )
                continue

            # Pick first available stock and clamp allocation strictly to quantity_free
            chosen_res = matching[0]
            allocated_qty = min(req_qty, chosen_res.quantity_free)

            target_pt = EpicenterPoint(
                lon=input_data.event.epicenter.lon,
                lat=input_data.event.epicenter.lat,
            )

            allocations.append(
                AllocatedItem(
                    resource_id=chosen_res.id,
                    resource_kind=chosen_res.resource_kind,
                    label=chosen_res.label,
                    quantity=allocated_qty,
                    depot_facility_id=chosen_res.depot_facility_id,
                    target_zone_label=f"Impact Zone around {input_data.event.name}",
                    target_location=target_pt,
                    priority=prio,
                    rationale=rat,
                )
            )

            # Decrement free quantity locally in memory during allocation calculation
            chosen_res.quantity_free -= allocated_qty

            if allocated_qty < req_qty:
                shortages.append(
                    f"Partial allocation for {kind.value}: req {req_qty}, alloc {allocated_qty}"
                )

        total_alloc = sum(a.quantity for a in allocations)
        summary = (
            f"Allocated {len(allocations)} resource units totaling {total_alloc} items. "
            f"{len(shortages)} potential inventory shortages identified."
        )

        return ResourceAllocationOutput(
            allocations=allocations,
            total_items_allocated=total_alloc,
            shortages_identified=shortages,
            operational_summary=summary,
        )
