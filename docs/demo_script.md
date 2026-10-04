# IDRA Live Demonstration Script

## Prerequisites
1. Start the full stack:
   ```bash
   make up
   make migrate
   make seed
   ```
2. Open the tactical frontend at `http://localhost:3000` (or API docs at `http://localhost:8000/docs`).

---

## Step 1 — Scenario Activation (`/admin`)
1. Sign in at `http://localhost:3000/login` using `admin@idra.local` / `AdminPass123!`.
2. Navigate to `/admin` (**Admin Scenario & Hazard Console**).
3. Activate **Scenario 1: 2026 Adyar River Basin Urban Flood (`chennai_flood`)**.
4. Observe the newly seeded event, 2 impassable/high-severity flood polygons along Kotturpuram and Saidapet, and 8 geocoded distress reports.

---

## Step 2 — Command Center Map & Multi-Agent Run (`/`)
1. Open the **Command Center** (`http://localhost:3000/`).
2. Inspect the MapLibre GL tactical map:
   - Red/Amber polygons mark inundated flood corridors.
   - Hospital and shelter pins display `REAL` (OSM location) and `SIMULATED` (capacity) `ProvenanceTag` badges.
3. Click **Run Multi-Agent Analysis** in the top bar:
   - Watch the **Agent Trace Drawer** stream live stage completions (`DISASTER_ASSESSMENT` $\to$ `RESCUE_PLANNING` $\to$ parallel `HOSPITAL_RECOMMENDATION`, `EVACUATION`, `RESOURCE_COORDINATION` $\to$ `ConflictResolver` $\to$ `SYNTHESIS`).
4. Click any recommendation card in the **Incident Briefing** panel:
   - The map camera smoothly flies (`flyTo`) to the target rescue zone or shelter and highlights the Dijkstra hazard-avoiding evacuation route (`RouteStatus.DETOUR` / `OPTIMAL`).

---

## Step 3 — Human-in-the-Loop Verification Gate (`/`)
1. Notice that every newly generated recommendation displays `OriginBadge` = `PENDING` (`AI-GENERATED • AWAITING VERIFICATION`) and resource allocations remain uncommitted (`is_committed = False`).
2. As `ADMIN`, click **Approve & Commit** on the top evacuation/resource recommendation (`VerificationControls`):
   - The badge transitions to `VERIFIED`, `ResourceUnit` quantities are decremented in PostgreSQL, and an immutable `AuditLog` entry is recorded.
3. Click **Export SitRep** to download the Markdown Situation Report (`GET /api/v1/runs/{run_id}/sitrep`).

---

## Step 4 — Citizen Assistance & Urgent Escalation (`/citizen`)
1. Open `http://localhost:3000/citizen` (**Public Citizen Emergency Assistant**).
2. Switch language between **English (`en`)**, **Tamil (`ta`)**, and **Hindi (`hi`)**.
3. Submit an informational query: *"What is the safe drinking water requirement and how do I purify flood water?"*
   - Observe the grounded answer citing Sphere/NDMA guidelines alongside nearest operational relief shelters outside hazard zones.
4. Submit an urgent distress message: *"Water entering first floor in Saidapet, 3 elderly trapped on roof!"*
   - Observe the red **URGENT ESCALATION** banner (`urgent_escalation = True`), automatic high-priority `IncidentReport` creation, and emergency helplines (`1070`, `1913`, `108`, `112`).

---

## Step 5 — Evaluation Harness Verification (`/api/v1/metrics/eval`)
1. Run the deterministic evaluation suite from the terminal:
   ```bash
   make eval
   ```
2. Query `GET http://localhost:8000/api/v1/metrics/eval` (or view `docs/evaluation.md`) to inspect all 34 automated metrics across `rag_eval`, `agent_eval`, `gis_eval`, and `system_eval`.
