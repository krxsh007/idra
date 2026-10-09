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

## 3. Hazard-Aware Dijkstra (`api/app/gis/routing.py`)

When computing an evacuation or medical route from `(origin_lon, origin_lat)` to `(dest_lon, dest_lat)`:

1. **Endpoint snapping:** both endpoints are snapped to the nearest road-graph node (`snap_point_to_graph_memory`, `<= 500 m`). If either endpoint cannot be snapped, no route is returned for that pair.
2. **Blocked edges:** `get_blocked_edges` (`api/app/gis/spatial.py`) uses PostGIS `ST_Intersects` to find road edges that intersect the active impassable hazard polygons (`is_impassable = True`) of the event.
3. **Weighted Dijkstra:** NetworkX `shortest_path(method="dijkstra")` runs with a callable weight function that returns `inf` for blocked edges, `length * HAZARD_SOFT_PENALTY` (default `25.0`) for any caller-supplied penalised edges, and the plain edge `length` (metres) otherwise. The graph itself is never mutated, so concurrent requests are safe.
4. **No path:** if no path exists (for example because the origin or destination is enclosed by impassable polygons) the router returns `None` and the `RoutingAgent` lists the pair under `unreachable_locations` instead of returning an unsafe route.

Each computed route reports `distance_m`, `duration_s`, `hazard_avoided`, `traverses_hazard` and `blocked_edges_avoided`. The `RoutingAgent` routes from the event epicentre to the first recommended shelter and from up to three incident reports to the first recommended shelter (or hospital, when casualties are reported), using the facility coordinates stored in PostGIS.
