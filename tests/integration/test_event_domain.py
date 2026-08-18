import uuid

import pytest
from app.core.security import get_current_user
from app.db.models.enums import UserRole
from app.db.models.users import User
from app.main import app
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_login_validation(async_client: AsyncClient) -> None:
    # Invalid login body (missing password and bad email format)
    res = await async_client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_event_creation_bbox_rejection(async_client: AsyncClient) -> None:
    # Mock current user as Admin
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        email="admin@test.com",
        password_hash="...",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        # Outside Chennai Core bbox (Delhi coordinates)
        payload = {
            "name": "Delhi Storm",
            "disaster_type": "FLOOD",
            "epicenter": {"lon": 77.20, "lat": 28.61},
            "radius_m": 5000,
            "description": "Outside bbox test",
        }
        res = await async_client.post(
            "/api/v1/events",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "outside the configured study area" in data["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_event_creation_rbac_rejection(async_client: AsyncClient) -> None:
    # Mock current user as Responder (not Admin)
    responder_id = uuid.uuid4()
    responder_user = User(
        id=responder_id,
        email="resp@test.com",
        password_hash="...",
        full_name="Responder",
        role=UserRole.RESPONDER,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: responder_user

    try:
        payload = {
            "name": "Chennai Floods",
            "disaster_type": "FLOOD",
            "epicenter": {"lon": 80.22, "lat": 13.04},
            "radius_m": 5000,
        }
        res = await async_client.post(
            "/api/v1/events",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_report_validation(async_client: AsyncClient) -> None:
    # Report with body < 5 characters
    res = await async_client.post(
        "/api/v1/reports",
        json={
            "body": "Hi",
            "location": {"lon": 80.22, "lat": 13.04},
        },
    )
    assert res.status_code == 400

    # Report outside bbox
    res = await async_client.post(
        "/api/v1/reports",
        json={
            "body": "Flooding observed on highway",
            "location": {"lon": 72.87, "lat": 19.07},
        },
    )
    assert res.status_code == 400
    assert "outside the configured study area" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_hazard_zone_polygon_validation(async_client: AsyncClient) -> None:
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        email="admin@test.com",
        password_hash="...",
        full_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        # Invalid polygon (unclosed / fewer than 4 coords)
        payload = {
            "event_id": str(uuid.uuid4()),
            "label": "Zone Alpha",
            "hazard_type": "FLOOD",
            "severity": "HIGH",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.20, 13.00],
                        [80.25, 13.00],
                        [80.20, 13.05],
                    ]
                ],
            },
        }
        res = await async_client.post(
            "/api/v1/hazard-zones",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert res.status_code == 400
    finally:
        app.dependency_overrides.clear()
