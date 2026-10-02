from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agents.facilities import FacilityCandidate
from app.schemas.events import EpicenterPoint, EventResponse
from app.schemas.hazards import HazardZoneResponse
from app.schemas.reports import ReportResponse


class RouteGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        description="GeoJSON LineString coordinate array: [ [lon, lat], [lon, lat], ... ]",
    )


class ComputedRouteItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    route_id: uuid.UUID
    origin: EpicenterPoint
    destination: EpicenterPoint
    destination_facility_id: uuid.UUID | None = None
    destination_name: str
    geometry: RouteGeometry
    distance_m: float
    duration_s: float
    hazard_avoided: bool
    traverses_hazard: bool
    blocked_edges_avoided: int = 0
    algorithm: str = "dijkstra_hazard_penalty"
    rationale: str = Field(..., min_length=5, max_length=500)


class RoutingInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    event: EventResponse
    reports: list[ReportResponse] = Field(default_factory=list)
    recommended_shelters: list[FacilityCandidate] = Field(default_factory=list)
    recommended_hospitals: list[FacilityCandidate] = Field(default_factory=list)
    hazard_zones: list[HazardZoneResponse] = Field(default_factory=list)


class RoutingOutput(BaseModel):
    routes: list[ComputedRouteItem] = Field(default_factory=list)
    total_routes_computed: int = 0
    unreachable_locations: list[str] = Field(default_factory=list)
    operational_summary: str = Field(..., min_length=10, max_length=1000)
