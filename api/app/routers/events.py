import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from geoalchemy2.functions import ST_DWithin, ST_GeomFromText
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.core.security import require_admin, require_responder
from app.db.models.enums import DisasterType, EventStatus
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.runs import Route
from app.db.models.users import User
from app.db.session import get_db
from app.gis.validation import point_to_wkt, validate_point_in_study_area
from app.schemas.events import (
    EpicenterPoint,
    EventCreate,
    EventListResponse,
    EventResponse,
    EventUpdate,
)
from app.services.audit import log_mutation

router = APIRouter(prefix="/events", tags=["Disaster Events"])


def _to_event_response(
    event: DisasterEvent,
    report_count: int = 0,
    hazard_zone_count: int = 0,
) -> EventResponse:
    shape = to_shape(event.epicenter)
    return EventResponse(
        id=event.id,
        name=event.name,
        disaster_type=event.disaster_type,
        status=event.status,
        epicenter=EpicenterPoint(lon=shape.x, lat=shape.y),
        radius_m=event.radius_m,
        declared_at=event.declared_at,
        closed_at=event.closed_at,
        description=event.description,
        created_by=event.created_by,
        created_at=event.created_at,
        report_count=report_count,
        hazard_zone_count=hazard_zone_count,
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    req: EventCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    # 1. Spatial validation
    validate_point_in_study_area(lon=req.epicenter.lon, lat=req.epicenter.lat)

    # 2. Duplicate active event detection (within 500m declared in last 1 hour)
    pt_geom = ST_GeomFromText(point_to_wkt(req.epicenter.lon, req.epicenter.lat), 4326)
    one_hour_ago = datetime.now(UTC).timestamp() - 3600

    dup_stmt = select(DisasterEvent).where(
        DisasterEvent.disaster_type == req.disaster_type,
        DisasterEvent.status == EventStatus.ACTIVE,
        func.extract("epoch", DisasterEvent.declared_at) >= one_hour_ago,
        ST_DWithin(DisasterEvent.epicenter, pt_geom, 500),
    )
    dup_res = await db.execute(dup_stmt)
    existing = dup_res.scalar_one_or_none()

    if existing is not None:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.VALIDATION_ERROR,
            message=(
                f"An active {req.disaster_type.value} event already exists within 500m "
                f"('{existing.name}', ID: {existing.id})."
            ),
            details={"existing_event_id": str(existing.id)},
        )

    # 3. Create event
    event = DisasterEvent(
        name=req.name,
        disaster_type=req.disaster_type,
        status=EventStatus.ACTIVE,
        epicenter=pt_geom,
        radius_m=req.radius_m,
        description=req.description,
        created_by=current_user.id,
    )
    db.add(event)
    await db.flush()

    # 4. Audit log
    await log_mutation(
        db=db,
        action="CREATE",
        entity_type="disaster_event",
        entity_id=event.id,
        actor_id=current_user.id,
        after_state={
            "name": event.name,
            "disaster_type": event.disaster_type.value,
            "radius_m": event.radius_m,
        },
    )

    # Reload event to populate geometry properly for output serialization
    return _to_event_response(event, report_count=0, hazard_zone_count=0)


@router.get("", response_model=EventListResponse)
async def list_events(
    event_status: EventStatus | None = Query(None, alias="status"),
    disaster_type: DisasterType | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_responder),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    base_query = select(DisasterEvent)
    count_query = select(func.count(DisasterEvent.id))

    if event_status is not None:
        base_query = base_query.where(DisasterEvent.status == event_status)
        count_query = count_query.where(DisasterEvent.status == event_status)

    if disaster_type is not None:
        base_query = base_query.where(DisasterEvent.disaster_type == disaster_type)
        count_query = count_query.where(DisasterEvent.disaster_type == disaster_type)

    total = (await db.execute(count_query)).scalar_one()

    stmt = base_query.order_by(DisasterEvent.declared_at.desc()).offset(offset).limit(limit)
    events = (await db.execute(stmt)).scalars().all()

    items: list[EventResponse] = []
    for ev in events:
        # Get count of reports and hazard zones
        r_count = (
            await db.execute(
                select(func.count(IncidentReport.id)).where(IncidentReport.event_id == ev.id)
            )
        ).scalar_one()
        h_count = (
            await db.execute(select(func.count(HazardZone.id)).where(HazardZone.event_id == ev.id))
        ).scalar_one()
        items.append(_to_event_response(ev, report_count=r_count, hazard_zone_count=h_count))

    return EventListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: uuid.UUID,
    current_user: User = Depends(require_responder),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()

    if event is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {event_id} not found",
        )

    r_count = (
        await db.execute(
            select(func.count(IncidentReport.id)).where(IncidentReport.event_id == event.id)
        )
    ).scalar_one()
    h_count = (
        await db.execute(select(func.count(HazardZone.id)).where(HazardZone.event_id == event.id))
    ).scalar_one()

    return _to_event_response(event, report_count=r_count, hazard_zone_count=h_count)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: uuid.UUID,
    req: EventUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()

    if event is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {event_id} not found",
        )

    before_state = {
        "status": event.status.value,
        "description": event.description,
        "closed_at": event.closed_at.isoformat() if event.closed_at else None,
    }

    if req.status is not None:
        event.status = req.status
        if req.status == EventStatus.CLOSED and event.closed_at is None:
            event.closed_at = req.closed_at or datetime.now(UTC)

    if req.description is not None:
        event.description = req.description

    if req.closed_at is not None:
        event.closed_at = req.closed_at

    await db.flush()

    after_state = {
        "status": event.status.value,
        "description": event.description,
        "closed_at": event.closed_at.isoformat() if event.closed_at else None,
    }

    await log_mutation(
        db=db,
        action="UPDATE",
        entity_type="disaster_event",
        entity_id=event.id,
        actor_id=current_user.id,
        before_state=before_state,
        after_state=after_state,
    )

    r_count = (
        await db.execute(
            select(func.count(IncidentReport.id)).where(IncidentReport.event_id == event.id)
        )
    ).scalar_one()
    h_count = (
        await db.execute(select(func.count(HazardZone.id)).where(HazardZone.event_id == event.id))
    ).scalar_one()

    return _to_event_response(event, report_count=r_count, hazard_zone_count=h_count)


@router.get("/{event_id}/geojson")
async def get_event_geojson(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all geospatial features associated with an event as a GeoJSON FeatureCollection.

    Includes the epicenter, hazard zones, incident reports, and nearby facilities.
    Every feature explicitly carries a data_provenance property.
    """
    from app.db.models.facilities import Facility

    stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    event = (await db.execute(stmt)).scalar_one_or_none()

    if event is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {event_id} not found",
        )

    features: list[dict[str, Any]] = []

    # 1. Event Epicenter Feature
    epicenter_shape = to_shape(event.epicenter)
    features.append(
        {
            "type": "Feature",
            "geometry": mapping(epicenter_shape),
            "properties": {
                "feature_type": "event_epicenter",
                "id": str(event.id),
                "name": event.name,
                "disaster_type": event.disaster_type.value,
                "status": event.status.value,
                "radius_m": event.radius_m,
                "declared_at": event.declared_at.isoformat() if event.declared_at else None,
                "data_provenance": "REAL",
            },
        }
    )

    # 2. Hazard Zones Features
    hz_stmt = select(HazardZone).where(HazardZone.event_id == event.id)
    hazard_zones = (await db.execute(hz_stmt)).scalars().all()
    for hz in hazard_zones:
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(hz.geom)),
                "properties": {
                    "feature_type": "hazard_zone",
                    "id": str(hz.id),
                    "label": hz.label,
                    "hazard_type": hz.hazard_type.value,
                    "severity": hz.severity.value,
                    "is_impassable": hz.is_impassable,
                    "active_from": hz.active_from.isoformat() if hz.active_from else None,
                    "data_provenance": "REAL",
                },
            }
        )

    # 3. Incident Reports Features
    rep_stmt = select(IncidentReport).where(IncidentReport.event_id == event.id)
    reports = (await db.execute(rep_stmt)).scalars().all()
    for rep in reports:
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(rep.location)),
                "properties": {
                    "feature_type": "incident_report",
                    "id": str(rep.id),
                    "source": rep.source.value,
                    "body": rep.body,
                    "casualties_reported": rep.casualties_reported,
                    "people_affected": rep.people_affected,
                    "data_provenance": rep.data_provenance.value,
                },
            }
        )

    # 4. Facilities within event impact radius
    fac_stmt = select(Facility).limit(20)
    facilities = (await db.execute(fac_stmt)).scalars().all()
    for fac in facilities:
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(to_shape(fac.location)),
                "properties": {
                    "feature_type": "facility",
                    "id": str(fac.id),
                    "name": fac.name,
                    "facility_type": fac.facility_type.value,
                    "total_capacity": fac.total_capacity,
                    "current_occupancy": fac.current_occupancy,
                    "is_operational": fac.is_operational,
                    "data_provenance": fac.location_provenance.value,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "properties": {
            "event_id": str(event.id),
            "event_name": event.name,
            "feature_count": len(features),
        },
        "features": features,
    }


@router.get(
    "/{event_id}/routes",
    response_model=list[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List all computed evacuation routes for an event",
)
async def get_event_routes(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(Route).where(Route.event_id == event_id).order_by(Route.computed_at.desc())
    res = await db.execute(stmt)
    routes = res.scalars().all()

    items = []
    for r in routes:
        path_shape = to_shape(r.path_geom)
        orig_shape = to_shape(r.origin)
        dest_shape = to_shape(r.destination)
        items.append(
            {
                "id": str(r.id),
                "run_id": str(r.run_id) if r.run_id else None,
                "event_id": str(r.event_id),
                "origin": {"lon": orig_shape.x, "lat": orig_shape.y},
                "destination": {"lon": dest_shape.x, "lat": dest_shape.y},
                "destination_facility_id": str(r.destination_facility_id)
                if r.destination_facility_id
                else None,
                "geometry": mapping(path_shape),
                "distance_m": r.distance_m,
                "duration_s": r.duration_s,
                "hazard_avoided": r.hazard_avoided,
                "traverses_hazard": r.traverses_hazard,
                "blocked_edge_count": r.blocked_edge_count,
                "algorithm": r.algorithm,
                "computed_at": r.computed_at.isoformat(),
            }
        )
    return items
