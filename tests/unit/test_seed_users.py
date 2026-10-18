from scripts.seed.seed_users import DEFAULT_USERS, hash_password, verify_password


def test_password_hashing() -> None:
    raw_password = "secure_test_password_123"
    hashed = hash_password(raw_password)
    assert hashed != raw_password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(raw_password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_default_users_configured() -> None:
    assert len(DEFAULT_USERS) == 3
    emails = [str(u["email"]) for u in DEFAULT_USERS]
    roles = [
        str(u["role"].value if hasattr(u["role"], "value") else u["role"]) for u in DEFAULT_USERS
    ]

    assert "admin@example.com" in emails
    assert "responder1@example.com" in emails
    assert "responder2@example.com" in emails
    assert "ADMIN" in roles
    assert roles.count("RESPONDER") == 2
