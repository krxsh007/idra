from __future__ import annotations

import uuid
from typing import Any

import structlog
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, Polygon

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, AgentStatus
from app.db.models.facilities import Facility
from app.gis.graph import road_graph_manager
from app.gis.routing import hazard_router
from app.schemas.agents.routing import (
    ComputedRouteItem,
    RouteGeometry,
    RoutingInput,
    RoutingOutput,
)
from app.schemas.events import EpicenterPoint

logger = structlog.get_logger(__name__)


async def _facility_point(
    ctx: RunContext, facility_id: uuid.UUID, fallback: EpicenterPoint
) -> EpicenterPoint:
    """Return the facility location, or a nearby fallback point when no database is available."""
    if ctx.db is None:
        return fallback
    try:
        fac = await ctx.db.get(Facility, facility_id)
        if fac is not None and fac.location is not None:
            pt = to_shape(fac.location)
            return EpicenterPoint(lon=pt.x, lat=pt.y)
    except Exception as e:  # pragma: no cover - defensive, falls back to the legacy behaviour
        logger.warning("facility_location_lookup_failed", error=str(e))
    return fallback


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

        if road_graph_manager._unavailable:
            return AgentFailure(
                code="ROAD_GRAPH_UNAVAILABLE",
                message="Road network graph is not loaded or unavailable.",
                status=AgentStatus.FAILED,
            )

        # 1. Classify road segments against this event's hazard polygons (in memory, using the
        #    street geometry): impassable zones close roads, other zones are heavily penalised.
        zones = []
        for hz in input_data.hazard_zones:
            rings = hz.geometry.coordinates
            polygon = Polygon(rings[0], rings[1:])
            zones.append((hz, polygon, road_graph_manager.edges_intersecting(polygon)))

        def plan_route(origin: EpicenterPoint, dest: EpicenterPoint) -> dict[str, Any] | None:
            o_pt, d_pt = Point(origin.lon, origin.lat), Point(dest.lon, dest.lat)
            # A zone the route starts or ends in can't be avoided: leave it by the shortest way
            # (penalised, not closed) and don't count it against "hazard avoided".
            endpoint_zones = {
                hz.id for hz, poly, _ in zones if poly.covers(o_pt) or poly.covers(d_pt)
            }
            blocked: set[tuple[int, int]] = set()
            penalized: set[tuple[int, int]] = set()
            avoidable: set[tuple[int, int]] = set()
            for hz, _, edges in zones:
                if hz.id in endpoint_zones:
                    penalized |= edges
                elif hz.is_impassable:
                    blocked |= edges
                else:
                    penalized |= edges
                    avoidable |= edges

            res = hazard_router.compute_route(
                origin_lon=origin.lon,
                origin_lat=origin.lat,
                dest_lon=dest.lon,
                dest_lat=dest.lat,
                blocked_edges=blocked,
                penalized_edges=penalized,
            )
            if res is None:
                return None
            used = set(zip(res["path_nodes"], res["path_nodes"][1:], strict=False))
            res["traverses_hazard"] = bool(used & avoidable)
            res["hazard_avoided"] = not res["traverses_hazard"]
            res["starts_in_hazard"] = any(poly.covers(o_pt) for _, poly, _ in zones)
            res["blocked_edges_avoided"] = len(blocked) // 2  # two-way streets closed
            return res

        def describe(base: str, res: dict[str, Any]) -> str:
            if res["starts_in_hazard"]:
                base += " Starts inside a hazard zone and takes the shortest way out."
            if res["traverses_hazard"]:
                base += " No hazard-free alternative: passes through another hazard zone."
            return base

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
            dest_pt = await _facility_point(
                ctx,
                target_shelter.facility_id,
                EpicenterPoint(
                    lon=input_data.event.epicenter.lon + 0.01,
                    lat=input_data.event.epicenter.lat + 0.01,
                ),
            )
            route_res = plan_route(input_data.event.epicenter, dest_pt)
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
                        starts_in_hazard=route_res["starts_in_hazard"],
                        blocked_edges_avoided=route_res["blocked_edges_avoided"],
                        rationale=describe(
                            f"Primary civilian evacuation corridor to {target_shelter.name}.",
                            route_res,
                        ),
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

            dest_pt = await _facility_point(
                ctx,
                dest_facility.facility_id,
                EpicenterPoint(lon=rep.location.lon + 0.01, lat=rep.location.lat + 0.01),
            )
            res = plan_route(rep.location, dest_pt)
            if res:
                p_type = "Medical rescue" if rep.casualties_reported else "Evacuation"
                if rep.casualties_reported:
                    incident_detail = "casualties reported"
                elif rep.people_affected:
                    incident_detail = f"{rep.people_affected} people affected"
                else:
                    incident_detail = "no casualties reported"
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
                        starts_in_hazard=res["starts_in_hazard"],
                        blocked_edges_avoided=res["blocked_edges_avoided"],
                        rationale=describe(
                            f"{p_type} route from a reported incident ({incident_detail}) "
                            f"to {dest_facility.name}.",
                            res,
                        ),
                    )
                )
            else:
                unreachable.append(f"Incident {rep.id} to {dest_facility.name}")

        avoided = sum(1 for r in routes if r.hazard_avoided)
        summary = (
            f"Computed {len(routes)} emergency corridors on the OpenStreetMap road network; "
            f"{avoided} avoid all hazard zones they don't start in. "
            f"{len(unreachable)} destination pairs unreachable due to impassable roadways."
        )

        return RoutingOutput(
            routes=routes,
            total_routes_computed=len(routes),
            unreachable_locations=unreachable,
            operational_summary=summary,
        )
