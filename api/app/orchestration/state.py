from __future__ import annotations

from typing import Any, TypedDict

from app.db.models.enums import AgentStatus, SeverityLevel


class AgentExecutionRecord(TypedDict, total=False):
    agent: str
    status: AgentStatus
    payload: dict[str, Any] | None
    latency_ms: int
    error_code: str | None
    error_message: str | None


class OrchestratorState(TypedDict, total=False):
    run_id: str
    event_id: str
    event_data: dict[str, Any]
    reports_data: list[dict[str, Any]]
    hazards_data: list[dict[str, Any]]
    weather_data: dict[str, Any] | None

    # Assessment
    assessment_output: dict[str, Any] | None
    assessment_status: AgentStatus
    assessed_severity: SeverityLevel | None

    # Facilities
    facilities_output: dict[str, Any] | None
    facilities_status: AgentStatus

    # Resources
    resources_output: dict[str, Any] | None
    resources_status: AgentStatus

    # Routing
    routing_output: dict[str, Any] | None
    routing_status: AgentStatus

    # Flags & Control
    needs_human_review: bool
    is_terminal: bool

    # History of agent node outputs
    outputs: list[AgentExecutionRecord]
    errors: list[dict[str, Any]]
