import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, utc_now
from app.db.models.enums import DisasterType, EventStatus, Provenance, ReportSource, SeverityLevel


class DisasterEvent(Base):
    __tablename__ = "disaster_events"
    __table_args__ = (
        CheckConstraint("radius_m BETWEEN 100 AND 50000", name="ck_disaster_events_radius_m"),
        CheckConstraint(
            "closed_at IS NULL OR closed_at >= declared_at",
            name="ck_disaster_events_closed_after_declared",
        ),
        Index("idx_events_epicenter", "epicenter", postgresql_using="gist"),
        Index("idx_events_status", "status", text("declared_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    disaster_type: Mapped[DisasterType] = mapped_column(
        PgEnum(DisasterType, name="disaster_type", create_type=False),
        nullable=False,
    )
    status: Mapped[EventStatus] = mapped_column(
        PgEnum(EventStatus, name="event_status", create_type=False),
        nullable=False,
        default=EventStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    epicenter: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    declared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    reports: Mapped[list["IncidentReport"]] = relationship(
        "IncidentReport", back_populates="event", cascade="all, delete-orphan"
    )
    hazard_zones: Mapped[list["HazardZone"]] = relationship(
        "HazardZone", back_populates="event", cascade="all, delete-orphan"
    )


class IncidentReport(Base):
    __tablename__ = "incident_reports"
    __table_args__ = (
        CheckConstraint(
            "char_length(body) BETWEEN 5 AND 4000",
            name="ck_incident_reports_body_length",
        ),
        CheckConstraint(
            "people_affected IS NULL OR people_affected >= 0",
            name="ck_incident_reports_people_affected",
        ),
        Index("idx_reports_location", "location", postgresql_using="gist"),
        Index("idx_reports_event", "event_id", text("reported_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=True,
    )
    source: Mapped[ReportSource] = mapped_column(
        PgEnum(ReportSource, name="report_source", create_type=False),
        nullable=False,
    )
    reporter_name: Mapped[str | None] = mapped_column(String, nullable=True)
    reporter_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    casualties_reported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    people_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_provenance: Mapped[Provenance] = mapped_column(
        PgEnum(Provenance, name="provenance", create_type=False),
        nullable=False,
        default=Provenance.REAL,
        server_default=text("'REAL'"),
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    event: Mapped[DisasterEvent | None] = relationship("DisasterEvent", back_populates="reports")


class HazardZone(Base):
    __tablename__ = "hazard_zones"
    __table_args__ = (
        CheckConstraint(
            "active_until IS NULL OR active_until > active_from",
            name="ck_hazard_zones_active_window",
        ),
        Index("idx_hazard_geom", "geom", postgresql_using="gist"),
        Index("idx_hazard_event", "event_id"),
        Index("idx_hazard_active", "active_from", "active_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    hazard_type: Mapped[DisasterType] = mapped_column(
        PgEnum(DisasterType, name="disaster_type", create_type=False),
        nullable=False,
    )
    severity: Mapped[SeverityLevel] = mapped_column(
        PgEnum(SeverityLevel, name="severity_level", create_type=False),
        nullable=False,
    )
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Polygon", srid=4326),
        nullable=False,
    )
    is_impassable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    active_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )
    active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    event: Mapped[DisasterEvent] = relationship("DisasterEvent", back_populates="hazard_zones")
