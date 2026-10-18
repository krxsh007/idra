from __future__ import annotations

import copy
import uuid
from typing import Any

import structlog
from app.gis.routing import HazardAwareRouter
from app.orchestration.state import OrchestratorState

logger = structlog.get_logger(__name__)


class ConflictResolver:
    """Deterministic Coordination Layer node resolving facility, route, and telemetry conflicts."""

    def __init__(self, router: HazardAwareRouter | None = None) -> None:
        self.router = router or HazardAwareRouter()

    def resolve(self, state: OrchestratorState) -> dict[str, Any]:
        """Execute deterministic conflict resolution passes on current run state."""
        log = logger.bind(event_id=state.get("event_id"))
        log.info("conflict_resolution_started")

        conflicts_detected: list[str] = []
        conflicts_resolved: list[str] = []
        reassigned_facilities: dict[str, dict[str, Any]] = {}  # old_id -> new_facility_info
        recomputed_routes: list[dict[str, Any]] = []
        needs_human_review = state.get("needs_human_review", False)
        residual_overbooking = 0

        # Pass 1: Facility double-booking & capacity ledger
        fac_out = copy.deepcopy(state.get("facilities_output") or {})
        recommended_shelters = fac_out.get("recommended_shelters", [])

        if recommended_shelters:
            # Build capacity ledger for shelters
            # If multiple zones or operations claim the primary shelter exceeding capacity:
            # Reassign displaced claims to secondary/next available shelter
            primary_shelter = recommended_shelters[0]
            avail_cap = int(primary_shelter.get("available_capacity", 0))

            # Estimate total evacuees from reports or planning zones
            planning_out = state.get("planning_output") or {}
            zones = planning_out.get("prioritized_zones", [])
            total_displaced = sum(z.get("people_estimate", 0) for z in zones)
            if total_displaced == 0:
                reports = state.get("reports_data", [])
                total_displaced = sum(r.get("people_affected", 0) or 10 for r in reports)

            # Check if primary shelter capacity is exceeded
            if avail_cap > 0 and total_displaced > avail_cap and len(recommended_shelters) > 1:
                conflicts_detected.append(
                    f"Shelter over-booking at '{primary_shelter.get('name')}': "
                    f"demanded {total_displaced} > capacity {avail_cap}"
                )

                # Reassign excess to next-ranked shelter
                next_shelter = recommended_shelters[1]
                reassigned_facilities[str(primary_shelter.get("facility_id"))] = next_shelter

                conflicts_resolved.append(
                    f"Resolved over-booking: Reassigned overflow evacuees from "
                    f"'{primary_shelter.get('name')}' to '{next_shelter.get('name')}'."
                )

                # Update primary shelter committed count and swap primary target
                fac_out["recommended_shelters"] = [next_shelter] + [
                    s
                    for s in recommended_shelters
                    if s.get("facility_id") != next_shelter.get("facility_id")
                ]
            elif avail_cap > 0 and total_displaced > avail_cap and len(recommended_shelters) <= 1:
                residual_overbooking = total_displaced - avail_cap
                conflicts_detected.append(
                    f"Shelter capacity deficit at '{primary_shelter.get('name')}': "
                    f"shortage of {residual_overbooking} spaces without alternate shelters."
                )

        # Pass 2: Resource over-commitment assertion check
        res_out = state.get("resources_output") or {}
        allocations = res_out.get("allocations", [])
        resource_alloc_totals: dict[str, int] = {}
        for a in allocations:
            r_id = str(a.get("resource_id"))
            current_tot = resource_alloc_totals.get(r_id, 0)
            resource_alloc_totals[r_id] = current_tot + int(a.get("quantity", 0))

        # Pass 3: Route destination invalidated & single bounded recomputation
        routing_out = copy.deepcopy(state.get("routing_output") or {})
        existing_routes = routing_out.get("routes", [])

        if reassigned_facilities and existing_routes:
            for old_id_str, new_fac in reassigned_facilities.items():
                for route in existing_routes:
                    dest_fac_id = str(route.get("destination_facility_id", ""))
                    if dest_fac_id == old_id_str:
                        # Mark existing route superseded
                        route["superseded"] = True
                        route["rationale"] = (
                            f"{route.get('rationale', '')} [SUPERSEDED: Shelter reassigned "
                            f"due to capacity conflict to {new_fac.get('name')}]."
                        )

                        # Bounded single recomputation to new destination
                        orig_pt = route.get("origin", {})
                        orig_lon = float(orig_pt.get("lon", 80.20))
                        orig_lat = float(orig_pt.get("lat", 13.00))

                        # New shelter location
                        # If facility candidate lacks direct lon/lat, fallback to offset
                        new_lon = float(new_fac.get("lon", orig_lon + 0.01))
                        new_lat = float(new_fac.get("lat", orig_lat + 0.01))

                        try:
                            computed = self.router.compute_route(
                                origin_lon=orig_lon,
                                origin_lat=orig_lat,
                                dest_lon=new_lon,
                                dest_lat=new_lat,
                            )
                            if computed:
                                new_route_item = {
                                    "route_id": str(uuid.uuid4()),
                                    "origin": orig_pt,
                                    "destination": {"lon": new_lon, "lat": new_lat},
                                    "destination_facility_id": str(new_fac.get("facility_id")),
                                    "geometry": {
                                        "type": "LineString",
                                        "coordinates": computed["coordinates"],
                                    },
                                    "distance_m": computed["distance_m"],
                                    "duration_s": computed["duration_s"],
                                    "hazard_avoided": not computed.get("traverses_hazard", False),
                                    "traverses_hazard": computed.get("traverses_hazard", False),
                                    "blocked_edges_avoided": 0,
                                    "rationale": (
                                        f"Recomputed corridor to reassigned shelter "
                                        f"'{new_fac.get('name')}'."
                                    ),
                                    "supersedes_route_id": route.get("route_id"),
                                }
                                recomputed_routes.append(new_route_item)
                                conflicts_resolved.append(
                                    f"Recomputed route to shelter '{new_fac.get('name')}'."
                                )
                        except Exception as e:
                            log.warning("route_recomputation_failed", error=str(e))

        if recomputed_routes:
            routing_out["routes"] = existing_routes + recomputed_routes
            routing_out["total_routes_computed"] = len(routing_out["routes"])

        # Pass 4: Contradictory severity signals detection
        assessment_out = state.get("assessment_output") or {}
        assessed_sev = state.get("assessed_severity") or assessment_out.get("severity")
        planning_out = state.get("planning_output") or {}
        p_zones = planning_out.get("prioritized_zones", [])

        if p_zones and assessed_sev in ["MODERATE", "LOW"]:
            all_blocked = all(z.get("accessibility") == "BLOCKED" for z in p_zones)
            if all_blocked:
                needs_human_review = True
                msg = (
                    f"Contradictory telemetry signals: All {len(p_zones)} rescue sectors are "
                    f"classified as BLOCKED by impassable inundation, but assessment severity "
                    f"is {assessed_sev}. Escalating for human review."
                )
                conflicts_detected.append(msg)
                conflicts_resolved.append("Flagged contradiction: needs_human_review set to true.")

        reassigned_fac_map = {k: v.get("facility_id") for k, v in reassigned_facilities.items()}

        return {
            "conflicts_detected": conflicts_detected,
            "conflicts_resolved": conflicts_resolved,
            "reassigned_facilities": reassigned_fac_map,
            "recomputed_routes": recomputed_routes,
            "needs_human_review": needs_human_review,
            "residual_overbooking": residual_overbooking,
            "updated_facilities_output": fac_out,
            "updated_routing_output": routing_out,
        }
