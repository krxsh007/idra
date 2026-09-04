from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.enums import FacilityType, Provenance
from app.schemas.events import EpicenterPoint


class FacilityResponse(BaseModel):
    id: uuid.UUID
    external_ref: str | None = None
    name: str
    facility_type: FacilityType
    location: EpicenterPoint
    address: str | None = None
    total_capacity: int = Field(ge=0)
    current_occupancy: int = Field(ge=0)
    specializations: list[str] = []
    has_generator: bool = False
    wheelchair_access: bool = False
    contact_phone: str | None = None
    is_operational: bool = True
    location_provenance: Provenance = Provenance.REAL
    capacity_provenance: Provenance = Provenance.SIMULATED
    updated_at: datetime

    class Config:
        from_attributes = True


class FacilityListResponse(BaseModel):
    items: list[FacilityResponse]
    total: int
    limit: int
    offset: int
