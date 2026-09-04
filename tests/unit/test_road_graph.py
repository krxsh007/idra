import networkx as nx
from app.core.config import settings
from app.gis.graph import road_graph_manager


def test_road_graph_singleton_loaded() -> None:
    G = road_graph_manager.get_graph()
    assert isinstance(G, nx.DiGraph)
    assert G.number_of_nodes() >= 1500
    assert G.number_of_edges() >= 5000


def test_road_graph_manifest_bbox() -> None:
    expected_bbox = [float(x.strip()) for x in settings.STUDY_AREA_BBOX.split(",")]
    manifest_bbox = road_graph_manager.manifest.get("bbox", [])
    assert len(manifest_bbox) == 4
    for m, e in zip(manifest_bbox, expected_bbox, strict=False):
        assert abs(m - e) < 0.01


def test_road_graph_connectivity_shortest_path() -> None:
    G = road_graph_manager.get_graph()
    # Kathipara Junction (1001) to Chennai Central (1007)
    path = nx.shortest_path(G, source=1001, target=1007, weight="travel_s")
    assert len(path) >= 5
    assert path[0] == 1001
    assert path[-1] == 1007


def test_road_graph_edge_attributes() -> None:
    G = road_graph_manager.get_graph()
    for _u, _v, data in list(G.edges(data=True))[:50]:
        assert "length_m" in data
        assert data["length_m"] > 0
        assert "speed_kph" in data
        assert data["speed_kph"] > 0
        assert "travel_s" in data
        assert data["travel_s"] > 0
