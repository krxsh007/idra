# ADR-004: Static Road-Class Weights with Dynamic Hazard Penalties

## Status
Accepted

## Context
Commercial real-time traffic APIs (e.g., Google Maps Roads API) require paid billing accounts, have severe rate limits, and do not allow arbitrary per-request impassability polygons. Review-I Section 7.6 only formalizes shortest-path routing over $G=(V,E \setminus E_{blocked})$.

## Decision
Replace live external traffic APIs with static OpenStreetMap (OSM) highway speed classes imputed via OSMnx, combined with dynamic hazard penalty multipliers derived from PostGIS polygon intersections.

## Consequences
- Zero external billing or network dependencies in the routing pipeline.
- Satisfies Section 7.6 routing formalism.
- Routes can be calculated and demonstrated offline.
