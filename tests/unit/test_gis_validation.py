import pytest
from app.core.errors import AppException
from app.gis.validation import (
    point_to_wkt,
    polygon_to_wkt,
    validate_point_in_study_area,
    validate_polygon_geometry,
)


def test_validate_point_inside_bbox() -> None:
    # Chennai core coordinates: 80.20, 13.05 (Inside [80.15, 12.95, 80.30, 13.15])
    validate_point_in_study_area(lon=80.20, lat=13.05)


def test_validate_point_outside_bbox() -> None:
    # Coordinates in Mumbai (Outside Chennai)
    with pytest.raises(AppException) as exc_info:
        validate_point_in_study_area(lon=72.87, lat=19.07)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "VALIDATION_ERROR"


def test_validate_polygon_valid() -> None:
    coords = [
        [
            [80.20, 13.00],
            [80.25, 13.00],
            [80.25, 13.05],
            [80.20, 13.05],
            [80.20, 13.00],
        ]
    ]
    poly = validate_polygon_geometry(coords)
    assert poly.is_valid
    assert poly.area > 0


def test_validate_polygon_unclosed() -> None:
    coords = [
        [
            [80.20, 13.00],
            [80.25, 13.00],
            [80.25, 13.05],
            [80.20, 13.05],
        ]
    ]
    with pytest.raises(AppException) as exc_info:
        validate_polygon_geometry(coords)
    assert exc_info.value.status_code == 400
    assert "not closed" in exc_info.value.message


def test_validate_polygon_outside_bbox() -> None:
    coords = [
        [
            [72.00, 19.00],
            [72.05, 19.00],
            [72.05, 19.05],
            [72.00, 19.05],
            [72.00, 19.00],
        ]
    ]
    with pytest.raises(AppException) as exc_info:
        validate_polygon_geometry(coords)
    assert exc_info.value.status_code == 400
    assert "outside the configured study area" in exc_info.value.message


def test_wkt_generators() -> None:
    assert point_to_wkt(80.20, 13.05) == "SRID=4326;POINT(80.2 13.05)"
    poly_coords = [
        [
            [80.20, 13.00],
            [80.25, 13.00],
            [80.25, 13.05],
            [80.20, 13.05],
            [80.20, 13.00],
        ]
    ]
    wkt = polygon_to_wkt(poly_coords)
    assert wkt.startswith("SRID=4326;POLYGON((80.2 13.0, 80.25 13.0")
