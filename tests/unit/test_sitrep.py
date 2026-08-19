import uuid
from datetime import UTC, datetime

from app.db.models.enums import DisasterType, EventStatus, Provenance, ReportSource, SeverityLevel
from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.rag.sitrep import generate_sitrep_text
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, Polygon


def test_sitrep_text_generation() -> None:
    event_id = uuid.uuid4()
    epicenter = from_shape(Point(80.22, 13.04), srid=4326)
    zone_geom = from_shape(
        Polygon([[80.20, 13.00], [80.25, 13.00], [80.25, 13.05], [80.20, 13.05], [80.20, 13.00]]),
        srid=4326,
    )

    event = DisasterEvent(
        id=event_id,
        name="Chennai Flood 2026",
        disaster_type=DisasterType.FLOOD,
        status=EventStatus.ACTIVE,
        epicenter=epicenter,
        radius_m=5000,
        declared_at=datetime.now(UTC),
        description="High intensity monsoon inundation in Adyar river basin.",
    )

    hazard_zones = [
        HazardZone(
            id=uuid.uuid4(),
            event_id=event_id,
            label="Adyar Overflow Zone",
            hazard_type=DisasterType.FLOOD,
            severity=SeverityLevel.SEVERE,
            geom=zone_geom,
            is_impassable=True,
            active_from=datetime.now(UTC),
            source_note="Water level 1.2m on bridge",
        )
    ]

    reports = [
        IncidentReport(
            id=uuid.uuid4(),
            event_id=event_id,
            source=ReportSource.CITIZEN,
            body="Water logging inside ground floor residential complex.",
            location=epicenter,
            casualties_reported=False,
            people_affected=25,
            data_provenance=Provenance.REAL,
            reported_at=datetime.now(UTC),
        ),
        IncidentReport(
            id=uuid.uuid4(),
            event_id=event_id,
            source=ReportSource.RESPONDER,
            body="Stranded elderly citizens require boat evacuation.",
            location=epicenter,
            casualties_reported=True,
            people_affected=4,
            data_provenance=Provenance.REAL,
            reported_at=datetime.now(UTC),
        ),
    ]

    sitrep_text = generate_sitrep_text(event, hazard_zones, reports)

    assert "# SITREP: Chennai Flood 2026" in sitrep_text
    assert "**Disaster Type:** FLOOD" in sitrep_text
    assert "**Status:** ACTIVE" in sitrep_text
    assert "- Total active hazard zones: 1" in sitrep_text
    assert "- Impassable road zones: 1" in sitrep_text
    assert "[IMPASSABLE ROAD]" in sitrep_text
    assert "- Total reports received: 2" in sitrep_text
    assert "- Reports with casualties: 1" in sitrep_text
    assert "- Estimated people affected: 29" in sitrep_text
    assert "[CASUALTY REPORTED]" in sitrep_text
