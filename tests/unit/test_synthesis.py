from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from app.agents.base import RunContext
from app.db.models.enums import AgentName, DisasterType, EventStatus, ResourceKind
from app.llm.fake import FakeLLMClient
from app.orchestration.synthesis import SynthesisAgent
from app.schemas.agents.synthesis import SynthesisInput, SynthesisItem, SynthesisOutput
from app.schemas.events import EpicenterPoint, EventResponse


def make_event() -> EventResponse:
    return EventResponse(
        id=uuid.uuid4(),
        name="Chennai North Flooding",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=EpicenterPoint(lon=80.20, lat=13.00),
        radius_m=5000.0,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_input(event: EventResponse) -> SynthesisInput:
    return SynthesisInput(
        event=event,
        assessment_output={"severity": "HIGH", "estimated_people_affected": 300},
        planning_output={
            "prioritized_zones": [
                {
                    "zone_label": "Canal Zone",
                    "priority": 1,
                    "accessibility": "BLOCKED",
                    "people_estimate": 80,
                },
                {
                    "zone_label": "Station Sector",
                    "priority": 2,
                    "accessibility": "CONSTRAINED",
                    "people_estimate": 120,
                },
            ]
        },
        facilities_output={
            "recommended_hospitals": [
                {
                    "name": "Stanley Medical College Hospital",
                    "available_capacity": 50,
                    "facility_id": str(uuid.uuid4()),
                }
            ],
            "recommended_shelters": [
                {
                    "name": "Corporation Community Hall",
                    "available_capacity": 200,
                    "facility_id": str(uuid.uuid4()),
                }
            ],
        },
        resources_output={
            "allocations": [
                {
                    "resource_id": str(uuid.uuid4()),
                    "label": "Ambulance Depot",
                    "resource_kind": ResourceKind.AMBULANCE.value,
                    "quantity": 2,
                    "priority": 1,
                    "target_zone_label": "Canal Zone",
                },
                {
                    "resource_id": str(uuid.uuid4()),
                    "label": "Food Packs",
                    "resource_kind": ResourceKind.FOOD_KIT.value,
                    "quantity": 50,
                    "priority": 3,
                    "target_zone_label": "Station Sector",
                },
            ]
        },
        conflicts_output={"conflicts_resolved": ["Reassigned 20 evacuees to secondary shelter."]},
    )


@pytest.mark.asyncio
async def test_synthesis_deterministic_priorities():
    event = make_event()
    agent = SynthesisAgent()
    ctx = RunContext(
        event_id=event.id,
        agent_name=agent.agent_name,
        llm=FakeLLMClient(),
    )

    input_data = make_input(event)

    out = await agent.run(ctx, input_data)

    assert len(out.recommendations) >= 5
    # Verify priority ordering
    priorities = [r.priority for r in out.recommendations]
    assert priorities == sorted(priorities)
    assert priorities[0] == 1  # Life safety at priority 1
    assert priorities[-1] == 5  # Monitoring at priority 5
    assert len(out.conflicts_noted) >= 1
    assert "Advisory decision-support" in out.disclaimer


def test_synthesis_consistency_catches_hallucinated_facility():
    agent = SynthesisAgent()
    allowed = {"Stanley Medical College Hospital", "Corporation Community Hall"}

    # Candidate with hallucinated hospital
    candidate = SynthesisOutput(
        executive_summary="Overview of flood operations.",
        recommendations=[
            SynthesisItem(
                priority=1,
                agent=AgentName.HOSPITAL_RECOMMENDATION,
                title="Send casualties to Imaginary Private Clinic",
                body="Route critical trauma patients to Imaginary Private Clinic immediately.",
            )
        ],
    )

    is_valid = agent._validate_consistency(candidate, allowed)
    assert is_valid is False


class _HangingLLM(FakeLLMClient):
    async def structured(self, *args, **kwargs):
        await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_synthesis_falls_back_when_llm_exceeds_budget():
    event = make_event()
    agent = SynthesisAgent()
    ctx = RunContext(
        event_id=event.id,
        agent_name=agent.agent_name,
        llm=_HangingLLM(),
        timeout_s=0.4,
    )

    out = await agent.run(ctx, make_input(event))

    # The agent returns its deterministic baseline instead of timing out as a whole.
    assert isinstance(out, SynthesisOutput)
    assert len(out.recommendations) >= 5


def test_synthesis_consistency_accepts_real_facility_after_leading_verb():
    agent = SynthesisAgent()
    allowed = {"Guindy Higher Secondary School Camp"}
    candidate = SynthesisOutput(
        executive_summary="Overview of flood operations.",
        recommendations=[
            SynthesisItem(
                priority=1,
                agent=AgentName.RESOURCE_COORDINATION,
                title="Dispatch Guindy Higher Secondary School resources",
                body="Stage boats at the camp.",
            )
        ],
    )
    assert agent._validate_consistency(candidate, allowed) is True


def test_synthesis_consistency_rejects_invented_name_sharing_suffix():
    agent = SynthesisAgent()
    allowed = {"Guindy Higher Secondary School Camp"}
    candidate = SynthesisOutput(
        executive_summary="Overview of flood operations.",
        recommendations=[
            SynthesisItem(
                priority=1,
                agent=AgentName.RESOURCE_COORDINATION,
                title="Evacuate to Adyar Higher Secondary School",
                body="Move residents now.",
            )
        ],
    )
    assert agent._validate_consistency(candidate, allowed) is False


@pytest.mark.asyncio
async def test_accepted_llm_briefing_is_labelled_ai_generated():
    """The model sees the deterministic draft and copies its origin; the code must relabel it."""
    event = make_event()
    agent = SynthesisAgent()
    llm_briefing = SynthesisOutput(
        executive_summary="Severe flooding in the canal and station sectors needs boat rescue.",
        recommendations=[
            SynthesisItem(
                priority=1,
                agent=AgentName.RESCUE_PLANNING,
                title="Boat rescue for the Canal Zone",
                body="Send rescue boats to the Canal Zone where residents are stranded.",
                origin="DETERMINISTIC_COMPUTATION",
            )
        ],
    )
    ctx = RunContext(
        event_id=event.id,
        agent_name=agent.agent_name,
        llm=FakeLLMClient(fixture_responses=[llm_briefing]),
    )

    out = await agent.run(ctx, make_input(event))

    assert out.executive_summary == llm_briefing.executive_summary
    assert [r.origin for r in out.recommendations] == ["AI_GENERATED"]


@pytest.mark.asyncio
async def test_deterministic_briefing_keeps_deterministic_origin():
    event = make_event()
    agent = SynthesisAgent()
    ctx = RunContext(event_id=event.id, agent_name=agent.agent_name, llm=FakeLLMClient())

    out = await agent.run(ctx, make_input(event))

    assert {r.origin for r in out.recommendations} == {"DETERMINISTIC_COMPUTATION"}
