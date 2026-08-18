from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class RoadNode(Base):
    __tablename__ = "road_nodes"
    __table_args__ = (Index("idx_rnode_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="Point", srid=4326),
        nullable=False,
    )


class RoadEdge(Base):
    __tablename__ = "road_edges"
    __table_args__ = (
        CheckConstraint("length_m > 0", name="length_positive"),
        CheckConstraint("speed_kph > 0", name="speed_positive"),
        CheckConstraint("travel_s > 0", name="travel_positive"),
        UniqueConstraint("u", "v", "key", name="uq_road_edges_u_v_key"),
        Index("idx_redge_geom", "geom", postgresql_using="gist"),
        Index("idx_redge_uv", "u", "v"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    u: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("road_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    v: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("road_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    osm_way_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    highway_class: Mapped[str | None] = mapped_column(String, nullable=True)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    speed_kph: Mapped[float] = mapped_column(Float, nullable=False)
    travel_s: Mapped[float] = mapped_column(Float, nullable=False)
    oneway: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="LineString", srid=4326),
        nullable=False,
    )
