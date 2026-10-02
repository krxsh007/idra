from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.ratelimit import rate_limiter
from app.db.session import get_db
from app.main import app
from app.rag.retriever import RetrievedChunk
from app.schemas.assistant import CitizenAgentLLMOutput
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_assistant_query_normal_flow(async_client: AsyncClient) -> None:
    session_id = uuid.uuid4()
    payload = {
        "query": "What precautions should I take during heavy flood warnings in Chennai?",
        "session_id": str(session_id),
        "location": {"lon": 80.22, "lat": 12.98},
    }

    dummy_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_title="NDMA SOP Flood Guidelines",
        source_type="SOP",
        hazard_types=[],
        section_path="Advisories",
        content="Keep an emergency kit ready and disconnect electrical power before evacuating.",
        vector_score=0.85,
        lexical_score=0.75,
        hybrid_score=0.82,
        published_at=None,
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with (
            patch(
                "app.agents.citizen_assistance.retriever.search", new_callable=AsyncMock
            ) as mock_search,
            patch("app.llm.fake.FakeLLMClient.structured", new_callable=AsyncMock) as mock_llm,
        ):
            mock_search.return_value = [dummy_chunk]
            mock_llm.return_value = CitizenAgentLLMOutput(
                answer="Disconnect electrical mains and store emergency supplies on upper floors.",
                cited_chunk_ids=[str(dummy_chunk.chunk_id)],
            )

            res = await async_client.post("/api/v1/assistant/query", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == str(session_id)
        assert "electrical mains" in data["answer"].lower()
        assert data["escalated"] is False
        assert data["safety_flag"] == "NONE"
        assert "DISCLAIMER" in data["disclaimer"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_assistant_query_urgent_escalation(async_client: AsyncClient) -> None:
    session_id = uuid.uuid4()
    payload = {
        "query": (
            "We are trapped inside house and water is rising fast to ceiling, "
            "send rescue boat immediately!"
        ),
        "session_id": str(session_id),
        "location": {"lon": 80.20, "lat": 13.00},
    }

    dummy_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_title="NDMA Rescue SOP",
        source_type="SOP",
        hazard_types=[],
        section_path="Trapped Evacuation",
        content="Call emergency responders immediately and move to highest point.",
        vector_score=0.8,
        lexical_score=0.7,
        hybrid_score=0.77,
        published_at=None,
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with (
            patch(
                "app.agents.citizen_assistance.retriever.search", new_callable=AsyncMock
            ) as mock_search,
            patch("app.llm.fake.FakeLLMClient.structured", new_callable=AsyncMock) as mock_llm,
        ):
            mock_search.return_value = [dummy_chunk]
            mock_llm.return_value = CitizenAgentLLMOutput(
                answer="Stay on highest roof level. Do not enter moving water.",
                cited_chunk_ids=[str(dummy_chunk.chunk_id)],
            )

            res = await async_client.post("/api/v1/assistant/query", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["escalated"] is True
        assert data["safety_flag"] == "LIFE_THREATENING"
        assert "112" in data["answer"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_assistant_rate_limiting(async_client: AsyncClient) -> None:
    # Reset or set bucket for test client to 0 tokens
    key = "assistant:127.0.0.1"
    rate_limiter.buckets[key].tokens = 0.0

    payload = {
        "query": "Where can I get clean water in my colony?",
    }
    res = await async_client.post("/api/v1/assistant/query", json=payload)
    assert res.status_code == 429
    assert "Retry-After" in res.headers
