import uuid

from fastapi import APIRouter, Depends, Query, status
from geoalchemy2.functions import ST_DWithin, ST_GeomFromText
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.core.ratelimit import limit_public_reports
from app.core.security import require_responder
from app.db.models.enums import EventStatus
from app.db.models.events import DisasterEvent, IncidentReport
from app.db.models.users import User
from app.db.session import get_db
from app.gis.validation import point_to_wkt, validate_point_in_study_area
from app.schemas.events import EpicenterPoint
from app.schemas.reports import ReportCreate, ReportListResponse, ReportResponse

router = APIRouter(tags=["Incident Reports"])


def _to_report_response(report: IncidentReport) -> ReportResponse:
    shape = to_shape(report.location)
    return ReportResponse(
        id=report.id,
        event_id=report.event_id,
        source=report.source,
        reporter_name=report.reporter_name,
        reporter_phone=report.reporter_phone,
        body=report.body,
        location=EpicenterPoint(lon=shape.x, lat=shape.y),
        casualties_reported=report.casualties_reported,
        people_affected=report.people_affected,
        data_provenance=report.data_provenance,
        reported_at=report.reported_at,
        created_at=report.created_at,
    )


@router.post(
    "/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_public_reports)],
)
async def submit_report(
    req: ReportCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    # 1. Validate spatial coordinates in study area
    validate_point_in_study_area(lon=req.location.lon, lat=req.location.lat)

    pt_geom = ST_GeomFromText(point_to_wkt(req.location.lon, req.location.lat), 4326)
    event_id = req.event_id

    # 2. If event_id not provided, automatically find the closest active event within its radius
    if event_id is None:
        stmt = (
            select(DisasterEvent)
            .where(
                DisasterEvent.status == EventStatus.ACTIVE,
                ST_DWithin(DisasterEvent.epicenter, pt_geom, DisasterEvent.radius_m),
            )
            .order_by(func.ST_Distance(DisasterEvent.epicenter, pt_geom))
            .limit(1)
        )
        res = await db.execute(stmt)
        matched_event = res.scalar_one_or_none()
        if matched_event:
            event_id = matched_event.id
    else:
        # Validate provided event exists
        ev_stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
        if (await db.execute(ev_stmt)).scalar_one_or_none() is None:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ErrorCode.NOT_FOUND,
                message=f"Disaster event {event_id} does not exist",
            )

    report = IncidentReport(
        event_id=event_id,
        source=req.source,
        reporter_name=req.reporter_name,
        reporter_phone=req.reporter_phone,
        body=req.body,
        location=pt_geom,
        casualties_reported=req.casualties_reported,
        people_affected=req.people_affected,
        data_provenance=req.data_provenance,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    return _to_report_response(report)


@router.get("/events/{event_id}/reports", response_model=ReportListResponse)
async def list_event_reports(
    event_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_responder),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    # Check event exists
    ev_stmt = select(DisasterEvent).where(DisasterEvent.id == event_id)
    if (await db.execute(ev_stmt)).scalar_one_or_none() is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.NOT_FOUND,
            message=f"Disaster event {event_id} does not exist",
        )

    count_stmt = select(func.count(IncidentReport.id)).where(IncidentReport.event_id == event_id)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(IncidentReport)
        .where(IncidentReport.event_id == event_id)
        .order_by(IncidentReport.reported_at.desc())
        .offset(offset)
        .limit(limit)
    )
    reports = (await db.execute(stmt)).scalars().all()

    return ReportListResponse(
        items=[_to_report_response(r) for r in reports],
        total=total,
        limit=limit,
        offset=offset,
    )
