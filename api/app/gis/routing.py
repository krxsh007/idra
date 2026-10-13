from __future__ import annotations

import math
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

        # Weight function for A*: one set lookup per edge (both directions precomputed)
        blocked_dir = blocked | {(v, u) for u, v in blocked}
        penalized_dir = penalized | {(v, u) for u, v in penalized}

        def weight_fn(u: int, v: int, d: dict[str, Any]) -> float | None:
            edge = (u, v)
            if edge in blocked_dir:
                return None  # networkx treats None as an impassable edge
            if edge in penalized_dir:
                return float(d.get("length", 100.0)) * penalty
            return float(d.get("length", 100.0))

        # A* with a straight-line lower bound returns the same path as Dijkstra (road length is
        # never shorter than the straight line, and penalties only add cost) but explores far
        # fewer nodes on a city-scale graph. The 0.5% margin keeps the planar distance a strict
        # lower bound of the true (haversine) distance across the study area.
        node_xy = road_graph_manager.node_xy()

        def straight_line_m(a: int, b: int) -> float:
            ax, ay = node_xy[a]
            bx, by = node_xy[b]
            return math.hypot(ax - bx, ay - by) * 0.995

        try:
            path_nodes = nx.astar_path(
                G,
                source=start_node,
                target=end_node,
                heuristic=straight_line_m,
                weight=weight_fn,
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        # Reconstruct path geometry (full street shape per edge) and aggregate statistics
        coords: list[list[float]] = []
        total_dist_m = 0.0
        duration_s = 0.0
        traverses_hazard = False
        blocked_edges_avoided = 0

        def node_coord(node_id: int) -> list[float]:
            ndata = G.nodes[node_id]
            return [
                float(ndata.get("lon", ndata.get("x", 0.0))),
                float(ndata.get("lat", ndata.get("y", 0.0))),
            ]

        coords.append(node_coord(path_nodes[0]))
        for prev_node, node_id in zip(path_nodes, path_nodes[1:], strict=False):
            edge_data = G.get_edge_data(prev_node, node_id, default={})
            geometry = edge_data.get("geometry")
            if geometry and len(geometry) >= 2:
                coords.extend([list(pt) for pt in geometry[1:]])
            else:
                coords.append(node_coord(node_id))

            edge_len = float(edge_data.get("length", 0.0))
            if edge_len <= 0.0:
                edge_len = haversine_distance_m(*node_coord(prev_node), *node_coord(node_id))
            total_dist_m += edge_len
            # Emergency transit at the road's speed (falls back to ~30 km/h)
            duration_s += float(edge_data.get("travel_s", edge_len / 8.33))

            if (prev_node, node_id) in penalized or (node_id, prev_node) in penalized:
                traverses_hazard = True

        # Check if any incident blocked edges were nearby / avoided
        if blocked:
            blocked_edges_avoided = len(blocked)

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
