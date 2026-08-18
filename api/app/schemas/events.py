import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DisasterType, EventStatus


class EpicenterPoint(BaseModel):
    lon: float = Field(..., description="Longitude in decimal degrees")
    lat: float = Field(..., description="Latitude in decimal degrees")


class EventCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    disaster_type: DisasterType
    epicenter: EpicenterPoint
    radius_m: int = Field(
        ..., ge=100, le=50000, description="Impact radius in meters (100 to 50000)"
    )
    description: str | None = Field(default=None, max_length=2000)


class EventUpdate(BaseModel):
    status: EventStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    closed_at: datetime | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    disaster_type: DisasterType
    status: EventStatus
    epicenter: EpicenterPoint
    radius_m: int
    declared_at: datetime
    closed_at: datetime | None = None
    description: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    report_count: int = 0
    hazard_zone_count: int = 0


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
    limit: int
    offset: int
