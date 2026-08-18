import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_api_v1_health_check(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_deep_health_check(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/health/deep")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert "components" in data
    assert "database" in data["components"]
    assert "road_graph" in data["components"]
    assert "llm" in data["components"]


@pytest.mark.asyncio
async def test_custom_request_id_header(async_client: AsyncClient) -> None:
    custom_id = "test-req-id-12345"
    response = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id
