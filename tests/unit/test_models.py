from typing import cast

from app.db.models import (
    AgentName,
    Base,
    DisasterEvent,
    DisasterType,
    EventStatus,
    Facility,
    FacilityType,
    HazardZone,
    IncidentReport,
    Provenance,
    Recommendation,
    Resource,
    ResourceAllocation,
    ResourceKind,
    SeverityLevel,
    UserRole,
    VerificationStatus,
)
from sqlalchemy import CheckConstraint, Table


def test_all_tables_registered_in_metadata() -> None:
    expected_tables = {
        "users",
        "disaster_events",
        "incident_reports",
        "hazard_zones",
        "facilities",
        "facility_capacity_log",
        "resources",
        "road_nodes",
        "road_edges",
        "kb_documents",
        "kb_chunks",
        "agent_runs",
        "agent_outputs",
        "recommendations",
        "recommendation_citations",
        "routes",
        "resource_allocations",
        "chat_sessions",
        "chat_messages",
        "audit_log",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(
        actual_tables
    ), f"Missing tables: {expected_tables - actual_tables}"


def test_safety_check_constraints_registered() -> None:
    # 1. disaster_events constraints
    event_table = cast(Table, DisasterEvent.__table__)
    event_constraints = [
        str(c.name) for c in event_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("radius_m" in name for name in event_constraints)
    assert any("closed" in name for name in event_constraints)

    # 2. incident_reports constraints
    report_table = cast(Table, IncidentReport.__table__)
    report_constraints = [
        str(c.name) for c in report_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("body" in name for name in report_constraints)
    assert any("people_affected" in name for name in report_constraints)

    # 3. hazard_zones constraints
    hazard_table = cast(Table, HazardZone.__table__)
    hazard_constraints = [
        str(c.name) for c in hazard_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("active" in name for name in hazard_constraints)

    # 4. facilities constraints
    facility_table = cast(Table, Facility.__table__)
    facility_constraints = [
        str(c.name) for c in facility_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("total_capacity" in name for name in facility_constraints)
    assert any("current_occupancy" in name for name in facility_constraints)
    assert any("occupancy" in name for name in facility_constraints)

    # 5. resources constraints
    resource_table = cast(Table, Resource.__table__)
    resource_constraints = [
        str(c.name) for c in resource_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("quantity_total" in name for name in resource_constraints)
    assert any("quantity_free" in name for name in resource_constraints)

    # 6. recommendations constraints
    rec_table = cast(Table, Recommendation.__table__)
    rec_constraints = [str(c.name) for c in rec_table.constraints if isinstance(c, CheckConstraint)]
    assert any("priority" in name for name in rec_constraints)
    assert any("origin" in name for name in rec_constraints)
    assert any("confidence" in name for name in rec_constraints)
    assert any("verified" in name for name in rec_constraints)

    # 7. resource_allocations constraints
    alloc_table = cast(Table, ResourceAllocation.__table__)
    alloc_constraints = [
        str(c.name) for c in alloc_table.constraints if isinstance(c, CheckConstraint)
    ]
    assert any("quantity" in name for name in alloc_constraints)
    assert any("priority" in name for name in alloc_constraints)


def test_enum_members() -> None:
    assert set(UserRole) == {UserRole.ADMIN, UserRole.RESPONDER, UserRole.CITIZEN}
    assert set(DisasterType) == {
        DisasterType.FLOOD,
        DisasterType.EARTHQUAKE,
        DisasterType.CYCLONE,
        DisasterType.LANDSLIDE,
        DisasterType.WILDFIRE,
        DisasterType.OTHER,
    }
    assert set(SeverityLevel) == {
        SeverityLevel.LOW,
        SeverityLevel.MODERATE,
        SeverityLevel.HIGH,
        SeverityLevel.SEVERE,
    }
    assert set(EventStatus) == {EventStatus.ACTIVE, EventStatus.MONITORING, EventStatus.CLOSED}
    assert set(FacilityType) == {FacilityType.HOSPITAL, FacilityType.SHELTER}
    assert set(Provenance) == {Provenance.REAL, Provenance.SIMULATED, Provenance.SYNTHETIC}
    assert set(VerificationStatus) == {
        VerificationStatus.PENDING,
        VerificationStatus.VERIFIED,
        VerificationStatus.OVERRIDDEN,
        VerificationStatus.REJECTED,
    }
    assert len(AgentName) == 8
    assert len(ResourceKind) == 8
