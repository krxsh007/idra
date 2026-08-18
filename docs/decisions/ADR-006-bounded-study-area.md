# ADR-006: Bounded Single-City Study Area (Chennai Core)

## Status
Accepted

## Context
Scope 4.2 in Review-I states that Project-I is a "proof of concept on representative/sample data" and disclaims nationwide live feeds. Unbounded geography leads to unverified coordinates and undemonstrable evaluation scenarios.

## Decision
Bind the implementation to one configurable metropolitan bounding box: Chennai city core (`80.15,12.95,80.30,13.15`). All geographic coordinates for hospitals, shelters, and roads are real and extracted from OpenStreetMap. Capacity and occupancy numbers are simulated and explicitly labelled with `"data_provenance": "SIMULATED"` in database rows, API responses, and UI badges.

## Consequences
- Guarantees all demo scenarios are locally verifiable with real landmark coordinates.
- Bounds road graph extraction and spatial queries to manageable sizes (30k–60k nodes).
