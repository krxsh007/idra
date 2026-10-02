from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import AgentName
from app.schemas.agents.planning import PlanningCitation
from app.schemas.events import EventResponse


class SynthesisItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    priority: int = Field(..., ge=1, le=5)
    agent: AgentName
    title: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10, max_length=1000)
    origin: str = "AI_GENERATED"
    structured_ref: dict[str, Any] | None = None
    citations: list[PlanningCitation] = Field(default_factory=list)


class SynthesisInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    assessment_output: dict[str, Any] | None = None
    planning_output: dict[str, Any] | None = None
    facilities_output: dict[str, Any] | None = None
    resources_output: dict[str, Any] | None = None
    routing_output: dict[str, Any] | None = None
    conflicts_output: dict[str, Any] | None = None


class SynthesisOutput(BaseModel):
    executive_summary: str = Field(..., min_length=20, max_length=1500)
    recommendations: list[SynthesisItem] = Field(default_factory=list)
    conflicts_noted: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Advisory decision-support briefing only. "
        "Human commander verification required before operational deployment."
    )
