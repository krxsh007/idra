from __future__ import annotations

import uuid

import pytest
from app.core.security import get_current_user
from app.db.models.enums import UserRole
from app.db.models.users import User
from app.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_eval_endpoint_citizen_forbidden(async_client: AsyncClient) -> None:
    """Verify CITIZEN role is forbidden from accessing /api/v1/metrics/eval."""
    citizen = User(
        id=uuid.uuid4(),
        email="citizen@test.com",
        password_hash="...",
        full_name="Citizen User",
        role=UserRole.CITIZEN,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: citizen

    try:
        res = await async_client.get(
            "/api/v1/metrics/eval",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_metrics_eval_endpoint_responder_success(async_client: AsyncClient) -> None:
    """Verify RESPONDER role can retrieve evaluation results via /api/v1/metrics/eval."""
    responder = User(
        id=uuid.uuid4(),
        email="responder@test.com",
        password_hash="...",
        full_name="Responder User",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: responder

    try:
        res = await async_client.get(
            "/api/v1/metrics/eval",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "summary" in body
        assert body["summary"]["total_automated_metrics"] == 34
        assert "suites" in body
        for suite in ("rag_eval", "agent_eval", "gis_eval", "system_eval", "ui_study"):
            assert suite in body["suites"]
    finally:
        app.dependency_overrides.clear()
