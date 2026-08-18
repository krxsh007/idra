# ADR-002: Shared Facility Matcher Service

## Status
Accepted

## Context
Hospital Recommendation and Shelter Allocation agents share approximately 85% identical logic: filtering operational facilities, checking hazard intersection, calculating true metric distances, and scoring candidates by proximity and free capacity.

## Decision
Implement a single shared internal `FacilityMatcher` service parameterized by facility type (`HOSPITAL` vs `SHELTER`) and configurable scoring weights:
- Hospital weighting prioritizes proximity (0.40), capacity (0.35), specialization matching (0.20), and generator backup (0.05).
- Shelter weighting prioritizes capacity adequacy (0.45), proximity (0.35), accessibility (0.10), and generator backup (0.10).

## Consequences
- Maintains two distinct agent contracts while sharing one robust spatial scoring service.
- Avoids duplicated codebase logic, simplifies testing, and accelerates milestone delivery.
