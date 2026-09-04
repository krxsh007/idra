from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from geoalchemy2.functions import (
    ST_Area,
    ST_Distance,
    ST_DWithin,
    ST_Intersects,
    ST_MakePoint,
    ST_SetSRID,
    ST_Union,
)
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.db.models.enums import FacilityType
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.facilities import Facility
from app.db.models.roads import RoadEdge, RoadNode
from app.gis.graph import road_graph_manager
from app.gis.validation import validate_point_in_bbox

MAX_SNAP_DISTANCE_M = 500.0


@dataclass
class FacilityDistanceResult:
    facility: Facility
    distance_m: float


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Compute haversine distance in meters between two lon/lat coordinates."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def snap_point_to_graph_memory(
    lon: float, lat: float, max_dist_m: float = MAX_SNAP_DISTANCE_M
) -> int:
    """Snap coordinate to nearest road node in loaded in-memory NetworkX graph."""
    validate_point_in_bbox(lon, lat)
    G = road_graph_manager.get_graph()

    closest_node = None
    min_dist = float("inf")

    for node_id, data in G.nodes(data=True):
        n_lon = data.get("lon", data.get("x", 0.0))
        n_lat = data.get("lat", data.get("y", 0.0))
        dist = haversine_distance_m(lon, lat, n_lon, n_lat)
        if dist < min_dist:
            min_dist = dist
            closest_node = node_id

    if closest_node is None or min_dist > max_dist_m:
        raise AppException(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=(
                f"Point ({lon}, {lat}) is {min_dist:.1f}m from nearest road, "
                f"exceeding {max_dist_m}m limit"
            ),
            status_code=422,
            details={"distance_m": min_dist, "limit_m": max_dist_m},
        )

    return int(closest_node)


async def snap_to_nearest_node(
    db: AsyncSession,
    lon: float,
    lat: float,
    max_dist_m: float = MAX_SNAP_DISTANCE_M,
) -> int:
    """Snap a point to the nearest road network node using PostGIS KNN (<->) on GiST index."""
    validate_point_in_bbox(lon, lat)

    try:
        point_geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        dist_expr = ST_Distance(
            cast(RoadNode.geom, func.geography),
            cast(point_geom, func.geography),
        )

        # KNN nearest node query
        stmt = (
            select(RoadNode.id, dist_expr.label("distance_m"))
            .order_by(RoadNode.geom.distance_centroid(point_geom))
            .limit(1)
        )
        res = await db.execute(stmt)
        row = res.first()

        if row is not None:
            node_id, distance_m = row
            if distance_m > max_dist_m:
                raise AppException(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message=(
                        f"Point ({lon}, {lat}) is {distance_m:.1f}m from nearest road, "
                        f"exceeding {max_dist_m}m limit"
                    ),
                    status_code=422,
                    details={"distance_m": distance_m, "limit_m": max_dist_m},
                )
            return int(node_id)
    except AppException:
        raise
    except Exception:
        # Fall back to in-memory graph
        pass

    return snap_point_to_graph_memory(lon, lat, max_dist_m)


async def get_nearby_facilities(
    db: AsyncSession,
    lon: float,
    lat: float,
    radius_m: float = 5000.0,
    facility_type: FacilityType | None = None,
    is_operational: bool | None = True,
    limit: int = 10,
) -> list[FacilityDistanceResult]:
    """Retrieve facilities within radius_m ordered by distance using ST_DWithin on geography."""
    point_geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    dist_expr = ST_Distance(
        cast(Facility.location, func.geography),
        cast(point_geom, func.geography),
    )

    stmt = select(Facility, dist_expr.label("distance_m")).where(
        ST_DWithin(
            cast(Facility.location, func.geography),
            cast(point_geom, func.geography),
            radius_m,
        )
    )

    if facility_type is not None:
        stmt = stmt.where(Facility.facility_type == facility_type)

    if is_operational is not None:
        stmt = stmt.where(Facility.is_operational == is_operational)

    stmt = stmt.order_by("distance_m").limit(limit)

    res = await db.execute(stmt)
    results: list[FacilityDistanceResult] = []
    for fac, dist in res.all():
        results.append(FacilityDistanceResult(facility=fac, distance_m=float(dist)))

    return results


async def get_reports_in_event(
    db: AsyncSession,
    event_id: uuid.UUID,
    limit: int = 100,
) -> list[IncidentReport]:
    """Retrieve incident reports located within the active event's impact radius."""
    event_stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    event_res = await db.execute(event_stmt)
    event = event_res.scalar_one_or_none()

    if not event:
        return []

    stmt = (
        select(IncidentReport)
        .where(
            ST_DWithin(
                cast(IncidentReport.location, func.geography),
                cast(event.epicenter, func.geography),
                event.radius_m,
            )
        )
        .order_by(IncidentReport.reported_at.desc())
        .limit(limit)
    )

    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_blocked_edges(
    db: AsyncSession,
    event_id: uuid.UUID,
) -> list[tuple[int, int]]:
    """Return list of (u, v) road node pairs that intersect active impassable hazard zones."""
    stmt = (
        select(RoadEdge.u, RoadEdge.v)
        .join(
            HazardZone,
            ST_Intersects(RoadEdge.geom, HazardZone.geom),
        )
        .where(
            HazardZone.event_id == event_id,
            HazardZone.is_impassable == True,  # noqa: E712
        )
        .distinct()
    )

    res = await db.execute(stmt)
    return [(int(u), int(v)) for u, v in res.all()]


async def calculate_hazard_area_sqm(
    db: AsyncSession,
    event_id: uuid.UUID,
) -> float:
    """Calculate the total unioned square meters of all active hazard zones for an event."""
    stmt = select(ST_Area(cast(ST_Union(HazardZone.geom), func.geography))).where(
        HazardZone.event_id == event_id
    )

    res = await db.execute(stmt)
    area = res.scalar_one_or_none()
    return float(area) if area is not None else 0.0


async def check_facility_hazard_intersection(
    db: AsyncSession,
    facility_id: uuid.UUID,
    event_id: uuid.UUID,
) -> bool:
    """Return True if the facility location lies inside an active hazard zone."""
    stmt = (
        select(func.count())
        .select_from(Facility)
        .join(
            HazardZone,
            ST_Intersects(Facility.location, HazardZone.geom),
        )
        .where(
            Facility.id == facility_id,
            HazardZone.event_id == event_id,
        )
    )
    res = await db.execute(stmt)
    return bool(res.scalar_one() > 0)
