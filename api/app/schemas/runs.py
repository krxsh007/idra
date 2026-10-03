from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import AgentName, AgentStatus, RunStatus, SeverityLevel


class AgentOutputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent: AgentName
    status: AgentStatus
    payload: dict[str, Any] | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class RunDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    status: RunStatus
    triggered_by: uuid.UUID | None = None
    llm_backend: str | None = None
    llm_model: str | None = None
    assessed_severity: SeverityLevel | None = None
    needs_human_review: bool
    total_latency_ms: int | None = None
    error_code: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    outputs: list[AgentOutputResponse] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunDetailResponse]
    total: int
    limit: int
    offset: int


class TriggerRunRequest(BaseModel):
    event_id: uuid.UUID
    force: bool = False
