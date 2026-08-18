# ADR-003: Computer Vision Offline Feasibility Study

## Status
Accepted

## Context
High-resolution, timestamped satellite or drone imagery of active Indian urban floods is unobtainable on student timelines. Freely available Sentinel-2 imagery (10m resolution, 5-day revisit) cannot resolve structural damage. Review-I Objective 5 states: *"Evaluate the feasibility of computer-vision-assisted disaster assessment."*

## Decision
Computer vision is deferred out of the synchronous MVP request path and delivered as an offline feasibility study module (optional Milestone M15). The Disaster Assessment Agent contract preserves an optional `visual_damage_indicator` (float or null) input/output field so the architecture is future-ready without making runtime reliability hostage to an external CV model.

## Consequences
- Prevents demo failures from missing or low-resolution imagery.
- Strictly satisfies Objective 5 as approved in Review-I.
