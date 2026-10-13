import pytest
from app.core.errors import AppException, ErrorCode
from app.gis.spatial import snap_point_to_graph_memory


def _snapped_distance_m(lon: float, lat: float) -> float:
    from app.gis.graph import road_graph_manager
    from app.gis.spatial import haversine_distance_m

    node = road_graph_manager.get_graph().nodes[snap_point_to_graph_memory(lon, lat)]
    return haversine_distance_m(lon, lat, node["lon"], node["lat"])


@pytest.mark.parametrize(
    ("landmark", "lon", "lat"),
    [
        ("Kathipara Junction", 80.2010, 13.0067),
        ("Koyambedu CMBT", 80.1948, 13.0694),
        ("Besant Nagar", 80.2668, 12.9990),
    ],
)
def test_landmarks_snap_to_a_nearby_road(landmark: str, lon: float, lat: float) -> None:
    """Hand-picked public landmarks sit on (or beside) real roads in the OSM network."""
    assert _snapped_distance_m(lon, lat) < 100.0, landmark


def test_snap_rejects_point_inside_guindy_national_park() -> None:
    """No public road runs through the middle of Guindy National Park."""
    with pytest.raises(AppException) as exc_info:
        snap_point_to_graph_memory(80.232, 13.002, max_dist_m=500.0)
    assert exc_info.value.status_code == 422


def test_snap_rejection_far_from_network() -> None:
    """Point in open water or edge of bbox with strict 5-meter max threshold."""
    lon, lat = 80.220, 13.050
    # With a tiny threshold of 5 meters, an off-road point should be rejected
    with pytest.raises(AppException) as exc_info:
        snap_point_to_graph_memory(lon, lat, max_dist_m=5.0)

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR.value
    assert exc_info.value.status_code == 422


def test_snap_rejection_outside_study_area_bbox() -> None:
    """Coordinate outside Chennai core study area bbox must be rejected immediately."""
    lon_outside, lat_outside = 80.500, 13.500  # Outside bbox
    with pytest.raises(AppException) as exc_info:
        snap_point_to_graph_memory(lon_outside, lat_outside)

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR.value
    assert exc_info.value.status_code == 400
