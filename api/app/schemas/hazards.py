import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import DisasterType, SeverityLevel


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(
        ...,
        description="GeoJSON Polygon coordinate array: [ [ [lon, lat], [lon, lat], ... ] ]",
    )


class HazardZoneCreate(BaseModel):
    event_id: uuid.UUID
    label: str = Field(..., min_length=2, max_length=100)
    hazard_type: DisasterType
    severity: SeverityLevel
    geometry: GeoJSONPolygon
    is_impassable: bool = False
    active_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active_until: datetime | None = None
    source_note: str | None = Field(default=None, max_length=1000)


class HazardZoneUpdate(BaseModel):
    severity: SeverityLevel | None = None
    is_impassable: bool | None = None
    active_until: datetime | None = None
    source_note: str | None = Field(default=None, max_length=1000)


class HazardZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    label: str
    hazard_type: DisasterType
    severity: SeverityLevel
    geometry: GeoJSONPolygon
    is_impassable: bool
    active_from: datetime
    active_until: datetime | None = None
    source_note: str | None = None
    created_at: datetime


class HazardZoneListResponse(BaseModel):
    items: list[HazardZoneResponse]
    total: int
