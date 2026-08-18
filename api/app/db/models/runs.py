import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, utc_now
from app.db.models.enums import (
    AgentName,
    AgentStatus,
    RunStatus,
    SeverityLevel,
    VerificationStatus,
)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("idx_run_event", "event_id", text("started_at DESC")),)

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
    status: Mapped[RunStatus] = mapped_column(
        PgEnum(RunStatus, name="run_status", create_type=False),
        nullable=False,
        default=RunStatus.QUEUED,
        server_default=text("'QUEUED'"),
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    llm_backend: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    assessed_severity: Mapped[SeverityLevel | None] = mapped_column(
        PgEnum(SeverityLevel, name="severity_level", create_type=False),
        nullable=True,
    )
    needs_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    outputs: Mapped[list["AgentOutput"]] = relationship(
        "AgentOutput", back_populates="run", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="run", cascade="all, delete-orphan"
    )
    routes: Mapped[list["Route"]] = relationship(
        "Route", back_populates="run", cascade="all, delete-orphan"
    )
    allocations: Mapped[list["ResourceAllocation"]] = relationship(
        "ResourceAllocation", back_populates="run", cascade="all, delete-orphan"
    )


class AgentOutput(Base):
    __tablename__ = "agent_outputs"
    __table_args__ = (
        UniqueConstraint("run_id", "agent", name="uq_agent_outputs_run_agent"),
        Index("idx_aout_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent: Mapped[AgentName] = mapped_column(
        PgEnum(AgentName, name="agent_name", create_type=False),
        nullable=False,
    )
    status: Mapped[AgentStatus] = mapped_column(
        PgEnum(AgentStatus, name="agent_status", create_type=False),
        nullable=False,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="outputs")


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_recommendations_priority"),
        CheckConstraint(
            "origin IN ('AI_GENERATED','DETERMINISTIC_COMPUTATION','HUMAN_ENTERED')",
            name="ck_recommendations_origin",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_recommendations_confidence_range",
        ),
        CheckConstraint(
            "verification_status = 'PENDING' OR verified_by IS NOT NULL",
            name="ck_recommendations_verified_by_required",
        ),
        Index("idx_rec_run", "run_id", "priority"),
        Index("idx_rec_event", "event_id", "verification_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent: Mapped[AgentName] = mapped_column(
        PgEnum(AgentName, name="agent_name", create_type=False),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="AI_GENERATED",
        server_default=text("'AI_GENERATED'"),
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    structured_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        PgEnum(VerificationStatus, name="verification_st", create_type=False),
        nullable=False,
        default=VerificationStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    override_note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="recommendations")
    citations: Mapped[list["RecommendationCitation"]] = relationship(
        "RecommendationCitation", back_populates="recommendation", cascade="all, delete-orphan"
    )


class RecommendationCitation(Base):
    __tablename__ = "recommendation_citations"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "chunk_id", name="uq_rec_citations_rec_chunk"),
        Index("idx_cit_rec", "recommendation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_title: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    quoted_span: Mapped[str | None] = mapped_column(String, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Relationships
    recommendation: Mapped[Recommendation] = relationship(
        "Recommendation", back_populates="citations"
    )


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        Index("idx_route_geom", "path_geom", postgresql_using="gist"),
        Index("idx_route_event", "event_id", text("computed_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disaster_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    origin: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    destination: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    destination_facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="SET NULL"),
        nullable=True,
    )
    path_geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="LineString", srid=4326),
        nullable=False,
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    hazard_avoided: Mapped[bool] = mapped_column(Boolean, nullable=False)
    traverses_hazard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    blocked_edge_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    algorithm: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="dijkstra_hazard_penalty",
        server_default=text("'dijkstra_hazard_penalty'"),
    )
    supersedes_route_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    run: Mapped[AgentRun | None] = relationship("AgentRun", back_populates="routes")


class ResourceAllocation(Base):
    __tablename__ = "resource_allocations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_resource_allocations_quantity_positive"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_resource_allocations_priority"),
        Index("idx_alloc_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_zone_label: Mapped[str] = mapped_column(String, nullable=False)
    target_location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    is_committed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("now()"),
    )

    # Relationships
    run: Mapped[AgentRun] = relationship("AgentRun", back_populates="allocations")
