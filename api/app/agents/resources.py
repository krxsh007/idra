from __future__ import annotations

import math

import structlog
from geoalchemy2.shape import to_shape
from sqlalchemy import select

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, ResourceKind, SeverityLevel
from app.db.models.facilities import Resource
from app.gis.spatial import haversine_distance_m
from app.schemas.agents.resources import (
    AllocatedItem,
    ResourceAllocationInput,
    ResourceAllocationOutput,
    ShortfallItem,
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
                shortfalls=[],
                total_items_allocated=0,
                total_allocated=0,
                shortages_identified=["No active database session to query resource depots."],
                operational_summary="Resource allocation could not connect to inventory depot.",
                justification="Database session unavailable.",
            )

        # 1. Query available resources from depot database
        stmt = select(Resource).where(Resource.quantity_free > 0)
        res = await ctx.db.execute(stmt)
        available_resources = list(res.scalars().all())

        allocations: list[AllocatedItem] = []
        shortfalls: list[ShortfallItem] = []
        shortages: list[str] = []

        # 2. Derive requirements using the PRD 8.7 requirement rule table
        # Structure: list of (kind, requested_qty, priority, rationale, zone_label, target_point)
        requirements: list[tuple[ResourceKind, int, int, str, str, EpicenterPoint]] = []

        if input_data.prioritized_zones:
            for zone in input_data.prioritized_zones:
                pop = max(1, zone.people_estimate)
                target_pt = zone.centroid
                z_label = zone.zone_label
                prio = zone.priority

                # Rule 1: accessibility BLOCKED -> 1 RESCUE_BOAT per 25 people, 1 RESCUE_TEAM per 50
                if zone.accessibility == "BLOCKED":
                    boats_req = max(1, math.ceil(pop / 25))
                    teams_req = max(1, math.ceil(pop / 50))
                    requirements.append(
                        (
                            ResourceKind.RESCUE_BOAT,
                            boats_req,
                            prio,
                            f"Impassable zone {z_label}: boat extraction for {pop} residents.",
                            z_label,
                            target_pt,
                        )
                    )
                    requirements.append(
                        (
                            ResourceKind.RESCUE_TEAM,
                            teams_req,
                            prio,
                            (
                                f"Impassable zone {z_label}: specialized water rescue team "
                                f"for {pop} residents."
                            ),
                            z_label,
                            target_pt,
                        )
                    )

                # Rule 2: casualties in zone -> 1 AMBULANCE per 5 casualties,
                # 1 MEDICAL_TEAM per 30 people
                # We check if rationale or telemetry signals casualties
                has_cas = "casualt" in zone.rationale.lower() or (
                    input_data.casualties_reported and prio == 1
                )
                if has_cas:
                    amb_req = max(1, min(10, math.ceil(pop / 20)))
                    med_req = max(1, math.ceil(pop / 30))
                    requirements.append(
                        (
                            ResourceKind.AMBULANCE,
                            amb_req,
                            prio,
                            f"Casualties in {z_label}: medical transport dispatched.",
                            z_label,
                            target_pt,
                        )
                    )
                    requirements.append(
                        (
                            ResourceKind.MEDICAL_TEAM,
                            med_req,
                            prio,
                            f"Casualties in {z_label}: onsite trauma care and triage.",
                            z_label,
                            target_pt,
                        )
                    )

                # Rule 3: any zone -> 1 FOOD_KIT per person (capped batch 50),
                # 1 BLANKET_KIT, 1 WATER_TANKER per 500
                food_req = min(pop, 50)
                blanket_req = min(pop, 50)
                water_req = max(1, math.ceil(pop / 500))
                requirements.append(
                    (
                        ResourceKind.FOOD_KIT,
                        food_req,
                        min(5, prio + 1),
                        f"Provisions for {z_label}.",
                        z_label,
                        target_pt,
                    )
                )
                requirements.append(
                    (
                        ResourceKind.BLANKET_KIT,
                        blanket_req,
                        min(5, prio + 1),
                        f"Bedding kits for {z_label}.",
                        z_label,
                        target_pt,
                    )
                )
                requirements.append(
                    (
                        ResourceKind.WATER_TANKER,
                        water_req,
                        min(5, prio + 1),
                        f"Potable water supply for {z_label}.",
                        z_label,
                        target_pt,
                    )
                )

                # Rule 4: severity SEVERE -> plus 1 GENERATOR per zone
                if input_data.severity == SeverityLevel.SEVERE:
                    requirements.append(
                        (
                            ResourceKind.GENERATOR,
                            1,
                            prio,
                            f"Backup power generation for severe sector {z_label}.",
                            z_label,
                            target_pt,
                        )
                    )
        else:
            # Fallback when no prioritized zones provided: allocate to general event epicenter
            ep = EpicenterPoint(
                lon=input_data.event.epicenter.lon,
                lat=input_data.event.epicenter.lat,
            )
            z_label = f"Impact Sector - {input_data.event.name}"
            if input_data.casualties_reported:
                requirements.append(
                    (
                        ResourceKind.AMBULANCE,
                        4,
                        1,
                        "Dispatched for verified casualties and urgent triage.",
                        z_label,
                        ep,
                    )
                )
                requirements.append(
                    (
                        ResourceKind.MEDICAL_TEAM,
                        2,
                        1,
                        "Dispatched for onsite trauma triage.",
                        z_label,
                        ep,
                    )
                )
            requirements.append(
                (
                    ResourceKind.RESCUE_BOAT,
                    3,
                    2,
                    "Dispatched for water rescue and evacuation.",
                    z_label,
                    ep,
                )
            )
            requirements.append(
                (
                    ResourceKind.FOOD_KIT,
                    50,
                    3,
                    "Provisions for affected residents.",
                    z_label,
                    ep,
                )
            )
            requirements.append(
                (
                    ResourceKind.WATER_TANKER,
                    2,
                    3,
                    "Potable water supply.",
                    z_label,
                    ep,
                )
            )

        # 3. Sort requirements by priority (ascending 1..5)
        requirements.sort(key=lambda r: r[2])

        # 4. Greedy Allocation with depot distance sorting and run-local ledger
        free_ledger = {r.id: r.quantity_free for r in available_resources}

        for kind, req_qty, prio, rat, z_label, target_loc in requirements:
            matching = [
                r
                for r in available_resources
                if r.resource_kind == kind and free_ledger.get(r.id, 0) > 0
            ]

            # Calculate depot distance for each matching resource
            def get_depot_dist(res_obj: Resource, loc: EpicenterPoint = target_loc) -> float:
                try:
                    shape_geom = to_shape(res_obj.depot_location)
                    return haversine_distance_m(loc.lon, loc.lat, shape_geom.x, shape_geom.y)
                except Exception:
                    return 0.0

            matching.sort(key=get_depot_dist)

            allocated_for_req = 0
            remaining_req = req_qty

            for depot_res in matching:
                if remaining_req <= 0:
                    break
                avail_free = free_ledger.get(depot_res.id, 0)
                if avail_free <= 0:
                    continue

                alloc_qty = min(remaining_req, avail_free)
                dist_m = get_depot_dist(depot_res)

                allocations.append(
                    AllocatedItem(
                        resource_id=depot_res.id,
                        resource_kind=depot_res.resource_kind,
                        label=depot_res.label,
                        quantity=alloc_qty,
                        depot_facility_id=depot_res.depot_facility_id,
                        target_zone_label=z_label,
                        target_location=target_loc,
                        depot_distance_m=dist_m,
                        priority=prio,
                        rationale=rat,
                    )
                )

                free_ledger[depot_res.id] = avail_free - alloc_qty
                allocated_for_req += alloc_qty
                remaining_req -= alloc_qty

            if allocated_for_req < req_qty:
                deficit = req_qty - allocated_for_req
                shortfalls.append(
                    ShortfallItem(
                        resource_kind=kind,
                        zone_label=z_label,
                        requested=req_qty,
                        allocated=allocated_for_req,
                        deficit=deficit,
                    )
                )
                if allocated_for_req == 0:
                    shortages.append(
                        f"Insufficient stock for {kind.value}: "
                        f"requested {req_qty}, available 0 in {z_label}"
                    )
                else:
                    shortages.append(
                        f"Partial allocation for {kind.value}: requested {req_qty}, "
                        f"allocated {allocated_for_req} in {z_label}"
                    )

        total_alloc = sum(a.quantity for a in allocations)
        summary = (
            f"Allocated {len(allocations)} batches totaling {total_alloc} resources. "
            f"{len(shortfalls)} deficits identified across sectors."
        )

        return ResourceAllocationOutput(
            allocations=allocations,
            shortfalls=shortfalls,
            total_items_allocated=total_alloc,
            total_allocated=total_alloc,
            shortages_identified=shortages,
            operational_summary=summary,
            justification=(
                f"Greedy rule-based allocation across "
                f"{len(input_data.prioritized_zones)} prioritized sectors."
            ),
        )
