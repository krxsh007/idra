from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.security import get_current_user
from app.db.models.enums import UserRole
from app.db.models.users import User
from app.db.session import get_db
from app.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_trigger_run_rbac_unauthenticated(async_client: AsyncClient) -> None:
    event_id = uuid.uuid4()
    res = await async_client.post(f"/api/v1/events/{event_id}/runs")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_trigger_run_event_not_found(async_client: AsyncClient) -> None:
    responder_id = uuid.uuid4()
    responder = User(
        id=responder_id,
        email="resp@test.com",
        password_hash="...",
        full_name="Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        non_existent_event_id = uuid.uuid4()
        res = await async_client.post(
            f"/api/v1/events/{non_existent_event_id}/runs",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_run_detail_not_found(async_client: AsyncClient) -> None:
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        random_run_id = uuid.uuid4()
        res = await async_client.get(f"/api/v1/runs/{random_run_id}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_in_progress_run_includes_agents_that_already_finished() -> None:
    """Outputs are persisted at the end of a run; the API surfaces finished agents meanwhile."""
    from datetime import UTC, datetime

    from app.db.models.enums import AgentName, AgentStatus, RunStatus
    from app.db.models.runs import AgentRun
    from app.orchestration.engine import orchestration_engine
    from app.routers.runs import _with_live_outputs

    run = AgentRun(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        status=RunStatus.RUNNING,
        needs_human_review=False,
        started_at=datetime.now(UTC),
        outputs=[],
    )
    orchestration_engine._live_outputs[str(run.id)] = [
        {
            "agent": AgentName.DISASTER_ASSESSMENT.value,
            "status": AgentStatus.SUCCESS,
            "payload": {"severity": "SEVERE"},
            "latency_ms": 1200,
        }
    ]
    try:
        detail = _with_live_outputs(run)
    finally:
        orchestration_engine._live_outputs.pop(str(run.id), None)

    assert [o.agent for o in detail.outputs] == [AgentName.DISASTER_ASSESSMENT]
    assert detail.outputs[0].payload == {"severity": "SEVERE"}

    # Once the run has finished, only persisted outputs are returned.
    run.status = RunStatus.COMPLETED
    assert _with_live_outputs(run).outputs == []
