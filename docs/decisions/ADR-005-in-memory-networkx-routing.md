# ADR-005: In-Memory NetworkX Road Graph with PostGIS Persistence

## Status
Accepted

## Context
Hazard-avoiding evacuation routing requires dynamic per-request edge weight modifications for tens of blocked road segments. Hosted routing engines (OSRM, Valhalla) do not support ad-hoc per-request edge blocking, and pgRouting requires complex setup.

## Decision
Extract the road network once with OSMnx for the study area bounding box, persist nodes and edges in PostGIS (`road_nodes`, `road_edges`), and serialize the NetworkX graph to `artifacts/road_graph.pkl`. Load the graph into memory at server startup as a singleton and execute Dijkstra shortest path with dynamic edge weight penalties.

## Consequences
- Routing is completely explainable, deterministic, fast (sub-second), and requires no external routing service.
- Single process, single metro area limitation (accepted for Project-I proof of concept).
