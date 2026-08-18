import uuid

from fastapi import APIRouter, Depends, status
from geoalchemy2.functions import ST_GeomFromText
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.core.security import require_admin, require_responder
from app.db.models.events import DisasterEvent, HazardZone
from app.db.models.users import User
from app.db.session import get_db
from app.gis.validation import polygon_to_wkt, validate_polygon_geometry
from app.schemas.hazards import (
    GeoJSONPolygon,
    HazardZoneCreate,
    HazardZoneListResponse,
    HazardZoneResponse,
    HazardZoneUpdate,
)
from app.services.audit import log_mutation

router = APIRouter(tags=["Hazard Zones"])


def _to_hazard_response(zone: HazardZone) -> HazardZoneResponse:
    poly = to_shape(zone.geom)
    # Extract exterior coordinates as GeoJSON Polygon coordinate list
    exterior_coords = [[float(c[0]), float(c[1])] for c in poly.exterior.coords]
    interior_coords = [[[float(c[0]), float(c[1])] for c in ring.coords] for ring in poly.interiors]
    coordinates = [exterior_coords, *interior_coords]

    return HazardZoneResponse(
        id=zone.id,
        event_id=zone.event_id,
        label=zone.label,
        hazard_type=zone.hazard_type,
        severity=zone.severity,
        geometry=GeoJSONPolygon(type="Polygon", coordinates=coordinates),
        is_impassable=zone.is_impassable,
        active_from=zone.active_from,
        active_until=zone.active_until,
        source_note=zone.source_note,
        created_at=zone.created_at,
    )


@router.post(
    "/hazard-zones",
    response_model=HazardZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_hazard_zone(
    req: HazardZoneCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> HazardZoneResponse:
    # 1. Geometric and bbox validation
    validate_polygon_geometry(req.geometry.coordinates)

    # 2. Check active window validity
    if req.active_until is not None and req.active_until <= req.active_from:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_ERROR,
            message="Hazard zone active_until must be after active_from",
        )

    # 3. Validate parent event exists
    ev_stmt = select(DisasterEvent).where(DisasterEvent.id == req.event_id)
    if (await db.execute(ev_stmt)).scalar_one_or_none() is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {req.event_id} does not exist",
        )

    poly_geom = ST_GeomFromText(polygon_to_wkt(req.geometry.coordinates), 4326)

    zone = HazardZone(
        event_id=req.event_id,
        label=req.label,
        hazard_type=req.hazard_type,
        severity=req.severity,
        geom=poly_geom,
        is_impassable=req.is_impassable,
        active_from=req.active_from,
        active_until=req.active_until,
        source_note=req.source_note,
    )
    db.add(zone)
    await db.flush()

    # 4. Log audit
    await log_mutation(
        db=db,
        action="CREATE",
        entity_type="hazard_zone",
        entity_id=zone.id,
        actor_id=current_user.id,
        after_state={
            "event_id": str(zone.event_id),
            "label": zone.label,
            "severity": zone.severity.value,
            "is_impassable": zone.is_impassable,
        },
    )

    return _to_hazard_response(zone)


@router.get("/events/{event_id}/hazard-zones", response_model=HazardZoneListResponse)
async def list_event_hazard_zones(
    event_id: uuid.UUID,
    current_user: User = Depends(require_responder),
    db: AsyncSession = Depends(get_db),
) -> HazardZoneListResponse:
    # Check parent event exists
    ev_stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    if (await db.execute(ev_stmt)).scalar_one_or_none() is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {event_id} does not exist",
        )

    stmt = (
        select(HazardZone)
        .where(HazardZone.event_id == event_id)
        .order_by(HazardZone.created_at.desc())
    )
    zones = (await db.execute(stmt)).scalars().all()

    return HazardZoneListResponse(
        items=[_to_hazard_response(z) for z in zones],
        total=len(zones),
    )


@router.patch("/hazard-zones/{zone_id}", response_model=HazardZoneResponse)
async def update_hazard_zone(
    zone_id: uuid.UUID,
    req: HazardZoneUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> HazardZoneResponse:
    stmt = select(HazardZone).where(HazardZone.id == zone_id)
    zone = (await db.execute(stmt)).scalar_one_or_none()

    if zone is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Hazard zone {zone_id} not found",
        )

    before_state = {
        "severity": zone.severity.value,
        "is_impassable": zone.is_impassable,
        "active_until": zone.active_until.isoformat() if zone.active_until else None,
        "source_note": zone.source_note,
    }

    if req.severity is not None:
        zone.severity = req.severity

    if req.is_impassable is not None:
        zone.is_impassable = req.is_impassable

    if req.active_until is not None:
        if req.active_until <= zone.active_from:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ErrorCode.VALIDATION_ERROR,
                message="Hazard zone active_until must be after active_from",
            )
        zone.active_until = req.active_until

    if req.source_note is not None:
        zone.source_note = req.source_note

    await db.flush()

    after_state = {
        "severity": zone.severity.value,
        "is_impassable": zone.is_impassable,
        "active_until": zone.active_until.isoformat() if zone.active_until else None,
        "source_note": zone.source_note,
    }

    await log_mutation(
        db=db,
        action="UPDATE",
        entity_type="hazard_zone",
        entity_id=zone.id,
        actor_id=current_user.id,
        before_state=before_state,
        after_state=after_state,
    )

    return _to_hazard_response(zone)
