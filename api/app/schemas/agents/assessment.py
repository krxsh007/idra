from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import SeverityLevel
from app.schemas.events import EventResponse
from app.schemas.hazards import HazardZoneResponse
from app.schemas.reports import ReportResponse


class CitationSourceType(str, Enum):
    SOP = "SOP"
    REPORT = "REPORT"
    HAZARD_ZONE = "HAZARD_ZONE"


class Citation(BaseModel):
    """Grounding citation linking assessment findings to specific evidence."""

    source_type: CitationSourceType
    source_id: str = Field(..., description="ID or chunk_id of the cited evidence")
    snippet: str = Field(..., min_length=5, max_length=500, description="Relevant excerpt or claim")
    relevance_note: str | None = Field(default=None, max_length=200)


class AssessmentInput(BaseModel):
    """Inputs required by the Disaster Assessment Agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    reports: list[ReportResponse] = Field(default_factory=list)
    hazard_zones: list[HazardZoneResponse] = Field(default_factory=list)
    weather_context: dict[str, Any] | None = None
    visual_damage_indicator: float | None = Field(
        default=None,
        description="Visual damage score in [0, 1] if available (always null in MVP)",
    )


class AssessmentOutput(BaseModel):
    """Disaster Assessment Agent output schema per PRD requirements."""

    severity: SeverityLevel = Field(..., description="Assessed overall severity level")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score in [0, 1] reflecting evidence coverage and consistency",
    )
    affected_area_summary: str = Field(
        ...,
        min_length=20,
        max_length=600,
        description="Concise description of the geographical and physical impact (20-600 chars)",
    )
    estimated_people_affected: int = Field(
        ...,
        ge=0,
        description="Estimated affected count clamped to at most 10x sum of reported affected",
    )
    casualties_reported: bool = Field(
        ...,
        description="Whether casualties or critical injuries have been confirmed in input data",
    )
    evacuation_recommended: bool = Field(
        ...,
        description="Whether immediate evacuation should be ordered for affected sectors",
    )
    key_factors: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Between 1 and 5 pivotal factors determining the assessment conclusions",
    )
    visual_damage_indicator: float | None = Field(
        default=None,
        description="Visual damage indicator preserved or null",
    )
    citations: list[Citation] = Field(
        ...,
        min_length=1,
        description="At least one grounding citation referencing SOP or reports/hazards",
    )
