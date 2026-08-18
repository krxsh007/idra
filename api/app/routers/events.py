import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from geoalchemy2.functions import ST_DWithin, ST_GeomFromText
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.core.security import require_admin, require_responder
from app.db.models.enums import DisasterType, EventStatus
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
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
