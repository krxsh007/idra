from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.gis.routing import HazardAwareRouter
from app.orchestration.conflicts import ConflictResolver
from app.orchestration.state import OrchestratorState


def test_conflict_resolver_double_booking_and_route_recomputation():
    mock_router = MagicMock(spec=HazardAwareRouter)
    mock_router.compute_route.return_value = {
        "coordinates": [[80.20, 13.00], [80.21, 13.01]],
        "distance_m": 1500.0,
        "duration_s": 240.0,
        "traverses_hazard": False,
    }

    resolver = ConflictResolver(router=mock_router)

    shelter_a_id = uuid.uuid4()
    shelter_b_id = uuid.uuid4()

    state: OrchestratorState = {
        "event_id": str(uuid.uuid4()),
        "facilities_output": {
            "recommended_shelters": [
                {
                    "facility_id": str(shelter_a_id),
                    "name": "Shelter A",
                    "available_capacity": 50,  # small capacity
                    "lon": 80.205,
                    "lat": 13.005,
                },
                {
                    "facility_id": str(shelter_b_id),
                    "name": "Shelter B",
                    "available_capacity": 500,  # larger capacity
                    "lon": 80.215,
                    "lat": 13.015,
                },
            ]
        },
        "planning_output": {
            "prioritized_zones": [
                {
                    "zone_label": "Sector 1",
                    "people_estimate": 150,  # exceeds Shelter A capacity (50)
                    "accessibility": "CONSTRAINED",
                }
            ]
        },
        "routing_output": {
            "routes": [
                {
                    "route_id": "r-1",
                    "origin": {"lon": 80.20, "lat": 13.00},
                    "destination": {"lon": 80.205, "lat": 13.005},
                    "destination_facility_id": str(shelter_a_id),
                    "rationale": "Initial route to Shelter A",
                }
            ]
        },
        "needs_human_review": False,
    }

    result = resolver.resolve(state)

    # 1. Double-booking detected and resolved
    assert len(result["conflicts_detected"]) >= 1
    assert any("over-booking" in c for c in result["conflicts_detected"])
    assert any("Reassigned overflow evacuees" in c for c in result["conflicts_resolved"])
    assert result["residual_overbooking"] == 0

    # 2. Route recomputed to Shelter B
    assert len(result["recomputed_routes"]) == 1
    assert result["recomputed_routes"][0]["destination_facility_id"] == str(shelter_b_id)
    assert result["updated_routing_output"]["routes"][0].get("superseded") is True
    assert mock_router.compute_route.call_count == 1


def test_conflict_resolver_contradictory_severity_signals():
    resolver = ConflictResolver()

    state: OrchestratorState = {
        "event_id": str(uuid.uuid4()),
        "assessed_severity": "MODERATE",  # MODERATE severity
        "planning_output": {
            "prioritized_zones": [
                {"zone_label": "Zone 1", "accessibility": "BLOCKED", "people_estimate": 50},
                {"zone_label": "Zone 2", "accessibility": "BLOCKED", "people_estimate": 40},
            ]  # ALL zones BLOCKED contradicts MODERATE severity
        },
        "facilities_output": {"recommended_shelters": []},
        "needs_human_review": False,
    }

    result = resolver.resolve(state)

    assert result["needs_human_review"] is True
    assert any("Contradictory telemetry signals" in c for c in result["conflicts_detected"])


def test_conflict_resolver_no_conflicts_clean():
    resolver = ConflictResolver()

    state: OrchestratorState = {
        "event_id": str(uuid.uuid4()),
        "assessed_severity": "HIGH",
        "facilities_output": {
            "recommended_shelters": [
                {
                    "facility_id": str(uuid.uuid4()),
                    "name": "Mega Shelter",
                    "available_capacity": 1000,
                }
            ]
        },
        "planning_output": {
            "prioritized_zones": [
                {"zone_label": "Sector 1", "people_estimate": 100, "accessibility": "ACCESSIBLE"}
            ]
        },
        "needs_human_review": False,
    }

    result = resolver.resolve(state)
    assert len(result["conflicts_detected"]) == 0
    assert result["needs_human_review"] is False
