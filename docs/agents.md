# IDRA Multi-Agent Orchestration & Coordination

## 1. The 7 Specialized Agents

| Agent | Enum (`AgentName`) | Tier | Primary Input | Structured Output (`app.agents.schemas`) |
|---|---|---|---|---|
| **1. Disaster Assessment** | `DISASTER_ASSESSMENT` | Tier A | Field reports, hazard zones, weather sidecar, RAG SOP chunks | `AssessmentOutput` |
| **2. Rescue Planning** | `RESCUE_PLANNING` | Tier A (with deterministic fallback) | `AssessmentOutput`, DBSCAN report clusters ($\epsilon=500\text{ m}$), RAG chunks | `RescuePlanOutput` |
| **3. Facility Recommendation** | `HOSPITAL_RECOMMENDATION` | Tier B (Deterministic) | `RescuePlanOutput`, PostGIS facility candidates, hazard intersections | `FacilityRecommendationOutput` |
| **4. Evacuation & Routing** | `EVACUATION` | Tier B (Deterministic) | Rescue zones, recommended facilities, NetworkX graph + blocked edges | `RoutingOutput` |
| **5. Resource Allocation** | `RESOURCE_COORDINATION` | Tier B (Deterministic) | Rescue zones, available `ResourceUnit` rows, Haversine distance | `ResourceAllocationOutput` |
| **6. Synthesis & Briefing** | `SYNTHESIS` | Tier A (with template fallback) | All upstream outputs + `ConflictReport` | `SynthesisOutput` |
| **7. Citizen Assistance** | `CITIZEN_ASSISTANCE` | Tier A (Public Endpoint) | Citizen query, location, language (`en`/`ta`/`hi`), RAG chunks | `CitizenAssistantResponse` |

---

## 2. Orchestration Execution DAG (`api/app/agents/orchestrator.py`)

```
[Event + Reports + HazardZones + Weather]
                   │
                   ▼
      ┌─────────────────────────┐
      │ DisasterAssessmentAgent │  (Stage 1)
      └────────────┬────────────┘
                   │
                   ▼
      ┌─────────────────────────┐
      │   RescuePlanningAgent   │  (Stage 2: DBSCAN + Priority Scoring)
      └────────────┬────────────┘
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
┌──────────┐ ┌───────────┐ ┌────────────┐
│ Facility │ │  Routing  │ │  Resource  │  (Stage 3: Parallel `asyncio.gather`)
│  Agent   │ │   Agent   │ │   Agent    │
└────┬─────┘ └─────┬─────┘ └─────┬──────┘
     └─────────────┼─────────────┘
                   ▼
      ┌─────────────────────────┐
      │    ConflictResolver     │  (Stage 4: Capacity & Contradiction Check)
      └────────────┬────────────┘
                   ▼
      ┌─────────────────────────┐
      │     SynthesisAgent      │  (Stage 5: Numeric Verification & SitRep)
      └─────────────────────────┘
```

---

## 3. Deterministic Scoring & Rules

### 3.1 Facility Multi-Criteria Scoring (`FacilityRecommendationAgent`)
- **Hard Filters:**
  1. Facility must be `OPERATIONAL` or `LIMITED`.
  2. Facility must not intersect an impassable hazard polygon (`in_hazard_zone == False`).
  3. Facility must have positive remaining capacity (`remaining_capacity > 0`).
- **Shelter Priority (`compute_shelter_score`):**
  - During `FLOOD` or `CYCLONE` events, shelters with backup power (`has_generator = True`) receive a mandatory `+0.25` priority bonus alongside normalized distance and available capacity scores.
  - If a single shelter cannot absorb a zone's displaced population, demand is greedily split across top-ranked shelters and any remainder is recorded in `unmet_shelter_demand_by_zone`.
- **Hospital Priority (`compute_hospital_score`):**
  - Combines trauma specialization match (`trauma`, `burns`, `pediatric`, `general`), ICU/bed availability, generator status, and distance.

### 3.2 Run-Local Resource Ledger (`ResourceAllocationAgent`)
- Initializes a run-local dictionary `ledger[resource_id] = unit.available_quantity`.
- Iterates over prioritized rescue zones and allocates nearest available units using `alloc_qty = min(needed, ledger[resource_id])`.
- Deducts `alloc_qty` from `ledger[resource_id]` in memory so no unit is double-allocated across zones, while leaving PostgreSQL `ResourceUnit` rows untouched until Admin verification.

### 3.3 Cross-Agent Conflict Resolution (`ConflictResolver`)
- **Facility Capacity Overflow (`FACILITY_CAPACITY_OVERFLOW`):** Detects when multiple rescue zones assign overlapping demand to the same shelter or hospital exceeding its remaining capacity, and automatically reassigns excess demand to the next highest-ranked facility.
- **Contradictory Assessment Signals (`CONTRADICTORY_SIGNALS`):** Detects mismatches between low severity ratings and high casualty/displaced counts, flagging the discrepancy for the `SynthesisAgent` and human operator.
