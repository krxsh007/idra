from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ResourceKind, SeverityLevel
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import HazardZoneResponse
from app.schemas.reports import ReportResponse


class AllocatedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: uuid.UUID
    resource_kind: ResourceKind
    label: str
    quantity: int = Field(..., gt=0, description="Allocated quantity <= free inventory")
    depot_facility_id: uuid.UUID | None = None
    target_zone_label: str
    target_location: EpicenterPoint
    priority: int = Field(..., ge=1, le=5)
    rationale: str = Field(..., min_length=5, max_length=500)


class ResourceAllocationInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    severity: SeverityLevel
    assessment_summary: str
    estimated_people_affected: int = 0
    casualties_reported: bool = False
    reports: list[ReportResponse] = Field(default_factory=list)
    hazard_zones: list[HazardZoneResponse] = Field(default_factory=list)


class ResourceAllocationOutput(BaseModel):
    allocations: list[AllocatedItem] = Field(default_factory=list)
    total_items_allocated: int = 0
    shortages_identified: list[str] = Field(default_factory=list)
    operational_summary: str = Field(..., min_length=10, max_length=1000)
