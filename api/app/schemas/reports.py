import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import Provenance, ReportSource
from app.schemas.events import EpicenterPoint


class ReportCreate(BaseModel):
    event_id: uuid.UUID | None = None
    source: ReportSource = ReportSource.CITIZEN
    reporter_name: str | None = Field(default=None, max_length=100)
    reporter_phone: str | None = Field(default=None, max_length=20)
    body: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Detailed description of incident (5 to 4000 characters)",
    )
    location: EpicenterPoint
    casualties_reported: bool = False
    people_affected: int | None = Field(default=None, ge=0)
    data_provenance: Provenance = Provenance.REAL


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID | None = None
    source: ReportSource
    reporter_name: str | None = None
    reporter_phone: str | None = None
    body: str
    location: EpicenterPoint
    casualties_reported: bool
    people_affected: int | None = None
    data_provenance: Provenance
    reported_at: datetime
    created_at: datetime


class ReportListResponse(BaseModel):
    items: list[ReportResponse]
    total: int
    limit: int
    offset: int
