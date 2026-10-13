from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.agents.assessment import DisasterAssessmentAgent
from app.agents.base import AgentFailure, RunContext
from app.db.models.enums import (
    AgentName,
    AgentStatus,
    DisasterType,
    EventStatus,
    Provenance,
    ReportSource,
    SeverityLevel,
)
from app.llm.fake import FakeLLMClient
from app.rag.retriever import RetrievedChunk
from app.schemas.agents.assessment import (
    AssessmentInput,
    AssessmentOutput,
    Citation,
    CitationSourceType,
)
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse
from app.schemas.reports import ReportResponse


def create_sample_event() -> EventResponse:
    return EventResponse(
        id=uuid.uuid4(),
        name="Velachery Flash Flood Event",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=EpicenterPoint(lon=80.22, lat=12.98),
        radius_m=3000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        description="Heavy monsoonal rains inundating residential colonies in Velachery.",
        report_count=2,
        hazard_zone_count=1,
    )


def create_sample_reports(event_id: uuid.UUID) -> list[ReportResponse]:
    return [
        ReportResponse(
            id=uuid.uuid4(),
            event_id=event_id,
            source=ReportSource.CITIZEN,
            body="Water levels reached 4 feet on 100 Feet Road. 25 people trapped.",
            location=EpicenterPoint(lon=80.221, lat=12.982),
            casualties_reported=False,
            people_affected=25,
            data_provenance=Provenance.REAL,
            reported_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        ),
        ReportResponse(
            id=uuid.uuid4(),
            event_id=event_id,
            source=ReportSource.RESPONDER,
            body="Power substations submerged. Need immediate evacuation assistance.",
            location=EpicenterPoint(lon=80.219, lat=12.979),
            casualties_reported=True,
            people_affected=15,
            data_provenance=Provenance.REAL,
            reported_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        ),
    ]


def create_sample_hazards(event_id: uuid.UUID) -> list[HazardZoneResponse]:
    return [
        HazardZoneResponse(
            id=uuid.uuid4(),
            event_id=event_id,
            label="Velachery Main Lake Inundation",
            hazard_type=DisasterType.FLOOD,
            severity=SeverityLevel.SEVERE,
            geometry=GeoJSONPolygon(
                coordinates=[
                    [
                        [80.21, 12.97],
                        [80.23, 12.97],
                        [80.23, 12.99],
                        [80.21, 12.99],
                        [80.21, 12.97],
                    ]
                ]
            ),
            is_impassable=True,
            active_from=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
    ]


def create_dummy_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_title="NDMA Flood Guidelines",
        source_type="SOP",
        hazard_types=[DisasterType.FLOOD],
        section_path="Section 4.2 / Evacuation Priorities",
        content="Standard protocol requires pre-emptive evacuation when water exceeds 3 feet.",
        vector_score=0.85,
        lexical_score=0.75,
        hybrid_score=0.82,
        published_at=datetime.now(UTC).date(),
    )


@pytest.mark.asyncio
async def test_no_llm_call_rule_on_insufficient_evidence():
    """If retrieval yields 0 chunks, return INSUFFICIENT_EVIDENCE with 0 LLM calls."""
    agent = DisasterAssessmentAgent()
    fake_llm = FakeLLMClient()
    event = create_sample_event()
    input_data = AssessmentInput(event=event)

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=fake_llm,
    )

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []  # No chunks clearing 0.35 floor

        result = await agent.run(ctx, input_data)

        assert isinstance(result, AgentFailure)
        assert result.status == AgentStatus.INSUFFICIENT_EVIDENCE
        assert result.code == "INSUFFICIENT_EVIDENCE"
        assert fake_llm.call_count == 0


@pytest.mark.asyncio
async def test_assessment_agent_execution_and_clamping():
    """Agent clamps estimated_people_affected to <= 10x sum of reported affected."""
    agent = DisasterAssessmentAgent()
    event = create_sample_event()
    reports = create_sample_reports(event.id)  # sum = 25 + 15 = 40
    hazards = create_sample_hazards(event.id)
    input_data = AssessmentInput(event=event, reports=reports, hazard_zones=hazards)

    chunk = create_dummy_chunk()

    # LLM hallucinates 5000 affected people
    fixture = AssessmentOutput(
        severity=SeverityLevel.SEVERE,
        confidence=0.88,
        affected_area_summary="Severe waterlogging observed across Velachery central area.",
        estimated_people_affected=5000,
        casualties_reported=False,
        evacuation_recommended=True,
        key_factors=["Water rising rapidly in residential sectors."],
        citations=[
            Citation(
                source_type=CitationSourceType.SOP,
                source_id=str(chunk.chunk_id),
                snippet="Pre-emptive evacuation required.",
            )
        ],
    )

    fake_llm = FakeLLMClient(fixture_responses=[fixture])
    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=fake_llm,
    )

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [chunk]

        result = await agent.run(ctx, input_data)

        assert isinstance(result, AssessmentOutput)
        assert fake_llm.call_count == 1
        # Clamped to 10 * 40 = 400
        assert result.estimated_people_affected == 400
        # Casualties aligned with input reports
        assert result.casualties_reported is True
        # Evacuation key factors reinforced
        has_evidence = any(
            "hazard" in k.lower() or "report" in k.lower() or "water" in k.lower()
            for k in result.key_factors
        )
        assert has_evidence


@pytest.mark.asyncio
async def test_slow_llm_provider_reported_as_unavailable():
    """A provider slower than the LLM budget is reported as LLM_UNAVAILABLE (not a timeout),
    so the pipeline continues on its degraded baseline instead of stopping."""
    agent = DisasterAssessmentAgent()
    event = create_sample_event()
    input_data = AssessmentInput(event=event)

    chunk = create_dummy_chunk()

    class SlowLLM(FakeLLMClient):
        async def structured(self, *args, **kwargs):
            await asyncio.sleep(0.5)
            return super().structured(*args, **kwargs)

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=SlowLLM(),
        timeout_s=0.1,
    )

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [chunk]

        result = await agent.run(ctx, input_data)

        assert isinstance(result, AgentFailure)
        assert result.status == AgentStatus.FAILED
        assert result.code == "LLM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_agent_timeout_handling():
    """Slowness outside the LLM call (here: retrieval) still ends in AGENT_TIMEOUT."""
    agent = DisasterAssessmentAgent()
    event = create_sample_event()
    input_data = AssessmentInput(event=event)

    async def slow_search(*args, **kwargs):
        await asyncio.sleep(0.5)
        return [create_dummy_chunk()]

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=FakeLLMClient(),
        timeout_s=0.05,
    )

    with patch("app.agents.assessment.retriever.search", side_effect=slow_search):
        result = await agent.run(ctx, input_data)

        assert isinstance(result, AgentFailure)
        assert result.status == AgentStatus.TIMEOUT
        assert result.code == "AGENT_TIMEOUT"


@pytest.mark.asyncio
async def test_repair_retry_on_schema_error():
    """BaseAgent attempts a second repair call if the first output fails validation."""
    agent = DisasterAssessmentAgent()
    event = create_sample_event()
    reports = create_sample_reports(event.id)
    input_data = AssessmentInput(event=event, reports=reports)
    chunk = create_dummy_chunk()

    valid_output = AssessmentOutput(
        severity=SeverityLevel.HIGH,
        confidence=0.75,
        affected_area_summary="High water levels in Velachery region requiring shelter deployment.",
        estimated_people_affected=150,
        casualties_reported=True,
        evacuation_recommended=False,
        key_factors=["Water accumulation near main roads."],
        citations=[
            Citation(
                source_type=CitationSourceType.REPORT,
                source_id=str(reports[0].id),
                snippet="Water levels reached 4 feet.",
            )
        ],
    )

    fake_llm = FakeLLMClient(
        fixture_responses=[
            {"invalid_key": "broken"},
            valid_output,
        ]
    )

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.DISASTER_ASSESSMENT,
        llm=fake_llm,
        max_repair_retries=1,
    )

    with patch("app.agents.assessment.retriever.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [chunk]

        result = await agent.run(ctx, input_data)

        assert isinstance(result, AssessmentOutput)
        assert fake_llm.call_count == 2
        assert "[REPAIR REQUIRED]" in fake_llm.recorded_prompts[1]
