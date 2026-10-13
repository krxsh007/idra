from __future__ import annotations

import structlog

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, FacilityType
from app.gis.spatial import get_facility_ids_in_hazard_zones, get_nearby_facilities
from app.schemas.agents.facilities import (
    FacilityCandidate,
    FacilityRecommendationInput,
    FacilityRecommendationOutput,
)

logger = structlog.get_logger(__name__)


class FacilityRecommendationAgent(
    BaseAgent[FacilityRecommendationInput, FacilityRecommendationOutput]
):
    """Recommends hospitals and shelters based on proximity, capacity, and capabilities."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.HOSPITAL_RECOMMENDATION,
            response_schema=FacilityRecommendationOutput,
        )

    async def _execute(
        self,
        ctx: RunContext,
        input_data: FacilityRecommendationInput,
    ) -> FacilityRecommendationOutput | AgentFailure:
        log = logger.bind(agent=self.agent_name.value, event_id=str(input_data.event.id))
        log.info("facility_recommendation_started")

        if ctx.db is None:
            # Deterministic fallback when DB session is not provided (e.g. testing without DB)
            return FacilityRecommendationOutput(
                recommended_hospitals=[],
                recommended_shelters=[],
                rationale="No active database session available for spatial facility lookups.",
                total_hospital_capacity_available=0,
                total_shelter_capacity_available=0,
            )

        # 1. Query nearby operational hospitals and shelters
        hospitals_res = await get_nearby_facilities(
            db=ctx.db,
            lon=input_data.epicenter.lon,
            lat=input_data.epicenter.lat,
            radius_m=input_data.hospital_search_radius_m,
            facility_type=FacilityType.HOSPITAL,
            is_operational=True,
            limit=10,
        )

        shelters_res = await get_nearby_facilities(
            db=ctx.db,
            lon=input_data.epicenter.lon,
            lat=input_data.epicenter.lat,
            radius_m=input_data.shelter_search_radius_m,
            facility_type=FacilityType.SHELTER,
            is_operational=True,
            limit=10,
        )

        # Never send people into a hazard zone: drop facilities located inside one.
        in_hazard = await get_facility_ids_in_hazard_zones(ctx.db, input_data.event.id)
        excluded = [
            item.facility.name
            for item in [*hospitals_res, *shelters_res]
            if item.facility.id in in_hazard
        ]
        hospitals_res = [item for item in hospitals_res if item.facility.id not in in_hazard]
        shelters_res = [item for item in shelters_res if item.facility.id not in in_hazard]
        if excluded:
            log.info("facilities_in_hazard_zones_excluded", facilities=excluded)

        # 2. Build Candidate lists
        recommended_hospitals: list[FacilityCandidate] = []
        total_hosp_avail = 0
        for item in hospitals_res:
            fac = item.facility
            avail = max(0, fac.total_capacity - fac.current_occupancy)
            if avail > 0:
                total_hosp_avail += avail
                reasons = [f"Distance {int(item.distance_m)}m"]
                if fac.has_generator:
                    reasons.append("Emergency backup generator active")
                if fac.wheelchair_access:
                    reasons.append("Wheelchair accessible")
                if fac.specializations:
                    reasons.append(f"Specializations: {', '.join(fac.specializations[:2])}")

                recommended_hospitals.append(
                    FacilityCandidate(
                        facility_id=fac.id,
                        name=fac.name,
                        facility_type=fac.facility_type,
                        distance_m=round(item.distance_m, 1),
                        total_capacity=fac.total_capacity,
                        current_occupancy=fac.current_occupancy,
                        available_capacity=avail,
                        has_generator=fac.has_generator,
                        wheelchair_access=fac.wheelchair_access,
                        specializations=fac.specializations,
                        match_reasons=reasons,
                    )
                )

        recommended_shelters: list[FacilityCandidate] = []
        total_shelter_avail = 0
        for item in shelters_res:
            fac = item.facility
            avail = max(0, fac.total_capacity - fac.current_occupancy)
            if avail > 0:
                total_shelter_avail += avail
                reasons = [f"Distance {int(item.distance_m)}m"]
                if fac.has_generator:
                    reasons.append("Generator available")
                if fac.wheelchair_access:
                    reasons.append("Wheelchair accessible")

                recommended_shelters.append(
                    FacilityCandidate(
                        facility_id=fac.id,
                        name=fac.name,
                        facility_type=fac.facility_type,
                        distance_m=round(item.distance_m, 1),
                        total_capacity=fac.total_capacity,
                        current_occupancy=fac.current_occupancy,
                        available_capacity=avail,
                        has_generator=fac.has_generator,
                        wheelchair_access=fac.wheelchair_access,
                        specializations=fac.specializations,
                        match_reasons=reasons,
                    )
                )

        # Sort candidates primarily by distance, prioritizing those with generator
        recommended_hospitals.sort(key=lambda c: (not c.has_generator, c.distance_m))
        recommended_shelters.sort(key=lambda c: (not c.has_generator, c.distance_m))

        top_hospitals = recommended_hospitals[:5]
        top_shelters = recommended_shelters[:5]

        rationale = (
            f"Identified {len(top_hospitals)} operational hospitals with {total_hosp_avail} "
            f"available beds and {len(top_shelters)} emergency shelters with {total_shelter_avail} "
            f"capacity within search radius, outside all hazard zones. Ranked by proximity and "
            f"backup power availability."
        )
        if excluded:
            rationale += (
                f" Excluded {len(excluded)} inside hazard zones: {', '.join(excluded[:5])}."
            )

        return FacilityRecommendationOutput(
            recommended_hospitals=top_hospitals,
            recommended_shelters=top_shelters,
            rationale=rationale,
            total_hospital_capacity_available=total_hosp_avail,
            total_shelter_capacity_available=total_shelter_avail,
        )
