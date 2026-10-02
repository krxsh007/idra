from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import SeverityLevel
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import HazardZoneResponse
from app.schemas.reports import ReportResponse


class PlanningCitation(BaseModel):
    chunk_id: uuid.UUID | str | None = None
    document_title: str
    quoted_span: str | None = None
    relevance_score: float | None = None
    source_url: str | None = None


class PrioritizedZone(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    zone_label: str
    centroid: EpicenterPoint
    priority: int = Field(
        ..., ge=1, le=5, description="Unique, contiguous priority starting from 1"
    )
    people_estimate: int = Field(..., ge=0)
    accessibility: Literal["ACCESSIBLE", "CONSTRAINED", "BLOCKED"]
    rationale: str = Field(..., min_length=10, max_length=1000)
    report_ids: list[uuid.UUID] = Field(default_factory=list)


class RescuePlanningInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    reports: list[ReportResponse] = Field(default_factory=list)
    hazard_zones: list[HazardZoneResponse] = Field(default_factory=list)
    assessment_severity: SeverityLevel
    assessment_summary: str = ""


class RescuePlanningOutput(BaseModel):
    prioritized_zones: list[PrioritizedZone] = Field(default_factory=list)
    operation_sequence: list[str] = Field(default_factory=list)
    citations: list[PlanningCitation] = Field(default_factory=list)
    origin: str = "AI_GENERATED"
