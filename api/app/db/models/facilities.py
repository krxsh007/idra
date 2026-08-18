import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, utc_now
from app.db.models.enums import FacilityType, Provenance, ResourceKind


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (
        CheckConstraint("total_capacity >= 0", name="ck_facilities_total_capacity_nonneg"),
        CheckConstraint("current_occupancy >= 0", name="ck_facilities_current_occupancy_nonneg"),
        CheckConstraint(
            "current_occupancy <= total_capacity",
            name="ck_facilities_occupancy_within_capacity",
        ),
        Index("idx_fac_location", "location", postgresql_using="gist"),
        Index("idx_fac_type", "facility_type", "is_operational"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    external_ref: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    facility_type: Mapped[FacilityType] = mapped_column(
        PgEnum(FacilityType, name="facility_type", create_type=False),
        nullable=False,
    )
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    current_occupancy: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    specializations: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )
    has_generator: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    wheelchair_access: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    is_operational: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    location_provenance: Mapped[Provenance] = mapped_column(
        PgEnum(Provenance, name="provenance", create_type=False),
        nullable=False,
        default=Provenance.REAL,
        server_default=text("'REAL'"),
    )
    capacity_provenance: Mapped[Provenance] = mapped_column(
        PgEnum(Provenance, name="provenance", create_type=False),
        nullable=False,
        default=Provenance.SIMULATED,
        server_default=text("'SIMULATED'"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    capacity_logs: Mapped[list["FacilityCapacityLog"]] = relationship(
        "FacilityCapacityLog", back_populates="facility", cascade="all, delete-orphan"
    )
    resources: Mapped[list["Resource"]] = relationship("Resource", back_populates="depot_facility")


class FacilityCapacityLog(Base):
    __tablename__ = "facility_capacity_log"
    __table_args__ = (
        CheckConstraint("occupancy >= 0", name="ck_facility_capacity_log_occupancy_nonneg"),
        Index("idx_caplog_fac", "facility_id", text("recorded_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    occupancy: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    facility: Mapped[Facility] = relationship("Facility", back_populates="capacity_logs")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint("quantity_total >= 0", name="ck_resources_quantity_total_nonneg"),
        CheckConstraint("quantity_free >= 0", name="ck_resources_quantity_free_nonneg"),
        CheckConstraint(
            "quantity_free <= quantity_total",
            name="ck_resources_quantity_free_within_total",
        ),
        Index("idx_res_depot", "depot_location", postgresql_using="gist"),
        Index("idx_res_kind", "resource_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    resource_kind: Mapped[ResourceKind] = mapped_column(
        PgEnum(ResourceKind, name="resource_kind", create_type=False),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_free: Mapped[int] = mapped_column(Integer, nullable=False)
    depot_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="SET NULL"),
        nullable=True,
    )
    depot_location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    data_provenance: Mapped[Provenance] = mapped_column(
        PgEnum(Provenance, name="provenance", create_type=False),
        nullable=False,
        default=Provenance.SIMULATED,
        server_default=text("'SIMULATED'"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    depot_facility: Mapped[Facility | None] = relationship("Facility", back_populates="resources")
