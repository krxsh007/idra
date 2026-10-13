import networkx as nx
from app.core.config import settings
from app.gis.graph import road_graph_manager


def test_road_graph_singleton_loaded() -> None:
    G = road_graph_manager.get_graph()
    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() >= 20000
    assert G.number_of_edges() >= 50000


def test_road_graph_manifest_bbox() -> None:
    expected_bbox = [float(x.strip()) for x in settings.STUDY_AREA_BBOX.split(",")]
    manifest_bbox = road_graph_manager.manifest.get("bbox", [])
    assert len(manifest_bbox) == 4
    for m, e in zip(manifest_bbox, expected_bbox, strict=False):
        assert abs(m - e) < 0.01


def test_road_graph_connectivity_shortest_path() -> None:
    from app.gis.routing import hazard_router
    from app.gis.spatial import haversine_distance_m

    # Kathipara Junction to Chennai Central across the real OSM street network
    origin, dest = (80.2010, 13.0067), (80.2750, 13.0827)
    res = hazard_router.compute_route(*origin, *dest)
    assert res is not None
    straight_m = haversine_distance_m(*origin, *dest)
    # Road distance exceeds the straight line but stays within a realistic detour factor
    assert straight_m < res["distance_m"] < 1.6 * straight_m
    # Route geometry follows street shapes, not just junction-to-junction lines
    assert len(res["coordinates"]) > len(res["path_nodes"])


def test_road_graph_is_osm_and_strongly_connected() -> None:
    G = road_graph_manager.get_graph()
    assert "OpenStreetMap" in road_graph_manager.manifest.get("source", "")
    assert nx.is_strongly_connected(G)


def test_road_graph_edge_attributes() -> None:
    G = road_graph_manager.get_graph()
    for _u, _v, data in list(G.edges(data=True))[:50]:
        assert "length_m" in data
        assert data["length_m"] > 0
        assert "speed_kph" in data
        assert data["speed_kph"] > 0
        assert "travel_s" in data
        assert data["travel_s"] > 0
