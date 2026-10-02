from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.db.models.enums import AgentName, AgentStatus, DisasterType, EventStatus, SeverityLevel
from app.llm.fake import FakeLLMClient
from app.orchestration.graph import create_orchestrator_graph
from app.orchestration.state import OrchestratorState
from app.schemas.agents.assessment import AssessmentOutput, Citation, CitationSourceType


def build_sample_state() -> OrchestratorState:
    event_id = str(uuid.uuid4())
    return {
        "run_id": str(uuid.uuid4()),
        "event_id": event_id,
        "event_data": {
            "id": event_id,
            "name": "Adyar Basin Flood",
            "disaster_type": DisasterType.FLOOD.value,
            "status": EventStatus.ACTIVE.value,
            "epicenter": {"lon": 80.25, "lat": 13.01},
            "radius_m": 2500,
            "declared_at": datetime.now(UTC).isoformat(),
            "description": "Rising waters near Kotturpuram",
            "created_at": datetime.now(UTC).isoformat(),
        },
        "reports_data": [],
        "hazards_data": [],
        "weather_data": None,
        "outputs": [],
        "errors": [],
        "needs_human_review": False,
        "is_terminal": False,
    }


@pytest.mark.asyncio
async def test_orchestrator_graph_success_flow():
    state = build_sample_state()
    fixture = AssessmentOutput(
        severity=SeverityLevel.HIGH,
        confidence=0.85,
        affected_area_summary="High water levels in Kotturpuram residential area.",
        estimated_people_affected=120,
        casualties_reported=False,
        evacuation_recommended=False,
        key_factors=["Adyar river cresting."],
        citations=[
            Citation(
                source_type=CitationSourceType.SOP,
                source_id="dummy_sop_chunk",
                snippet="Flood standard response.",
            )
        ],
    )
    fake_llm = FakeLLMClient(fixture_responses=[fixture])
    graph = create_orchestrator_graph(db=None, llm=fake_llm)

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_retriever:
        from app.rag.retriever import RetrievedChunk

        mock_retriever.return_value = [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                doc_title="NDMA Guidelines",
                source_type="SOP",
                hazard_types=[DisasterType.FLOOD],
                section_path="Section 1",
                content="Flood protocol content",
                vector_score=0.9,
                lexical_score=0.8,
                hybrid_score=0.87,
                published_at=datetime.now(UTC).date(),
            )
        ]

        result = await graph.ainvoke(state)

        assert result["assessment_status"] == AgentStatus.SUCCESS
        assert result["needs_human_review"] is False
        assert len(result["outputs"]) == 3
        agents_run = [o["agent"] for o in result["outputs"]]
        assert agents_run == [
            AgentName.DISASTER_ASSESSMENT.value,
            AgentName.HOSPITAL_RECOMMENDATION.value,
            AgentName.RESOURCE_COORDINATION.value,
        ]
        assert all(o["status"] == AgentStatus.SUCCESS for o in result["outputs"])


@pytest.mark.asyncio
async def test_orchestrator_graph_low_confidence_triggers_human_review():
    state = build_sample_state()
    # Confidence 0.35 is below settings.ASSESSMENT_CONFIDENCE_FLOOR = 0.5
    fixture = AssessmentOutput(
        severity=SeverityLevel.MODERATE,
        confidence=0.35,
        affected_area_summary="Uncertain telemetry for southern sector.",
        estimated_people_affected=50,
        casualties_reported=False,
        evacuation_recommended=False,
        key_factors=["Sparse telemetry."],
        citations=[
            Citation(
                source_type=CitationSourceType.SOP,
                source_id="dummy_chunk",
                snippet="Protocol snippet.",
            )
        ],
    )
    fake_llm = FakeLLMClient(fixture_responses=[fixture])
    graph = create_orchestrator_graph(db=None, llm=fake_llm)

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_retriever:
        from app.rag.retriever import RetrievedChunk

        mock_retriever.return_value = [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                doc_title="NDMA Guidelines",
                source_type="SOP",
                hazard_types=[DisasterType.FLOOD],
                section_path="Section 1",
                content="Flood protocol content",
                vector_score=0.8,
                lexical_score=0.7,
                hybrid_score=0.77,
                published_at=datetime.now(UTC).date(),
            )
        ]

        result = await graph.ainvoke(state)

        assert result["assessment_status"] == AgentStatus.SUCCESS
        assert result["needs_human_review"] is True
        assert result["is_terminal"] is True


@pytest.mark.asyncio
async def test_orchestrator_graph_insufficient_evidence_flow():
    state = build_sample_state()
    fake_llm = FakeLLMClient()
    graph = create_orchestrator_graph(db=None, llm=fake_llm)

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_retriever:
        mock_retriever.return_value = []  # No chunks cleared floor

        result = await graph.ainvoke(state)

        assert result["assessment_status"] == AgentStatus.INSUFFICIENT_EVIDENCE
        assert result["needs_human_review"] is True
        assert result["is_terminal"] is True
        assert len(result["outputs"]) == 1
        assert result["outputs"][0]["error_code"] == "INSUFFICIENT_EVIDENCE"
