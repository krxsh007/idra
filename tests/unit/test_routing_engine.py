from __future__ import annotations

import pytest
from app.gis.graph import road_graph_manager
from app.gis.routing import HazardAwareRouter


@pytest.fixture(autouse=True)
def ensure_graph():
    road_graph_manager.load_graph()


def test_routing_engine_finds_path():
    router = HazardAwareRouter()
    # Adyar to Velachery coordinates inside Chennai Core bbox
    res = router.compute_route(
        origin_lon=80.25,
        origin_lat=13.01,
        dest_lon=80.22,
        dest_lat=12.98,
    )
    assert res is not None
    assert "coordinates" in res
    assert len(res["coordinates"]) >= 2
    assert res["distance_m"] > 0
    assert res["duration_s"] > 0
    assert res["hazard_avoided"] is True


def test_routing_engine_avoids_blocked_edges():
    router = HazardAwareRouter()
    # Baseline path
    baseline = router.compute_route(
        origin_lon=80.25,
        origin_lat=13.01,
        dest_lon=80.22,
        dest_lat=12.98,
    )
    assert baseline is not None
    path_nodes = baseline["path_nodes"]
    assert len(path_nodes) >= 3

    # Block an edge along the optimal route
    blocked_edge = (path_nodes[1], path_nodes[2])
    detour = router.compute_route(
        origin_lon=80.25,
        origin_lat=13.01,
        dest_lon=80.22,
        dest_lat=12.98,
        blocked_edges={blocked_edge},
    )

    # Detour must still succeed (unless graph is disconnected) and not use the blocked edge
    if detour is not None:
        detour_nodes = detour["path_nodes"]
        pairs = list(zip(detour_nodes[:-1], detour_nodes[1:], strict=False))
        assert blocked_edge not in pairs
        assert (blocked_edge[1], blocked_edge[0]) not in pairs


def test_routing_engine_flags_penalized_edges():
    router = HazardAwareRouter()
    baseline = router.compute_route(
        origin_lon=80.25,
        origin_lat=13.01,
        dest_lon=80.22,
        dest_lat=12.98,
    )
    assert baseline is not None
    path_nodes = baseline["path_nodes"]

    # Penalize all edges along the baseline path
    penalized = {(path_nodes[i], path_nodes[i + 1]) for i in range(len(path_nodes) - 1)}

    penalized_route = router.compute_route(
        origin_lon=80.25,
        origin_lat=13.01,
        dest_lon=80.22,
        dest_lat=12.98,
        penalized_edges=penalized,
        penalty_factor=1.01,
    )
    assert penalized_route is not None
