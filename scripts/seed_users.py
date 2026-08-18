import asyncio
import os
import sys
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure api directory and project root are on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API_DIR = os.path.join(PROJECT_ROOT, "api")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.core.config import settings  # noqa: E402
from app.db.models.enums import UserRole  # noqa: E402
from app.db.models.users import User  # noqa: E402


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


DEFAULT_USERS = [
    {
        "email": settings.SEED_ADMIN_EMAIL,
        "password": settings.SEED_ADMIN_PASSWORD,
        "full_name": "Emergency Administrator",
        "role": UserRole.ADMIN,
    },
    {
        "email": "responder1@example.com",
        "password": "responder_password_1",
        "full_name": "Field Responder Alpha",
        "role": UserRole.RESPONDER,
    },
    {
        "email": "responder2@example.com",
        "password": "responder_password_2",
        "full_name": "Field Responder Bravo",
        "role": UserRole.RESPONDER,
    },
]


async def seed_users(session: AsyncSession | None = None) -> list[User]:
    """Seed default users into the database idempotently."""
    close_session = False
    if session is None:
        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        session = session_factory()
        close_session = True

    created_users: list[User] = []
    try:
        for user_data in DEFAULT_USERS:
            stmt = select(User).where(User.email == user_data["email"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing is None:
                user = User(
                    email=user_data["email"],
                    password_hash=hash_password(user_data["password"]),
                    full_name=user_data["full_name"],
                    role=user_data["role"],
                    is_active=True,
                )
                session.add(user)
                created_users.append(user)
                print(f"[SEED] Created user: {user.email} (Role: {user.role.value})")
            else:
                print(f"[SEED] User already exists: {existing.email} (Skipped)")

        await session.commit()
    finally:
        if close_session:
            await session.close()

    return created_users


if __name__ == "__main__":
    print(f"Connecting to database: {settings.DATABASE_URL.split('@')[-1]}")
    asyncio.run(seed_users())
