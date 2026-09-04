from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException, ErrorCode
from app.db.models.enums import FacilityType
from app.db.models.facilities import Facility
from app.db.session import get_db
from app.schemas.events import EpicenterPoint
from app.schemas.facilities import FacilityListResponse, FacilityResponse

router = APIRouter(prefix="/facilities", tags=["Facilities"])


def facility_to_response(fac: Facility) -> FacilityResponse:
    pt = to_shape(fac.location)
    assert isinstance(pt, Point)
    return FacilityResponse(
        id=fac.id,
        external_ref=fac.external_ref,
        name=fac.name,
        facility_type=fac.facility_type,
        location=EpicenterPoint(lon=pt.x, lat=pt.y),
        address=fac.address,
        total_capacity=fac.total_capacity,
        current_occupancy=fac.current_occupancy,
        specializations=fac.specializations,
        has_generator=fac.has_generator,
        wheelchair_access=fac.wheelchair_access,
        contact_phone=fac.contact_phone,
        is_operational=fac.is_operational,
        location_provenance=fac.location_provenance,
        capacity_provenance=fac.capacity_provenance,
        updated_at=fac.updated_at,
    )


@router.get("", response_model=FacilityListResponse)
async def list_facilities(
    facility_type: FacilityType | None = Query(None, description="Filter by facility type"),
    is_operational: bool | None = Query(None, description="Filter by operational status"),
    min_capacity: int | None = Query(None, ge=0, description="Minimum total capacity"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> FacilityListResponse:
    """Retrieve disaster response facilities with optional type and capacity filters."""
    stmt = select(Facility)

    if facility_type is not None:
        stmt = stmt.where(Facility.facility_type == facility_type)

    if is_operational is not None:
        stmt = stmt.where(Facility.is_operational == is_operational)

    if min_capacity is not None:
        stmt = stmt.where(Facility.total_capacity >= min_capacity)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    stmt = stmt.order_by(Facility.name).offset(offset).limit(limit)
    res = await db.execute(stmt)
    facilities = res.scalars().all()

    return FacilityListResponse(
        items=[facility_to_response(f) for f in facilities],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{id}", response_model=FacilityResponse)
async def get_facility(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FacilityResponse:
    """Retrieve details of a specific emergency facility."""
    stmt = select(Facility).where(Facility.id == id)
    res = await db.execute(stmt)
    fac = res.scalar_one_or_none()

    if not fac:
        raise AppException(
            error_code=ErrorCode.NOT_FOUND,
            message=f"Facility with id {id} was not found",
            status_code=404,
        )

    return facility_to_response(fac)
