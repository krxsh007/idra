import pytest
from app.core.errors import AppException, ErrorCode
from app.gis.spatial import snap_point_to_graph_memory


def test_hand_verified_snap_kathipara_junction() -> None:
    """Hand-verified coordinate 1: Kathipara Junction arterial node."""
    lon, lat = 80.1802, 12.9801  # Slightly offset from exact (80.180, 12.980)
    node_id = snap_point_to_graph_memory(lon, lat, max_dist_m=500.0)
    assert node_id == 1001


def test_hand_verified_snap_koyambedu_cmbt() -> None:
    """Hand-verified coordinate 2: Koyambedu CMBT bus terminus."""
    lon, lat = 80.1904, 13.0722  # Slightly offset from exact (80.190, 13.072)
    node_id = snap_point_to_graph_memory(lon, lat, max_dist_m=500.0)
    assert node_id == 2002


def test_hand_verified_snap_besant_nagar() -> None:
    """Hand-verified coordinate 3: Besant Nagar coastal arterial."""
    lon, lat = 80.2698, 13.0102  # Slightly offset from exact (80.270, 13.010)
    node_id = snap_point_to_graph_memory(lon, lat, max_dist_m=500.0)
    assert node_id == 3002


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
