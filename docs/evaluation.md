# IDRA Testing & Evaluation Report (Artifact 13)

> **Generated automatically by `scripts/run_eval.py` from measured harness output (`artifacts/eval_results.json`).**
> - **Timestamp (UTC):** `2026-10-09T05:12:00.789826+00:00`
> - **LLM Backend:** `fake`
> - **Automated Metrics Passed:** `34 / 34` (`100.0%`)
> - **UI Human Cohort Status:** `AWAITING_HUMAN_PARTICIPANTS`

---

## 13.1 Test Pyramid Summary

| Level | Scope | Tooling | Suite Location |
|---|---|---|---|
| **Unit** | Chunker, cleaner, embeddings, facility scorer, router weight, selection rules, conflict resolver, security guards | `pytest` | `tests/unit/` |
| **Integration** | Auth, events, reports, hazards, facilities, runs, recommendations, assistant, and metrics routers | `pytest` + `httpx.AsyncClient` | `tests/integration/` |
| **End-to-End & Faults** | Full 7-agent orchestration across all 3 seeded Chennai scenarios + all 9 failure modes of Section 12.8 | `pytest` | `tests/e2e/test_scenarios_and_faults.py` |
| **Smoke** | Executable curl verification against a running stack | `bash` + `curl` | `scripts/smoke.sh` |

---

## 13.2 RAG Pipeline Metrics (`rag_eval`)

Measured over `retrieval_queries.json` (40 in-domain queries + 5 out-of-domain floor-miss queries across `data/kb/raw/*.md`):

| Metric | Measured | Target | Status |
|---|---|---|---|
| `retrieval_precision_at_5` | `0.92` | `>= 0.7` | **PASS** |
| `retrieval_recall_at_8` | `0.8042` | `>= 0.75` | **PASS** |
| `retrieval_mrr_at_8` | `0.8375` | `>= 0.8` | **PASS** |
| `citation_resolution_rate` | `1.0` | `>= 0.95` | **PASS** |
| `zero_llm_call_on_floor_miss_rate` | `1.0` | `== 1.0` | **PASS** |
| `retrieval_latency_p50_ms` | `2.12` | `<= 150.0` | **PASS** |
| `retrieval_latency_p95_ms` | `2.23` | `<= 250.0` | **PASS** |
| `inter_annotator_cohens_kappa` | `0.89` | `>= 0.8` | **PASS** |

---

## 13.3 Agent & Coordination Metrics (`agent_eval`)

Measured over `assessment_cases.json` (20 cases), `facility_cases.json` (10 cases), `resource_cases.json` (10 cases), `conflict_cases.json` (8 cases), and `citizen_queries.json` (30 queries + 5 prompt-injection payloads):

| Metric | Measured | Target | Status |
|---|---|---|---|
| `assessment_severity_accuracy` | `0.95` | `>= 0.8` | **PASS** |
| `assessment_severity_macro_f1` | `0.9495` | `>= 0.78` | **PASS** |
| `assessment_within_one_tier_rate` | `1.0` | `>= 0.95` | **PASS** |
| `facility_hard_filter_compliance_rate` | `1.0` | `== 1.0` | **PASS** |
| `facility_top1_ranking_accuracy` | `1.0` | `>= 0.85` | **PASS** |
| `shelter_multi_split_unmet_demand_accuracy` | `1.0` | `== 1.0` | **PASS** |
| `resource_zero_overcommitment_rate` | `1.0` | `== 1.0` | **PASS** |
| `resource_shortfall_reporting_accuracy` | `1.0` | `== 1.0` | **PASS** |
| `conflict_resolution_accuracy` | `1.0` | `>= 0.9` | **PASS** |
| `synthesis_numeric_entity_consistency_rate` | `1.0` | `== 1.0` | **PASS** |
| `citizen_urgent_escalation_recall` | `1.0` | `== 1.0` | **PASS** |
| `citizen_false_positive_escalation_rate` | `0.0` | `<= 0.1` | **PASS** |
| `citizen_prompt_injection_refusal_rate` | `1.0` | `== 1.0` | **PASS** |

---

## 13.4 GIS & Hazard-Avoiding Routing Metrics (`gis_eval`)

Measured over `routing_cases.json` (10 detour cases + 5 hazard-enclosure cases) on the Chennai study-area road graph (`1,748` nodes, `6,820` edges):

| Metric | Measured | Target | Status |
|---|---|---|---|
| `snap_accuracy_within_500m` | `1.0` | `== 1.0` | **PASS** |
| `path_connectivity_and_edge_validity_rate` | `1.0` | `== 1.0` | **PASS** |
| `distance_sum_accuracy_within_1m_rate` | `1.0` | `== 1.0` | **PASS** |
| `hazard_avoidance_rate_detour_cases` | `1.0` | `>= 0.9` | **PASS** |
| `enclosure_degradation_accuracy` | `1.0` | `== 1.0` | **PASS** |
| `route_computation_latency_p50_ms` | `3.59` | `<= 100.0` | **PASS** |
| `route_computation_latency_p95_ms` | `5.55` | `<= 250.0` | **PASS** |

---

## 13.5 System, Orchestration & Reliability Metrics (`system_eval`)

Measured over full orchestration runs on the 3 canonical scenarios (`chennai_flood`, `coastal_cyclone`, `building_collapse`), Tier-B LLM-disabled runs, and 10-way concurrent route requests:

| Metric | Measured | Target | Status |
|---|---|---|---|
| `e2e_scenario_completion_rate` | `1.0` | `== 1.0` | **PASS** |
| `tier_b_llm_disabled_survival_rate` | `1.0` | `== 1.0` | **PASS** |
| `verification_gate_enforcement_rate` | `1.0` | `== 1.0` | **PASS** |
| `concurrent_graph_immutability_rate` | `1.0` | `== 1.0` | **PASS** |
| `orchestration_run_latency_p50_ms` | `27.5` | `<= 5000.0` | **PASS** |
| `orchestration_run_latency_p95_ms` | `32.12` | `<= 15000.0` | **PASS** |

---

## 13.6 UI & Human-Factors Evaluation (`ui_study_results.json`)

Per Artifact 15 Rule 5 (*"Never write a metric value you did not measure, and never fill a missing measurement with a plausible number"*), human participant cohort metrics are reported as `null` until the 6-8 participant usability session is executed:

- **Study Status:** `AWAITING_HUMAN_PARTICIPANTS` (`0 / 8` human participants completed)
- **SUS Mean Score:** `None` (Target: `>= 72.0`)
- **Human Task Completion Rate:** `None` (Target: `>= 0.85`)
- **Human `OriginBadge` Comprehension Rate:** `None` (Target: `>= 0.85`)
- **Human `ProvenanceTag` Comprehension Rate:** `None` (Target: `>= 0.85`)
- **Automated UI Verification Checks:**
  - `OriginBadge` verification states verified: `4` (`PENDING`, `VERIFIED`, `OVERRIDDEN`, `REJECTED`)
  - `ProvenanceTag` variants verified: `2` (`REAL`, `SIMULATED`)
  - Non-dismissible emergency disclaimer banner present: `True`
  - Admin-only `VerificationControls` RBAC gated: `True`
  - Briefing-to-Map `flyTo` camera binding verified: `True`

---

## 13.7 Committed Evaluation Datasets (`api/app/eval/datasets/`)

| Dataset File | Records | Purpose | Inter-Annotator Agreement |
|---|---|---|---|
| `retrieval_queries.json` | 40 + 5 OOD | RAG Precision@5, Recall@8, MRR@8, and score-floor rejection | Cohen's kappa = 0.89 |
| `assessment_cases.json` | 20 | Disaster Assessment severity classification and macro-F1 | Cohen's kappa = 0.91 |
| `routing_cases.json` | 15 (10 detour, 5 enclosure) | Dijkstra hazard avoidance, connectivity, and Stage-2 degradation | Deterministic ground truth |
| `facility_cases.json` | 10 (5 shelter, 5 hospital) | Hard filters, generator priority, greedy split, specialization match | Deterministic ground truth |
| `resource_cases.json` | 10 | Run-local ledger clamping, zero DB mutation, shortfall accuracy | Deterministic ground truth |
| `citizen_queries.json` | 30 + 5 injection | Urgent keyword escalation recall, false-positive rate, safety filter | Deterministic ground truth |
| `conflict_cases.json` | 8 | Facility capacity overflow reassignment & contradictory signals | Deterministic ground truth |
| `ui_study_results.json` | 5 tasks + 4 questions | SUS usability instrument, task completion, badge comprehension | Cohort instrument |

---

## 13.8 Honest Discussion of Missed Targets & Limitations

### Automated Metric Misses
- All automated metrics met their target thresholds.

### Root-Cause Analysis & Technical Discussion
1. **RAG Recall@8 and MRR@8 under Offline Feature-Hashed Embeddings (`LLM_BACKEND=fake`):**
   - Under the deterministic feature-hashed vector fallback (`LLM_BACKEND=fake`), `retrieval_precision_at_5` reaches `0.92`, `retrieval_recall_at_8` reaches `0.8042`, `retrieval_mrr_at_8` reaches `0.8375`, and `zero_llm_call_on_floor_miss_rate` achieves `1.00`.
   - **Trade-off:** Feature hashing projects tokens and 4-5 character prefixes into 384 signed buckets without neural synonym expansion. Preserving a strict `RAG_SCORE_FLOOR = 0.35` guarantees `100%` rejection of out-of-domain queries (`zero_llm_call_on_floor_miss_rate = 1.0`), prioritizing zero hallucination over permissive recall.
2. **In-Memory NetworkX Road Graph Scope:**
   - Routing operates over a single-process in-memory NetworkX graph (`1,748` nodes, `6,820` edges) bounded to `STUDY_AREA_BBOX` (`80.15, 12.95, 80.30, 13.15`). Scaling to state-wide multi-million-edge road networks requires migrating Stage-0/1 shortest-path queries to `pgRouting` (`ADR-005`).
3. **Simulated Capacity Provenance:**
   - Hospital bed occupancies and shelter capacities are seeded and not connected to live health-department telemetry. Every synthetic figure is explicitly tagged with `capacity_provenance = SIMULATED` in PostgreSQL, the JSON API, and the `ProvenanceTag` UI badge.
4. **Annotator Bias Acknowledgement:**
   - Ground-truth relevance labels in `retrieval_queries.json` (kappa = 0.89) and severity labels in `assessment_cases.json` (kappa = 0.91) were authored and reconciled by the project developers against published NDMA/Sphere/TNSDMA guidelines rather than an external panel of emergency commissioners.
