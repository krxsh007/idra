from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.security import get_current_user
from app.db.models.enums import AgentName, UserRole, VerificationStatus
from app.db.models.runs import Recommendation
from app.db.models.users import User
from app.db.session import get_db
from app.main import app
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_verify_rbac_responder_forbidden(async_client: AsyncClient) -> None:
    responder = User(
        id=uuid.uuid4(),
        email="resp@test.com",
        password_hash="...",
        full_name="Responder User",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: responder

    try:
        rec_id = uuid.uuid4()
        res = await async_client.post(
            f"/api/v1/recommendations/{rec_id}/verify",
            json={"action": "VERIFIED"},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_override_without_note_bad_request(async_client: AsyncClient) -> None:
    admin = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash="...",
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        rec_id = uuid.uuid4()
        res = await async_client.post(
            f"/api/v1/recommendations/{rec_id}/verify",
            json={"action": "OVERRIDDEN", "note": ""},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 400
        assert "Note is required" in res.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_already_verified_conflict(async_client: AsyncClient) -> None:
    admin = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash="...",
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    rec_id = uuid.uuid4()
    existing_rec = Recommendation(
        id=rec_id,
        run_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        agent=AgentName.SHELTER_ALLOCATION,
        priority=1,
        title="Evacuate to Community Hall",
        body="Zone A requires immediate shelter.",
        origin="AI_GENERATED",
        verification_status=VerificationStatus.VERIFIED,  # already verified
        verified_by=admin.id,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_rec
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        res = await async_client.post(
            f"/api/v1/recommendations/{rec_id}/verify",
            json={"action": "VERIFIED"},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 409
        assert "already been verified" in res.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_success_with_audit_log(async_client: AsyncClient) -> None:
    admin = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash="...",
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    rec_id = uuid.uuid4()
    pending_rec = Recommendation(
        id=rec_id,
        run_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        agent=AgentName.SYNTHESIS,
        priority=1,
        title="Deploy Rescue Boats to Sector 4",
        body="High water levels require boat deployment.",
        origin="AI_GENERATED",
        verification_status=VerificationStatus.PENDING,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = pending_rec
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        res = await async_client.post(
            f"/api/v1/recommendations/{rec_id}/verify",
            json={"action": "VERIFIED", "note": "Confirmed on site."},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["verification_status"] == "VERIFIED"
        assert pending_rec.verified_by == admin.id
        assert pending_rec.verification_status == VerificationStatus.VERIFIED
        assert mock_db.commit.called
        assert mock_db.add.called  # audit_log added
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_recommendations(async_client: AsyncClient) -> None:
    responder = User(
        id=uuid.uuid4(),
        email="resp@test.com",
        password_hash="...",
        full_name="Responder User",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    rec = Recommendation(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        agent=AgentName.SHELTER_ALLOCATION,
        priority=1,
        title="Open Shelters",
        body="Open shelters immediately.",
        origin="AI_GENERATED",
        verification_status=VerificationStatus.PENDING,
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [rec]
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        res = await async_client.get(
            "/api/v1/recommendations",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Open Shelters"
    finally:
        app.dependency_overrides.clear()


async def _list_sql(async_client: AsyncClient, query: str) -> str:
    """Call the list endpoint with a mocked DB and return the SQL it executed."""
    responder = User(
        id=uuid.uuid4(),
        email="resp@test.com",
        password_hash="...",
        full_name="Responder User",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    mock_db = AsyncMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_current_user] = lambda: responder
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        res = await async_client.get(
            f"/api/v1/recommendations{query}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 200
    finally:
        app.dependency_overrides.clear()

    stmt = mock_db.execute.call_args.args[0]
    return str(stmt.compile()).lower()


@pytest.mark.asyncio
async def test_list_recommendations_by_event_defaults_to_latest_run(
    async_client: AsyncClient,
) -> None:
    sql = await _list_sql(async_client, f"?event_id={uuid.uuid4()}")
    # Only the event's most recent run, not every run's briefing accumulated together.
    assert "recommendations.run_id = (select" in sql
    assert "order by recommendations.created_at desc" in sql
    assert "limit" in sql


@pytest.mark.asyncio
async def test_list_recommendations_explicit_run_id(async_client: AsyncClient) -> None:
    sql = await _list_sql(async_client, f"?event_id={uuid.uuid4()}&run_id={uuid.uuid4()}")
    assert "recommendations.run_id = :run_id_1" in sql
    assert "limit" not in sql
