# ADR-001: Two-Tier Multi-Agent Architecture

## Status
Accepted

## Context
The Review-I report specifies seven agents: Disaster Assessment, Rescue Planning, Evacuation, Hospital Recommendation, Shelter Allocation, Resource Coordination, and Citizen Assistance.
Conflating responsibility with implementation by using LLM prompt-engineering for deterministic mathematical and spatial problems (such as shortest path routing or facility scoring) results in severe hallucinations (inventing bed counts, impossible routes), high latency, and high cost.

## Decision
Implement the seven agents in two distinct tiers behind a uniform `BaseAgent` contract:
1. **Tier A (LLM Reasoning Agents - 3):** Disaster Assessment, Rescue Planning, Citizen Assistance. These consume unstructured data, require RAG grounding, and produce qualitative judgement.
2. **Tier B (Deterministic Solver Agents - 4):** Evacuation, Hospital Recommendation, Shelter Allocation, Resource Coordination. These compute spatial and mathematical solutions deterministically over PostGIS and NetworkX. Each calls the LLM at most once at the end for a short natural-language justification, never to compute the numbers.

## Consequences
- Completely eliminates hallucinations for bed counts, capacities, route geometries, and resource counts.
- Halves LLM API calls and execution latency per orchestration run.
- Ensures all deterministic spatial results are reproducible and explainable to examiners.
