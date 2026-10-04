# IDRA GIS Spatial Queries & Hazard-Avoiding Routing Engine

## 1. Study Area & Road Network Artifact
- **Study Area Bounding Box (`STUDY_AREA_BBOX`):** `[80.15, 12.95, 80.30, 13.15]` (Chennai Metropolitan Area, WGS84 `EPSG:4326`).
- **Pre-Built Road Graph (`artifacts/road_graph.pkl` + `artifacts/road_graph_manifest.json`):**
  - `1,748` road intersection nodes and `6,820` directed road edges.
  - Each edge stores `u`, `v`, `osmid`, `highway`, `length_m`, `speed_kph`, `travel_time_s`, and `geometry` (`LineString`).
  - Loaded once into process memory by `RoadGraphManager` (`api/app/gis/graph.py`) and treated as strictly read-only across concurrent route computations.

---

## 2. Coordinate Snapping (`api/app/gis/spatial.py`)
- `snap_to_nearest_node(lon, lat, max_snap_distance_m=500.0)` locates the nearest road graph vertex using Haversine distance (`haversine_distance_m`).
- If the nearest vertex exceeds `500.0 m` (or lies outside `STUDY_AREA_BBOX`), the snap fails explicitly (`SnapError`) rather than silently routing from an unrelated road segment.

---

## 3. Three-Stage Hazard-Aware Dijkstra (`api/app/gis/routing.py`)

When computing an evacuation or medical route from `(origin_lon, origin_lat)` to `(dest_lon, dest_lat)`:

1. **Blocked & Penalized Edge Identification:**
   - PostGIS (`ST_Intersects`) or local bounding/edge sets identify:
     - `blocked_edges`: edges intersecting impassable hazard polygons (`is_impassable = True`).
     - `penalized_edges`: edges intersecting passable hazard zones, scaled by severity multiplier (`LOW: 1.5x`, `MODERATE: 2.5x`, `HIGH: 5.0x`, `SEVERE: 10.0x`).
2. **Stage 0 — Baseline Shortest Path:**
   - Computes baseline Dijkstra shortest path on `travel_time_s` ignoring hazards to establish `baseline_distance_m` and `baseline_eta_minutes`.
3. **Stage 1 — Strict Hazard Avoidance:**
   - Runs NetworkX Dijkstra with a callable edge weight function (`_make_weight_fn`) that returns `None` (infinite cost / impassable) for any `(u, v)` in `blocked_edges` and multiplies `travel_time_s` by `penalty_factor` for `(u, v)` in `penalized_edges`.
   - Never mutates the underlying `nx.MultiDiGraph`.
   - If a path is found and coincides with Stage 0, returns `RouteStatus.OPTIMAL`; if it detours around blocked edges, returns `RouteStatus.DETOUR`.
4. **Stage 2 — Hazard-Enclosure Degradation:**
   - If Stage 1 raises `nx.NetworkXNoPath` (e.g., origin or destination is completely enclosed by an impassable flood polygon), Stage 2 relaxes `blocked_edges` to a heavy traversal penalty (`100.0x`) so responders still receive a last-resort extraction vector tagged with `RouteStatus.DEGRADED` (`crosses_impassable_hazard = True`).
