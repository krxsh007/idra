import uuid

import pytest
from app.core.errors import AppException
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    require_admin,
    require_responder,
    verify_password,
)
from app.db.models.enums import UserRole
from app.db.models.users import User


def test_password_hash_and_verify() -> None:
    pw = "SuperSecret_2026!"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_create_and_decode() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(subject=user_id, role=UserRole.ADMIN)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "ADMIN"
    assert "exp" in payload


@pytest.mark.asyncio
async def test_require_admin() -> None:
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash="...",
        full_name="Admin",
        role=UserRole.ADMIN,
    )
    res = await require_admin(current_user=admin_user)
    assert res.role == UserRole.ADMIN

    responder_user = User(
        id=uuid.uuid4(),
        email="resp@test.com",
        password_hash="...",
        full_name="Responder",
        role=UserRole.RESPONDER,
    )
    with pytest.raises(AppException) as exc_info:
        await require_admin(current_user=responder_user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_responder() -> None:
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash="...",
        full_name="Admin",
        role=UserRole.ADMIN,
    )
    assert (await require_responder(current_user=admin_user)).role == UserRole.ADMIN

    responder_user = User(
        id=uuid.uuid4(),
        email="resp@test.com",
        password_hash="...",
        full_name="Responder",
        role=UserRole.RESPONDER,
    )
    assert (await require_responder(current_user=responder_user)).role == UserRole.RESPONDER

    citizen_user = User(
        id=uuid.uuid4(),
        email="cit@test.com",
        password_hash="...",
        full_name="Citizen",
        role=UserRole.CITIZEN,
    )
    with pytest.raises(AppException) as exc_info:
        await require_responder(current_user=citizen_user)
    assert exc_info.value.status_code == 403
