from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import AgentName, VerificationStatus


class RecommendationCitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_title: str
    source_type: str = "SOP"
    source_url: str | None = None
    section_path: str | None = None
    quoted_span: str | None = None
    relevance_score: float | None = None


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    event_id: uuid.UUID
    agent: AgentName
    priority: int
    title: str
    body: str
    origin: str
    confidence: float | None = None
    structured_ref: dict[str, Any] | None = None
    verification_status: VerificationStatus
    verified_by: uuid.UUID | None = None
    verified_at: datetime | None = None
    override_note: str | None = None
    created_at: datetime
    citations: list[RecommendationCitationResponse] = Field(default_factory=list)


class RecommendationListResponse(BaseModel):
    items: list[RecommendationResponse]
    total: int


class VerifyRecommendationRequest(BaseModel):
    action: VerificationStatus
    note: str | None = None
