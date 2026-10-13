from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.agents.base import RunContext
from app.agents.facilities import FacilityRecommendationAgent
from app.db.models.enums import AgentName, DisasterType, FacilityType, SeverityLevel
from app.db.models.facilities import Facility
from app.gis.spatial import FacilityDistanceResult
from app.llm.fake import FakeLLMClient
from app.schemas.agents.facilities import FacilityRecommendationInput
from app.schemas.events import EpicenterPoint, EventResponse


def make_sample_facility(
    name: str,
    fac_type: FacilityType,
    total_cap: int,
    curr_occ: int,
    has_gen: bool = True,
    wheelchair: bool = True,
) -> Facility:
    f = Facility(
        id=uuid.uuid4(),
        name=name,
        facility_type=fac_type,
        total_capacity=total_cap,
        current_occupancy=curr_occ,
        has_generator=has_gen,
        wheelchair_access=wheelchair,
        specializations=["Trauma", "ICU"] if fac_type == FacilityType.HOSPITAL else [],
        is_operational=True,
    )
    return f


@pytest.mark.asyncio
async def test_facility_agent_no_db_fallback():
    agent = FacilityRecommendationAgent()
    event = EventResponse(
        id=uuid.uuid4(),
        name="Test Flood",
        disaster_type=DisasterType.FLOOD,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.25, lat=13.04),
        radius_m=3000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    input_data = FacilityRecommendationInput(
        event=event,
        assessment_summary="Severe flooding",
        severity=SeverityLevel.SEVERE,
        epicenter=event.epicenter,
    )
    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.HOSPITAL_RECOMMENDATION,
        db=None,
        llm=FakeLLMClient(),
    )

    out = await agent.run(ctx, input_data)
    assert out.total_hospital_capacity_available == 0
    assert out.total_shelter_capacity_available == 0
    assert len(out.recommended_hospitals) == 0


def _build_inputs():
    agent = FacilityRecommendationAgent()
    event = EventResponse(
        id=uuid.uuid4(),
        name="Chennai Cyclone",
        disaster_type=DisasterType.CYCLONE,
        status="ACTIVE",  # type: ignore[arg-type]
        epicenter=EpicenterPoint(lon=80.22, lat=12.98),
        radius_m=4000,
        declared_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    input_data = FacilityRecommendationInput(
        event=event,
        assessment_summary="High wind damage and urban inundation",
        severity=SeverityLevel.HIGH,
        epicenter=event.epicenter,
    )

    hosp1 = make_sample_facility("Apollo Greams", FacilityType.HOSPITAL, 500, 300, has_gen=True)
    hosp2 = make_sample_facility("Govt General", FacilityType.HOSPITAL, 1000, 950, has_gen=False)
    sh1 = make_sample_facility("Velachery Relief Camp", FacilityType.SHELTER, 300, 50, has_gen=True)
    return agent, event, input_data, hosp1, hosp2, sh1


@pytest.mark.asyncio
async def test_facility_agent_recommends_and_sorts_with_db():
    agent, event, input_data, hosp1, hosp2, sh1 = _build_inputs()
    from sqlalchemy.ext.asyncio import AsyncSession

    mock_db = AsyncMock(spec=AsyncSession)
    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.HOSPITAL_RECOMMENDATION,
        db=mock_db,
        llm=FakeLLMClient(),
    )

    with (
        patch("app.agents.facilities.get_nearby_facilities", new_callable=AsyncMock) as mock_get,
        patch(
            "app.agents.facilities.get_facility_ids_in_hazard_zones",
            new_callable=AsyncMock,
            return_value=set(),
        ),
    ):
        # First call for hospitals, second call for shelters
        mock_get.side_effect = [
            [
                FacilityDistanceResult(facility=hosp1, distance_m=1200.0),
                FacilityDistanceResult(facility=hosp2, distance_m=800.0),
            ],
            [
                FacilityDistanceResult(facility=sh1, distance_m=500.0),
            ],
        ]

        out = await agent.run(ctx, input_data)

        assert len(out.recommended_hospitals) == 2
        # Prioritizes generator: hosp1 has generator so sorted first even though 1200m vs 800m
        assert out.recommended_hospitals[0].name == "Apollo Greams"
        assert out.recommended_hospitals[0].available_capacity == 200
        assert out.recommended_hospitals[1].name == "Govt General"
        assert out.recommended_hospitals[1].available_capacity == 50

        assert len(out.recommended_shelters) == 1
        assert out.recommended_shelters[0].name == "Velachery Relief Camp"
        assert out.recommended_shelters[0].available_capacity == 250
        assert out.total_hospital_capacity_available == 250
        assert out.total_shelter_capacity_available == 250


@pytest.mark.asyncio
async def test_facility_agent_excludes_facilities_inside_hazard_zones():
    agent, event, input_data, hosp1, hosp2, sh1 = _build_inputs()
    from sqlalchemy.ext.asyncio import AsyncSession

    ctx = RunContext(
        event_id=event.id,
        agent_name=AgentName.HOSPITAL_RECOMMENDATION,
        db=AsyncMock(spec=AsyncSession),
        llm=FakeLLMClient(),
    )

    with (
        patch("app.agents.facilities.get_nearby_facilities", new_callable=AsyncMock) as mock_get,
        patch(
            "app.agents.facilities.get_facility_ids_in_hazard_zones",
            new_callable=AsyncMock,
            return_value={hosp1.id, sh1.id},
        ),
    ):
        mock_get.side_effect = [
            [
                FacilityDistanceResult(facility=hosp1, distance_m=1200.0),
                FacilityDistanceResult(facility=hosp2, distance_m=800.0),
            ],
            [FacilityDistanceResult(facility=sh1, distance_m=500.0)],
        ]

        out = await agent.run(ctx, input_data)

    assert [h.name for h in out.recommended_hospitals] == ["Govt General"]
    assert out.recommended_shelters == []
    assert "inside hazard zones" in out.rationale
