import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.db.models.enums import DisasterType, EventStatus, FacilityType, Provenance
from app.db.models.events import DisasterEvent
from app.db.models.facilities import Facility
from app.db.session import get_db
from app.main import app
from geoalchemy2.shape import from_shape
from httpx import AsyncClient
from shapely.geometry import Point


@pytest.mark.asyncio
async def test_deep_health_check_road_graph_status(async_client: AsyncClient) -> None:
    res = await async_client.get("/api/v1/health/deep")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "road_graph" in data["components"]
    rg = data["components"]["road_graph"]
    assert rg["status"] == "ok"
    assert rg["details"]["nodes"] > 1000
    assert rg["details"]["edges"] > 3000


@pytest.mark.asyncio
async def test_facilities_list_endpoint(async_client: AsyncClient) -> None:
    fac_id = uuid.uuid4()
    loc = from_shape(Point(80.279, 13.081), srid=4326)
    mock_facility = Facility(
        id=fac_id,
        external_ref="HOSP-001",
        name="Test General Hospital",
        facility_type=FacilityType.HOSPITAL,
        location=loc,
        address="Central Road",
        total_capacity=1000,
        current_occupancy=400,
        specializations=["Trauma"],
        has_generator=True,
        wheelchair_access=True,
        contact_phone="+91-44-12345678",
        is_operational=True,
        location_provenance=Provenance.REAL,
        capacity_provenance=Provenance.SIMULATED,
        updated_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    # Mock count query and items query
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [mock_facility]

    mock_session.execute.side_effect = [count_result, items_result]

    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        res = await async_client.get("/api/v1/facilities?limit=10")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["name"] == "Test General Hospital"
        assert item["facility_type"] == "HOSPITAL"
        assert item["location_provenance"] == "REAL"
        assert item["capacity_provenance"] == "SIMULATED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_event_geojson_not_found(async_client: AsyncClient) -> None:
    mock_session = AsyncMock()
    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = res_mock

    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        res = await async_client.get(f"/api/v1/events/{fake_uuid}/geojson")
        assert res.status_code == 404
        data = res.json()
        assert data["error"]["code"] == "NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_event_geojson_feature_provenance(async_client: AsyncClient) -> None:
    event_id = uuid.uuid4()
    epicenter = from_shape(Point(80.225, 13.050), srid=4326)
    mock_event = DisasterEvent(
        id=event_id,
        name="Chennai Monsoon Event",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=epicenter,
        radius_m=6000,
        declared_at=datetime.now(UTC),
    )

    mock_session = AsyncMock()
    # Mock queries: 1) event, 2) hazard zones, 3) reports, 4) facilities
    ev_res = MagicMock()
    ev_res.scalar_one_or_none.return_value = mock_event

    empty_list_mock = MagicMock()
    empty_list_mock.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [ev_res, empty_list_mock, empty_list_mock, empty_list_mock]

    app.dependency_overrides[get_db] = lambda: mock_session

    try:
        res = await async_client.get(f"/api/v1/events/{event_id}/geojson")
        assert res.status_code == 200
        data = res.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        epicenter_feat = data["features"][0]
        assert epicenter_feat["properties"]["feature_type"] == "event_epicenter"
        assert epicenter_feat["properties"]["data_provenance"] == "REAL"
    finally:
        app.dependency_overrides.clear()
