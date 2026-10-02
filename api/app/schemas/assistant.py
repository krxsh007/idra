from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import FacilityType
from app.schemas.events import EpicenterPoint


class CitizenQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=1000)
    location: EpicenterPoint | None = None
    session_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None


class NearestFacilityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    facility_id: uuid.UUID
    name: str
    facility_type: FacilityType
    distance_m: float
    capacity_provenance: str = "SIMULATED"


class CitizenAgentCitation(BaseModel):
    chunk_id: uuid.UUID | str | None = None
    document_title: str
    quoted_span: str | None = None
    relevance_score: float | None = None


class CitizenAgentLLMOutput(BaseModel):
    answer: str = Field(..., min_length=20, max_length=1000)
    cited_chunk_ids: list[str] = Field(default_factory=list)


class CitizenQueryResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    citations: list[CitizenAgentCitation] = Field(default_factory=list)
    nearest_facilities: list[NearestFacilityItem] = Field(default_factory=list)
    escalated: bool = False
    escalation_reason: str | None = None
    safety_flag: Literal["NONE", "URGENT", "LIFE_THREATENING"] = "NONE"
    disclaimer: str
