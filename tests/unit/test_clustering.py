from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models.enums import Provenance, ReportSource, SeverityLevel
from app.gis.clustering import classify_cluster_accessibility, cluster_incident_reports
from app.schemas.events import EpicenterPoint
from app.schemas.hazards import GeoJSONPolygon, HazardZoneResponse
from app.schemas.reports import ReportResponse


def make_report(
    lon: float, lat: float, casualties: bool = False, people: int = 10
) -> ReportResponse:
    return ReportResponse(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        source=ReportSource.CITIZEN,
        body="Flood report",
        location=EpicenterPoint(lon=lon, lat=lat),
        casualties_reported=casualties,
        people_affected=people,
        data_provenance=Provenance.SIMULATED,
        reported_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_hazard(coords: list[list[float]], is_impassable: bool = True) -> HazardZoneResponse:
    return HazardZoneResponse(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        label="Hazard Alpha",
        hazard_type="FLOOD",
        severity=SeverityLevel.HIGH,
        geometry=GeoJSONPolygon(type="Polygon", coordinates=[coords]),
        is_impassable=is_impassable,
        active_from=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def test_cluster_incident_reports_dbscan():
    # Two reports close to each other (< 100m)
    r1 = make_report(80.2000, 13.0000, people=15)
    r2 = make_report(80.2005, 13.0002, casualties=True, people=25)
    # One distant report (> 2km away)
    r3 = make_report(80.2500, 13.0500, people=30)

    clusters = cluster_incident_reports([r1, r2, r3], hazard_zones=[], eps_m=500.0, min_points=2)
    assert len(clusters) == 2
    # Cluster containing r1 and r2
    c_group = next(c for c in clusters if len(c.reports) == 2)
    assert c_group.people_estimate == 40
    assert c_group.has_casualties is True
    assert c_group.accessibility == "ACCESSIBLE"


def test_classify_cluster_accessibility():
    # Box around (80.20, 13.00)
    polygon_coords = [
        [80.190, 12.990],
        [80.210, 12.990],
        [80.210, 13.010],
        [80.190, 13.010],
        [80.190, 12.990],
    ]
    hazard = make_hazard(polygon_coords, is_impassable=True)

    # 1. Point inside polygon -> BLOCKED
    assert classify_cluster_accessibility(80.200, 13.000, [hazard]) == "BLOCKED"

    # 2. Point ~150m outside north edge (13.010 + 0.001 deg is ~111m) -> CONSTRAINED
    assert classify_cluster_accessibility(80.200, 13.011, [hazard]) == "CONSTRAINED"

    # 3. Point ~2km away -> ACCESSIBLE
    assert classify_cluster_accessibility(80.200, 13.030, [hazard]) == "ACCESSIBLE"

    # 4. Passable hazard zone -> ACCESSIBLE even if inside
    hazard_passable = make_hazard(polygon_coords, is_impassable=False)
    assert classify_cluster_accessibility(80.200, 13.000, [hazard_passable]) == "ACCESSIBLE"
