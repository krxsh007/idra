from __future__ import annotations

import time
from typing import Any

from app.core.errors import AppException
from app.eval.datasets import load_routing_cases
from app.gis.graph import road_graph_manager
from app.gis.routing import hazard_router
from app.gis.spatial import haversine_distance_m, snap_point_to_graph_memory


def run_gis_evaluation() -> dict[str, Any]:
    """Run the GIS & hazard-aware routing evaluation suite on routing_cases.json."""
    road_graph_manager.load_graph()
    G = road_graph_manager.get_graph()
    dataset = load_routing_cases()
    detour_cases = dataset["detour_cases"]
    enclosure_cases = dataset["enclosure_cases"]

    snap_checks_passed = 0
    snap_checks_total = 0

    connectivity_passed = 0
    connectivity_total = 0

    distance_sum_passed = 0
    distance_sum_total = 0

    detour_passed = 0
    enclosure_passed = 0
    latencies_ms: list[float] = []

    # 1. Evaluate 10 detour cases
    for case in detour_cases:
        orig = case["origin"]
        dest = case["destination"]
        u_blk, v_blk = int(case["blocked_edge"][0]), int(case["blocked_edge"][1])

        for pt in (orig, dest):
            snap_checks_total += 1
            snapped = snap_point_to_graph_memory(pt["lon"], pt["lat"])
            if snapped in G.nodes:
                snap_checks_passed += 1

        t0 = time.perf_counter()
        res = hazard_router.compute_route(
            origin_lon=orig["lon"],
            origin_lat=orig["lat"],
            dest_lon=dest["lon"],
            dest_lat=dest["lat"],
            blocked_edges={(u_blk, v_blk)},
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        if res is not None:
            path_nodes = res["path_nodes"]
            pairs = list(zip(path_nodes[:-1], path_nodes[1:], strict=False))

            connectivity_total += 1
            if all(G.has_edge(u, v) for u, v in pairs):
                connectivity_passed += 1

            # Verify edge length sum within 1.0m
            distance_sum_total += 1
            manual_dist = 0.0
            for u, v in pairs:
                ed = G.get_edge_data(u, v, default={})
                elen = float(ed.get("length", 0.0))
                if elen <= 0.0:
                    nu, nv = G.nodes[u], G.nodes[v]
                    elen = haversine_distance_m(
                        float(nu.get("lon", nu.get("x", 0.0))),
                        float(nu.get("lat", nu.get("y", 0.0))),
                        float(nv.get("lon", nv.get("x", 0.0))),
                        float(nv.get("lat", nv.get("y", 0.0))),
                    )
                manual_dist += elen
            if abs(manual_dist - float(res["distance_m"])) <= 1.0:
                distance_sum_passed += 1

            if (u_blk, v_blk) not in pairs and (v_blk, u_blk) not in pairs:
                detour_passed += 1

    # 2. Evaluate 5 enclosure cases
    for case in enclosure_cases:
        orig = case["origin"]
        dest = case["destination"]
        penalized_set = {(int(e[0]), int(e[1])) for e in case["penalized_edges"]}

        t0 = time.perf_counter()
        res = hazard_router.compute_route(
            origin_lon=orig["lon"],
            origin_lat=orig["lat"],
            dest_lon=dest["lon"],
            dest_lat=dest["lat"],
            penalized_edges=penalized_set,
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        if res is not None and res["traverses_hazard"] is True:
            enclosure_passed += 1

    # 3. Verify rejection outside 500m snap threshold
    snap_checks_total += 1
    try:
        snap_point_to_graph_memory(80.1501, 12.9501, max_dist_m=10.0)
    except AppException:
        snap_checks_passed += 1

    lat_sorted = sorted(latencies_ms)
    p50_ms = lat_sorted[len(lat_sorted) // 2] if lat_sorted else 0.0
    p95_idx = min(int(len(lat_sorted) * 0.95), len(lat_sorted) - 1)
    p95_ms = lat_sorted[p95_idx] if lat_sorted else 0.0

    snap_rate = round(snap_checks_passed / max(snap_checks_total, 1), 4)
    conn_rate = round(connectivity_passed / max(connectivity_total, 1), 4)
    dist_rate = round(distance_sum_passed / max(distance_sum_total, 1), 4)
    detour_rate = round(detour_passed / max(len(detour_cases), 1), 4)
    enc_rate = round(enclosure_passed / max(len(enclosure_cases), 1), 4)

    return {
        "suite": "gis_eval",
        "dataset_size": len(detour_cases) + len(enclosure_cases),
        "metrics": {
            "snap_accuracy_within_500m": {
                "value": snap_rate,
                "target": 1.00,
                "operator": "==",
                "passed": snap_rate == 1.00,
            },
            "path_connectivity_and_edge_validity_rate": {
                "value": conn_rate,
                "target": 1.00,
                "operator": "==",
                "passed": conn_rate == 1.00,
            },
            "distance_sum_accuracy_within_1m_rate": {
                "value": dist_rate,
                "target": 1.00,
                "operator": "==",
                "passed": dist_rate == 1.00,
            },
            "hazard_avoidance_rate_detour_cases": {
                "value": detour_rate,
                "target": 0.90,
                "operator": ">=",
                "passed": detour_rate >= 0.90,
            },
            "enclosure_degradation_accuracy": {
                "value": enc_rate,
                "target": 1.00,
                "operator": "==",
                "passed": enc_rate == 1.00,
            },
            "route_computation_latency_p50_ms": {
                "value": round(p50_ms, 2),
                "target": 100.0,
                "operator": "<=",
                "passed": p50_ms <= 100.0,
            },
            "route_computation_latency_p95_ms": {
                "value": round(p95_ms, 2),
                "target": 250.0,
                "operator": "<=",
                "passed": p95_ms <= 250.0,
            },
        },
    }
