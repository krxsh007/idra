from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from app.gis.spatial import haversine_distance_m
from app.schemas.hazards import HazardZoneResponse
from app.schemas.reports import ReportResponse


@dataclass
class ClusterResult:
    cluster_id: int
    centroid_lon: float
    centroid_lat: float
    reports: list[ReportResponse]
    people_estimate: int
    has_casualties: bool
    accessibility: str  # "ACCESSIBLE" | "CONSTRAINED" | "BLOCKED"


def distance_point_to_polygon_m(
    lon: float, lat: float, poly_geom: dict[str, Any]
) -> tuple[bool, float]:
    """Check if point is inside polygon and compute minimum distance in meters to polygon."""
    poly = shape(poly_geom)
    pt = Point(lon, lat)

    if poly.contains(pt) or poly.covers(pt):
        return True, 0.0

    # Nearest point on polygon boundary
    p1, p2 = nearest_points(pt, poly)
    dist_m = haversine_distance_m(p1.x, p1.y, p2.x, p2.y)
    return False, dist_m


def classify_cluster_accessibility(
    centroid_lon: float,
    centroid_lat: float,
    hazard_zones: list[HazardZoneResponse],
) -> str:
    """Deterministically classify cluster accessibility against impassable hazard polygons.

    - BLOCKED: Centroid is inside an impassable hazard zone
    - CONSTRAINED: Centroid is within 300m of an impassable hazard zone
    - ACCESSIBLE: Otherwise
    """
    impassable_zones = [hz for hz in hazard_zones if hz.is_impassable]
    if not impassable_zones:
        return "ACCESSIBLE"

    min_dist_to_impassable = float("inf")

    for hz in impassable_zones:
        geom_dict = hz.geometry.model_dump()
        is_inside, dist_m = distance_point_to_polygon_m(centroid_lon, centroid_lat, geom_dict)
        if is_inside:
            return "BLOCKED"
        if dist_m < min_dist_to_impassable:
            min_dist_to_impassable = dist_m

    if min_dist_to_impassable <= 300.0:
        return "CONSTRAINED"
    return "ACCESSIBLE"


def cluster_incident_reports(
    reports: list[ReportResponse],
    hazard_zones: list[HazardZoneResponse],
    eps_m: float = 500.0,
    min_points: int = 2,
) -> list[ClusterResult]:
    """Cluster incident reports using spatial distance (eps=500m, min_points=2).

    Uses Haversine distance graph clustering with DBSCAN semantics.
    Noise reports that do not meet min_points form individual clusters if there are
    no multi-point clusters, or are attached to nearest cluster within eps_m.
    """
    if not reports:
        return []

    n = len(reports)
    # 1. Build adjacency list of neighbors within eps_m
    neighbors: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            d = haversine_distance_m(
                reports[i].location.lon,
                reports[i].location.lat,
                reports[j].location.lon,
                reports[j].location.lat,
            )
            if d <= eps_m:
                neighbors[i].append(j)
                if i != j:
                    neighbors[j].append(i)

    # 2. DBSCAN clustering
    visited = [False] * n
    cluster_labels = [-1] * n
    current_cluster = 0

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True

        if len(neighbors[i]) >= min_points:
            # Core point: expand cluster
            cluster_labels[i] = current_cluster
            queue = [idx for idx in neighbors[i] if idx != i]

            while queue:
                neighbor_idx = queue.pop(0)
                if not visited[neighbor_idx]:
                    visited[neighbor_idx] = True
                    if len(neighbors[neighbor_idx]) >= min_points:
                        queue.extend([q for q in neighbors[neighbor_idx] if q not in queue])
                if cluster_labels[neighbor_idx] == -1:
                    cluster_labels[neighbor_idx] = current_cluster

            current_cluster += 1

    # 3. Handle unassigned/noise points
    for i in range(n):
        if cluster_labels[i] == -1:
            # If no clusters exist at all, or point is isolated, assign own cluster
            cluster_labels[i] = current_cluster
            current_cluster += 1

    # 4. Group reports by cluster label
    clusters_map: dict[int, list[ReportResponse]] = {}
    for i, cid in enumerate(cluster_labels):
        clusters_map.setdefault(cid, []).append(reports[i])

    # 5. Build ClusterResult objects
    results: list[ClusterResult] = []
    for cid, c_reports in clusters_map.items():
        avg_lon = sum(r.location.lon for r in c_reports) / len(c_reports)
        avg_lat = sum(r.location.lat for r in c_reports) / len(c_reports)
        people = sum(r.people_affected or 5 for r in c_reports)
        cas = any(r.casualties_reported for r in c_reports)
        access = classify_cluster_accessibility(avg_lon, avg_lat, hazard_zones)

        results.append(
            ClusterResult(
                cluster_id=cid,
                centroid_lon=avg_lon,
                centroid_lat=avg_lat,
                reports=c_reports,
                people_estimate=people,
                has_casualties=cas,
                accessibility=access,
            )
        )

    return results
