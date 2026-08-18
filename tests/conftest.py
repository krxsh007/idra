import os
import sys
from collections.abc import AsyncGenerator
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure project root and api directory are on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API_DIR = os.path.join(PROJECT_ROOT, "api")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
