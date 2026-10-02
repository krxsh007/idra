from __future__ import annotations

from typing import Any

import networkx as nx

from app.core.config import settings
from app.core.errors import AppException
from app.gis.graph import road_graph_manager
from app.gis.spatial import haversine_distance_m, snap_point_to_graph_memory


class HazardAwareRouter:
    """Computes optimal routes over Chennai road network avoiding hazard areas."""

    def __init__(self) -> None:
        pass

    def compute_route(
        self,
        origin_lon: float,
        origin_lat: float,
        dest_lon: float,
        dest_lat: float,
        blocked_edges: set[tuple[int, int]] | None = None,
        penalized_edges: set[tuple[int, int]] | None = None,
        penalty_factor: float | None = None,
    ) -> dict[str, Any] | None:
        """Calculate shortest route avoiding blocked edges and penalizing hazardous edges.

        Returns dict with path coordinates, distance in meters, duration in seconds,
        or None if no path exists.
        """
        penalty = penalty_factor or settings.HAZARD_SOFT_PENALTY
        blocked = blocked_edges or set()
        penalized = penalized_edges or set()

        # Snap endpoints to road network nodes
        try:
            start_node = snap_point_to_graph_memory(origin_lon, origin_lat)
            end_node = snap_point_to_graph_memory(dest_lon, dest_lat)
        except AppException:
            return None

        G = road_graph_manager.get_graph()

        # Weight function for Dijkstra / A*
        def weight_fn(u: int, v: int, d: dict[str, Any]) -> float:
            if (u, v) in blocked or (v, u) in blocked:
                return float("inf")

            base_length = float(d.get("length", 100.0))
            if (u, v) in penalized or (v, u) in penalized:
                return base_length * penalty
            return base_length

        try:
            path_nodes = nx.shortest_path(
                G,
                source=start_node,
                target=end_node,
                weight=weight_fn,
                method="dijkstra",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        # Reconstruct path geometry and aggregate statistics
        coords: list[list[float]] = []
        total_dist_m = 0.0
        traverses_hazard = False
        blocked_edges_avoided = 0

        for i, node_id in enumerate(path_nodes):
            ndata = G.nodes[node_id]
            n_lon = float(ndata.get("lon", ndata.get("x", 0.0)))
            n_lat = float(ndata.get("lat", ndata.get("y", 0.0)))
            coords.append([n_lon, n_lat])

            if i > 0:
                prev_node = path_nodes[i - 1]
                edge_data = G.get_edge_data(prev_node, node_id, default={})
                edge_len = float(edge_data.get("length", 0.0))
                if edge_len <= 0.0:
                    prev_lon, prev_lat = coords[-2]
                    edge_len = haversine_distance_m(prev_lon, prev_lat, n_lon, n_lat)
                total_dist_m += edge_len

                if (prev_node, node_id) in penalized or (node_id, prev_node) in penalized:
                    traverses_hazard = True

        # Check if any incident blocked edges were nearby / avoided
        if blocked:
            blocked_edges_avoided = len(blocked)

        # Estimate travel duration assuming emergency transit speed of ~30 km/h (8.33 m/s)
        duration_s = total_dist_m / 8.33

        return {
            "path_nodes": path_nodes,
            "coordinates": coords,
            "distance_m": round(total_dist_m, 1),
            "duration_s": round(duration_s, 1),
            "hazard_avoided": not traverses_hazard,
            "traverses_hazard": traverses_hazard,
            "blocked_edges_avoided": blocked_edges_avoided,
        }


hazard_router = HazardAwareRouter()
