from __future__ import annotations

import uuid

import structlog

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName
from app.gis.routing import hazard_router
from app.gis.spatial import get_blocked_edges
from app.schemas.agents.routing import (
    ComputedRouteItem,
    RouteGeometry,
    RoutingInput,
    RoutingOutput,
)
from app.schemas.events import EpicenterPoint

logger = structlog.get_logger(__name__)


class RoutingAgent(BaseAgent[RoutingInput, RoutingOutput]):
    """Computes hazard-avoiding evacuation and rescue corridors using the Chennai road graph."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.EVACUATION,
            response_schema=RoutingOutput,
        )

    async def _execute(
        self,
        ctx: RunContext,
        input_data: RoutingInput,
    ) -> RoutingOutput | AgentFailure:
        log = logger.bind(agent=self.agent_name.value, event_id=str(input_data.event.id))
        log.info("routing_computation_started")

        # 1. Fetch blocked edges from DB if session exists
        blocked_edges: set[tuple[int, int]] = set()
        if ctx.db is not None:
            db_blocked = await get_blocked_edges(ctx.db, input_data.event.id)
            blocked_edges = set(db_blocked)

        routes: list[ComputedRouteItem] = []
        unreachable: list[str] = []

        # Target shelter for civilian evacuation
        target_shelter = (
            input_data.recommended_shelters[0] if input_data.recommended_shelters else None
        )
        # Target hospital for casualty medical rescue
        target_hospital = (
            input_data.recommended_hospitals[0] if input_data.recommended_hospitals else None
        )

        # 2. Compute route from event epicenter to shelter
        if target_shelter:
            dest_pt = EpicenterPoint(
                lon=input_data.event.epicenter.lon + 0.01,
                lat=input_data.event.epicenter.lat + 0.01,
            )
            route_res = hazard_router.compute_route(
                origin_lon=input_data.event.epicenter.lon,
                origin_lat=input_data.event.epicenter.lat,
                dest_lon=dest_pt.lon,
                dest_lat=dest_pt.lat,
                blocked_edges=blocked_edges,
            )
            if route_res:
                routes.append(
                    ComputedRouteItem(
                        route_id=uuid.uuid4(),
                        origin=input_data.event.epicenter,
                        destination=dest_pt,
                        destination_facility_id=target_shelter.facility_id,
                        destination_name=target_shelter.name,
                        geometry=RouteGeometry(
                            type="LineString", coordinates=route_res["coordinates"]
                        ),
                        distance_m=route_res["distance_m"],
                        duration_s=route_res["duration_s"],
                        hazard_avoided=route_res["hazard_avoided"],
                        traverses_hazard=route_res["traverses_hazard"],
                        blocked_edges_avoided=route_res["blocked_edges_avoided"],
                        rationale=f"Primary civilian evacuation corridor to {target_shelter.name}.",
                    )
                )
            else:
                unreachable.append(f"Epicenter to shelter {target_shelter.name}")

        # 3. Compute routes from individual reported incident clusters to shelter/hospital
        for rep in input_data.reports[:3]:
            dest_facility = (
                target_hospital if rep.casualties_reported and target_hospital else target_shelter
            )
            if not dest_facility:
                continue

            dest_pt = EpicenterPoint(
                lon=rep.location.lon + 0.01,
                lat=rep.location.lat + 0.01,
            )
            res = hazard_router.compute_route(
                origin_lon=rep.location.lon,
                origin_lat=rep.location.lat,
                dest_lon=dest_pt.lon,
                dest_lat=dest_pt.lat,
                blocked_edges=blocked_edges,
            )
            if res:
                p_type = "Medical rescue" if rep.casualties_reported else "Evacuation"
                routes.append(
                    ComputedRouteItem(
                        route_id=uuid.uuid4(),
                        origin=rep.location,
                        destination=dest_pt,
                        destination_facility_id=dest_facility.facility_id,
                        destination_name=dest_facility.name,
                        geometry=RouteGeometry(type="LineString", coordinates=res["coordinates"]),
                        distance_m=res["distance_m"],
                        duration_s=res["duration_s"],
                        hazard_avoided=res["hazard_avoided"],
                        traverses_hazard=res["traverses_hazard"],
                        blocked_edges_avoided=res["blocked_edges_avoided"],
                        rationale=f"{p_type} route from incident {rep.id} to {dest_facility.name}.",
                    )
                )
            else:
                unreachable.append(f"Incident {rep.id} to {dest_facility.name}")

        summary = (
            f"Successfully computed {len(routes)} emergency corridors avoiding hazards. "
            f"{len(unreachable)} destination pairs unreachable due to impassable roadways."
        )

        return RoutingOutput(
            routes=routes,
            total_routes_computed=len(routes),
            unreachable_locations=unreachable,
            operational_summary=summary,
        )
