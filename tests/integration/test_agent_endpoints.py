from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.security import get_current_user
from app.db.models.enums import (
    AgentName,
    UserRole,
    VerificationStatus,
)
from app.db.models.runs import Recommendation, RecommendationCitation
from app.db.models.users import User
from app.db.session import get_db
from app.main import app
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def responder_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="responder@test.com",
        password_hash="...",
        full_name="Rescue Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_planning_endpoint(async_client: AsyncClient, responder_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: responder_user
    mock_db = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        payload = {
            "event": {
                "id": str(uuid.uuid4()),
                "name": "Monsoon Overflow",
                "disaster_type": "FLOOD",
                "status": "ACTIVE",
                "epicenter": {"lon": 80.20, "lat": 13.00},
                "radius_m": 5000,
                "declared_at": datetime.now(UTC).isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
            },
            "reports": [
                {
                    "id": str(uuid.uuid4()),
                    "source": "CITIZEN",
                    "body": "Submerged street",
                    "location": {"lon": 80.201, "lat": 13.001},
                    "casualties_reported": True,
                    "people_affected": 25,
                    "data_provenance": "SIMULATED",
                    "reported_at": datetime.now(UTC).isoformat(),
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ],
            "hazard_zones": [],
            "assessment_severity": "HIGH",
            "assessment_summary": "Inundated corridor with casualties.",
        }

        with patch(
            "app.agents.rescue_planning.retriever.search", new_callable=AsyncMock, return_value=[]
        ):
            res = await async_client.post(
                "/api/v1/agents/planning",
                json=payload,
                headers={"Authorization": "Bearer fake-token"},
            )
        assert res.status_code == 200
        data = res.json()
        assert "prioritized_zones" in data
        assert "operation_sequence" in data
        assert len(data["prioritized_zones"]) >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_synthesis_endpoint(async_client: AsyncClient, responder_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: responder_user
    mock_db = AsyncMock(spec=AsyncSession)
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        payload = {
            "event": {
                "id": str(uuid.uuid4()),
                "name": "Cyclone Vardah Response",
                "disaster_type": "CYCLONE",
                "status": "ACTIVE",
                "epicenter": {"lon": 80.25, "lat": 13.05},
                "radius_m": 8000,
                "declared_at": datetime.now(UTC).isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
            },
            "assessment_output": {
                "severity": "HIGH",
                "estimated_people_affected": 150,
            },
            "planning_output": {
                "prioritized_zones": [
                    {
                        "zone_label": "Sector North",
                        "centroid": {"lon": 80.25, "lat": 13.05},
                        "priority": 1,
                        "people_estimate": 100,
                        "accessibility": "BLOCKED",
                        "rationale": "High storm surge",
                    }
                ]
            },
            "facilities_output": {
                "recommended_shelters": [
                    {
                        "facility_id": str(uuid.uuid4()),
                        "name": "Community Relief Center",
                        "available_capacity": 500,
                        "distance_m": 800,
                    }
                ]
            },
        }

        res = await async_client.post(
            "/api/v1/agents/synthesis",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "executive_summary" in data
        assert "recommendations" in data
        assert len(data["recommendations"]) >= 1
        assert "disclaimer" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_event_recommendations_endpoint(async_client: AsyncClient) -> None:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    event_id = uuid.uuid4()
    run_id = uuid.uuid4()

    rec = Recommendation(
        id=uuid.uuid4(),
        run_id=run_id,
        event_id=event_id,
        agent=AgentName.RESCUE_PLANNING,
        priority=1,
        title="Immediate Rescue Dispatch",
        body="Deploy rescue boats to inundated sector.",
        origin="AI_GENERATED",
        confidence=0.95,
        verification_status=VerificationStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    rec.citations = [
        RecommendationCitation(
            id=1,
            recommendation_id=rec.id,
            chunk_id=uuid.uuid4(),
            document_title="NDMA Guidelines",
            quoted_span="Life-safety priority",
            relevance_score=0.9,
        )
    ]

    mock_result.scalars.return_value.all.return_value = [rec]
    mock_db.execute.return_value = mock_result
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        res = await async_client.get(f"/api/v1/events/{event_id}/recommendations")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["priority"] == 1
        assert data[0]["agent"] == "RESCUE_PLANNING"
        assert len(data[0]["citations"]) == 1
        assert data[0]["citations"][0]["document_title"] == "NDMA Guidelines"
    finally:
        app.dependency_overrides.clear()
