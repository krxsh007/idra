from fastapi import status
from shapely.geometry import Polygon

from app.core.config import settings
from app.core.errors import AppException, ErrorCode


def validate_point_in_study_area(lon: float, lat: float) -> None:
    """Validate that (lon, lat) falls within configured STUDY_AREA_BBOX."""
    min_lon, min_lat, max_lon, max_lat = settings.parsed_bbox

    if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message=(
                f"Coordinates ({lon}, {lat}) fall outside the configured study area "
                f"bbox [{min_lon}, {min_lat}, {max_lon}, {max_lat}]."
            ),
            details={
                "provided_coords": {"lon": lon, "lat": lat},
                "study_area_bbox": {
                    "min_lon": min_lon,
                    "min_lat": min_lat,
                    "max_lon": max_lon,
                    "max_lat": max_lat,
                },
            },
        )


def validate_polygon_geometry(
    coordinates: list[list[list[float]]] | list[list[tuple[float, float]]],
) -> Polygon:
    """Validate GeoJSON Polygon coordinates, closure, self-intersection, and bbox bounds."""
    if not coordinates or not coordinates[0]:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="Polygon must contain at least one linear ring of coordinates.",
        )

    exterior_ring = coordinates[0]
    if len(exterior_ring) < 4:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message=(
                "Polygon exterior ring must have at least 4 coordinate pairs (including closure)."
            ),
        )

    # Check closure
    first_pt = exterior_ring[0]
    last_pt = exterior_ring[-1]
    if first_pt[0] != last_pt[0] or first_pt[1] != last_pt[1]:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="Polygon exterior ring is not closed (first and last points must match).",
        )

    # Check all coordinates fall within study area
    for pt in exterior_ring:
        validate_point_in_study_area(lon=float(pt[0]), lat=float(pt[1]))

    try:
        poly = Polygon(exterior_ring)
    except Exception as exc:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid polygon geometry structure: {exc}",
        ) from exc

    if not poly.is_valid:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="Polygon is geometrically invalid or self-intersecting.",
        )

    # Max area check (100 km² in equatorial degrees is approx 0.0082 sq degrees)
    if poly.area > 0.01:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="Hazard zone polygon area exceeds the maximum allowed size (100 km²).",
        )

    return poly


def point_to_wkt(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def polygon_to_wkt(coordinates: list[list[list[float]]] | list[list[tuple[float, float]]]) -> str:
    ring_strs = []
    for ring in coordinates:
        coord_pairs = ", ".join(f"{pt[0]} {pt[1]}" for pt in ring)
        ring_strs.append(f"({coord_pairs})")
    all_rings = ", ".join(ring_strs)
    return f"SRID=4326;POLYGON({all_rings})"
