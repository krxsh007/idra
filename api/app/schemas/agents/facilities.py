from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import FacilityType, SeverityLevel
from app.schemas.events import EpicenterPoint, EventResponse


class FacilityCandidate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    facility_id: uuid.UUID
    name: str
    facility_type: FacilityType
    distance_m: float
    total_capacity: int
    current_occupancy: int
    available_capacity: int
    has_generator: bool
    wheelchair_access: bool
    specializations: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class FacilityRecommendationInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    assessment_summary: str
    severity: SeverityLevel
    casualties_reported: bool = False
    estimated_people_affected: int = 0
    epicenter: EpicenterPoint
    hospital_search_radius_m: float = 15000.0
    shelter_search_radius_m: float = 10000.0


class FacilityRecommendationOutput(BaseModel):
    recommended_hospitals: list[FacilityCandidate] = Field(default_factory=list)
    recommended_shelters: list[FacilityCandidate] = Field(default_factory=list)
    rationale: str = Field(..., min_length=10, max_length=1000)
    total_shelter_capacity_available: int = 0
    total_hospital_capacity_available: int = 0
