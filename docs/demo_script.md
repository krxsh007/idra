# IDRA Live Demonstration Script

About 10 minutes end to end. Steps 1–5 are the core demo; step 6 is backup material for questions.

## Before the demo
1. Start the stack and confirm it is healthy:
   ```bash
   make up
   make smoke
   ```
2. Open `http://localhost:5173` and sign in (**Sign In** → **Admin** quick-fill → **Sign In**).
3. Trigger one run per scenario you plan to show, so each already has a briefing loaded if the LLM provider is slow on the day.
4. Keep `http://localhost:8000/docs` open in a second tab.

With `LLM_BACKEND=gemini` on the free tier, expect 20–40 s per run. If the provider returns 503/429, every
Tier A agent falls back to its deterministic output and the run still completes; this is a feature to point out,
not a failure. For a fully offline demo, set `LLM_BACKEND=fake`, run `make seed`, and recreate the API container.

---

## Step 1 — The problem and the map (1 min)
1. Pick **Scenario 1: Chennai Adyar & Kotturpuram Monsoon Flood** in the event selector.
2. Walk through the map layers (bottom-left **Map Layers** panel): study-area bounding box, hazard polygons
   (severe = red, high = amber), geocoded incident reports, and hospital (H) / shelter (S) facilities.
3. Open **Event Details** to show the event metadata and reports feeding the agents.

## Step 2 — Multi-agent run (3 min)
1. In **Briefing & Runs**, click **Trigger Run**.
2. Narrate the 7-stage pipeline as each card turns to **Done**:
   - **Tier A (LLM + grounding):** 1. Disaster Assessment (RAG over NDMA/TNSDMA/Sphere SOPs), 2. Rescue Planning
     (DBSCAN clustering of reports into rescue zones), 7. Briefing Synthesis.
   - **Tier B (deterministic):** 3. Facility Matching (PostGIS), 4. Evacuation Routing (hazard-avoiding Dijkstra on the
     OSM road graph), 5. Resource Ledger, 6. Conflict Resolver.
3. Key point: the LLM only writes prose and prioritisation on top of numbers the deterministic agents computed.
   Facility names in the LLM briefing are checked against real facilities, and outputs are screened for forbidden
   language; on any failure the agent returns its deterministic output.

## Step 3 — Prioritised briefing and map focus (2 min)
1. Scroll to **Prioritized Briefing**: recommendations ordered by priority (life safety first), each with an
   origin badge (AI-generated vs deterministic) and provenance tag (REAL vs SIMULATED data).
2. Click the locate action on a recommendation card: the map flies to the target zone or facility.
3. Point at the **Evacuation Routes** on the map: lines from each rescue zone (amber dot) to its hospital (blue)
   or shelter (green), computed by hazard-avoiding Dijkstra. In Scenario 1 the shelter route visibly detours
   around the severe flood polygon. Click a route for distance, travel time, and whether hazards were avoided.

## Step 4 — Human-in-the-loop verification (2 min)
1. Every recommendation starts as **PENDING**; nothing is committed automatically.
2. As Admin, click **Approve** on a recommendation: it becomes **VERIFIED** and is recorded in the audit log.
3. Click **Override** or **Reject**: the gate refuses without a justification note. Enter one to complete it.
4. Use the **ALL / PENDING / VERIFIED** filter to show the review state.

## Step 5 — Citizen Emergency Assistant (2 min)
1. Open **Citizen Emergency Assistant** (bottom-right).
2. Informational query: *"What should I do during severe flood waterlogging in Chennai?"* → grounded answer
   with citations to the SOP documents and official helplines.
3. Urgent query: *"Water entering first floor in Saidapet, 3 elderly trapped on roof!"* → flagged
   **LIFE_THREATENING**, escalated into an incident report for responders, with 112/1077 guidance.
4. Out-of-scope query (e.g. *"Is it safe to drive through water on OMR?"*): when retrieval finds no guidance above
   the score floor, the assistant makes **zero** LLM calls and returns the safe fallback instead of guessing.

## Step 6 — Evidence for questions
- **Tests:** `make test` (unit, integration, and end-to-end fault-injection suites).
- **Evaluation:** `make eval` regenerates [`evaluation.md`](evaluation.md) — 34 automated metrics across RAG
  quality, agent behaviour, GIS routing, and system faults. Agent and fault metrics use a scripted LLM so they are
  reproducible; RAG metrics use the configured embedding model.
- **API:** `http://localhost:8000/docs` for the REST/SSE endpoints.
- **Reliability story:** pull the Gemini key (or wait for a 503) and show that runs still complete with
  deterministic fallbacks.
