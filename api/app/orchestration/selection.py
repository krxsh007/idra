from __future__ import annotations

from typing import Any

from app.db.models.enums import AgentName, SeverityLevel


def evaluate_agent_activation(
    assessment_output: dict[str, Any] | None,
    planning_output: dict[str, Any] | None = None,
    shelter_target_exists: bool = False,
) -> dict[AgentName, bool]:
    """Pure-function deterministic selection table per PRD Section 3.3.

    - Disaster Assessment: Always True
    - Rescue Planning: severity in {MODERATE, HIGH, SEVERE}
    - Shelter Allocation: evacuation_recommended == True OR displaced_estimate > 0
    - Hospital Recommendation: casualties_reported == True OR severity in {HIGH, SEVERE}
    - Evacuation: evacuation_recommended == True AND a shelter target exists
    - Resource Coordination: Rescue Planning produced at least one prioritized zone
    - Citizen Assistance: Never in an event run
    """
    if assessment_output is None:
        return {
            AgentName.DISASTER_ASSESSMENT: True,
            AgentName.RESCUE_PLANNING: False,
            AgentName.SHELTER_ALLOCATION: False,
            AgentName.HOSPITAL_RECOMMENDATION: False,
            AgentName.EVACUATION: False,
            AgentName.RESOURCE_COORDINATION: False,
            AgentName.CITIZEN_ASSISTANCE: False,
            AgentName.SYNTHESIS: False,
        }

    severity_str = assessment_output.get("severity", "LOW")
    evac_rec = bool(assessment_output.get("evacuation_recommended", False))
    displaced = int(assessment_output.get("estimated_people_affected", 0))
    casualties = bool(assessment_output.get("casualties_reported", False))

    is_rescue_planning = severity_str in [
        SeverityLevel.MODERATE.value,
        SeverityLevel.HIGH.value,
        SeverityLevel.SEVERE.value,
        SeverityLevel.MODERATE,
        SeverityLevel.HIGH,
        SeverityLevel.SEVERE,
    ]

    is_shelter_allocation = evac_rec or displaced > 0

    is_hospital_rec = casualties or severity_str in [
        SeverityLevel.HIGH.value,
        SeverityLevel.SEVERE.value,
        SeverityLevel.HIGH,
        SeverityLevel.SEVERE,
    ]

    is_evacuation = evac_rec and shelter_target_exists

    prioritized_zones = planning_output.get("prioritized_zones", []) if planning_output else []
    is_resource_coordination = len(prioritized_zones) > 0 or displaced > 0

    return {
        AgentName.DISASTER_ASSESSMENT: True,
        AgentName.RESCUE_PLANNING: is_rescue_planning,
        AgentName.SHELTER_ALLOCATION: is_shelter_allocation,
        AgentName.HOSPITAL_RECOMMENDATION: is_hospital_rec,
        AgentName.EVACUATION: is_evacuation,
        AgentName.RESOURCE_COORDINATION: is_resource_coordination,
        AgentName.CITIZEN_ASSISTANCE: False,
        AgentName.SYNTHESIS: True,
    }
