# IDRA System Architecture

## 1. Architectural Overview
The **Intelligent Disaster Response Assistant (IDRA)** is a multi-agent decision-support and emergency command platform built around a modular Python/FastAPI backend, a single PostgreSQL 16 database with `postgis` and `vector` (`pgvector`) extensions, an in-memory NetworkX road graph extracted from OpenStreetMap for the Chennai Metropolitan Area (`STUDY_AREA_BBOX = [80.15, 12.95, 80.30, 13.15]`), and a Next.js 14 App Router tactical frontend with MapLibre GL JS.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Next.js 14 Tactical Frontend                         │
│  ┌───────────────────────────┐  ┌──────────────────────┐  ┌───────────────┐  │
│  │  MapLibre GL Command Map  │  │  Incident Briefing   │  │ Citizen Portal│  │
│  │  • Hazard Polygons        │  │  • Severity & SitRep │  │ • Multilingual│  │
│  │  • Facilities & Shelters  │  │  • Agent Traces      │  │   RAG Grounded│  │
│  │  • Dijkstra Routes        │  │  • Verification Gate │  │ • Urgent Flag │  │
│  └─────────────┬─────────────┘  └──────────┬───────────┘  └───────┬───────┘  │
└────────────────┼───────────────────────────┼──────────────────────┼──────────┘
                 │ REST + SSE (/api/v1/...)  │                      │
┌────────────────▼───────────────────────────▼──────────────────────▼──────────┐
│                        FastAPI Application Layer (api/)                      │
│  • JWT + RBAC (CITIZEN | RESPONDER | ADMIN)                                  │
│  • Rate Limiting & Prompt-Injection Sanitization                             │
│  • SSE Run Stream & Weather Sidecar (Open-Meteo, off by default)             │
├──────────────────────────────────────────────────────────────────────────────┤
│                   Orchestration Engine & 7-Agent Pipeline                    │
│  Stage 1: DisasterAssessmentAgent (Tier A: RAG + LLM)                        │
│  Stage 2: RescuePlanningAgent     (Tier A: DBSCAN + RAG + LLM/Rule Fallback) │
│  Stage 3: FacilityAgent | RoutingAgent | ResourceAllocationAgent (Tier B)    │
│  Stage 4: ConflictResolver        (Deterministic Cross-Agent Reconciliation) │
│  Stage 5: SynthesisAgent          (Tier A + Deterministic Template Fallback) │
├────────────────────────┬───────────────────────────┬─────────────────────────┤
│   Hybrid RAG Engine    │   GIS & Routing Engine    │   Persistence Layer     │
│  • Markdown Parser     │  • NetworkX Road Graph    │  • PostgreSQL 16        │
│  • Token Chunker       │    (OSM, 62k junctions)   │  • PostGIS 3.4          │
│  • 384-d Embeddings    │  • PostGIS ST_Intersects  │  • pgvector 0.8         │
│  • Cosine + BM25       │  • Hazard-Aware A*        │  • (no external cache)  │
│    (0.70 / 0.30)       │    (= Dijkstra-optimal)   │                         │
└────────────────────────┴───────────────────────────┴─────────────────────────┘
```

---

## 2. Two-Tier Reliability Architecture (ADR-002)
IDRA strictly separates its 7 specialized agents into two reliability tiers so that LLM outages or hallucinations never block life-safety routing, shelter assignment, or resource dispatch:

- **Tier A (LLM-Assisted with Grounding & Fallback):**
  - `DisasterAssessmentAgent`: Synthesizes field reports, weather telemetry, and retrieved NDMA/Sphere SOP chunks into a structured severity classification.
  - `RescuePlanningAgent`: Clusters geocoded reports using Haversine DBSCAN ($\epsilon = 500\text{ m}$) and generates prioritized rescue zones with citations; automatically falls back to deterministic rule-based zone prioritization if the LLM fails.
  - `SynthesisAgent`: Compiles the unified operational briefing (`SynthesisOutput`); falls back to a deterministic structured template if LLM validation or numeric consistency fails.
  - `CitizenAssistantAgent`: Answers public queries strictly grounded in retrieved KB chunks (`RAG_SCORE_FLOOR = 0.35`); short-circuits with zero LLM calls when retrieval confidence is below floor.
- **Tier B (100% Deterministic — Zero LLM Calls):**
  - `FacilityRecommendationAgent`: Filters and ranks hospitals and relief shelters using PostGIS spatial queries and multi-criteria scoring.
  - `RoutingAgent`: Computes hazard-avoiding evacuation and ambulance routes via weighted Dijkstra (blocked edges impassable, soft penalties for hazards) over the Chennai road network.
  - `ResourceAllocationAgent`: Allocates available staging units using a run-local ledger that prevents double-dispatch across zones.

---

## 3. Human-in-the-Loop Verification Gate
Every recommendation produced by an orchestration run enters PostgreSQL with:
- `verification_status = PENDING`
- `ResourceAllocation.is_committed = False`

No resource inventory (`ResourceUnit.available_quantity` / `status`) is mutated during an orchestration run. Only an authenticated `ADMIN` operator invoking `POST /api/v1/recommendations/{id}/verify` with `status` in `{VERIFIED, OVERRIDDEN, REJECTED}` can commit (`VERIFIED` / `OVERRIDDEN` with `commit_allocations=True`) or reject a recommendation, recording an immutable `AuditLog` entry.
