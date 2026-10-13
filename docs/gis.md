# IDRA GIS Spatial Queries & Hazard-Avoiding Routing Engine

## 1. Study Area & Road Network Artifact
- **Study Area Bounding Box (`STUDY_AREA_BBOX`):** `[80.15, 12.95, 80.30, 13.15]` (Chennai Metropolitan Area, WGS84 `EPSG:4326`).
- **Road Graph (`artifacts/road_graph.pkl` + `artifacts/road_graph_manifest.json`):**
  - Built by `scripts/load_road_network.py` from **OpenStreetMap** drivable roads (motorway → living_street, plus `_link` ramps; footpaths, service roads and tracks excluded) inside the bbox, fetched once from the Overpass API and committed gzipped at `data/osm/chennai_roads_overpass.json.gz` (© OpenStreetMap contributors, ODbL). A fresh clone builds the pickle from this extract automatically.
  - Raw OSM nodes are collapsed so graph nodes are junctions and dead ends only (`62,243` nodes, `164,910` directed edges); each edge keeps the full street `geometry`, so routes follow real road shapes. Only the largest connected component is kept, so the graph is strongly connected.
  - Each edge stores `length`/`length_m`, `speed_kph` (by road class), `travel_s`, `highway_class`, `name`, `osm_way_id` and `geometry`. Two-way travel is assumed (emergency vehicles and evacuees on foot).
  - Loaded once into process memory by `RoadGraphManager` (`api/app/gis/graph.py`), frozen out of the cyclic GC, and treated as read-only. The same edges are written to `road_nodes`/`road_edges` in PostGIS.

---

## 2. Coordinate Snapping (`api/app/gis/spatial.py`)
- `snap_point_to_graph_memory(lon, lat, max_dist_m=500.0)` finds the nearest road-graph junction with a vectorised (numpy) nearest-neighbour search and reports its exact Haversine distance.
- If the nearest junction is more than `500 m` away (e.g. inside Guindy National Park or the IIT Madras campus) or the point lies outside `STUDY_AREA_BBOX`, snapping fails explicitly rather than silently routing from an unrelated road.

---

## 3. Hazard-Aware Routing (`api/app/gis/routing.py`, `api/app/agents/routing.py`)

When computing an evacuation or medical route from `(origin_lon, origin_lat)` to `(dest_lon, dest_lat)`:

1. **Endpoint snapping:** both endpoints are snapped to the nearest junction (`<= 500 m`). If either cannot be snapped, no route is returned for that pair.
2. **Hazard classification:** the `RoutingAgent` intersects each of the event's hazard polygons with the street geometry (shapely `STRtree`, in memory). Roads in **impassable** zones are closed; roads in any other hazard zone are penalised (`length × HAZARD_SOFT_PENALTY`, default `25`). A zone that contains the route's **origin or destination** is penalised rather than closed, so a rescue from inside a flood takes the shortest way out instead of being declared unreachable.
3. **A\* search:** NetworkX `astar_path` with a straight-line lower bound (planar metres × 0.995). This returns the same optimal path as Dijkstra (verified on every routing evaluation case) while exploring far fewer nodes. The graph is never mutated, so concurrent requests are safe.
4. **No path:** if every way out is closed, the router returns `None` and the pair is listed under `unreachable_locations` rather than returning an unsafe route.

**Facility safety:** the `FacilityRecommendationAgent` excludes hospitals and shelters located inside any of the event's hazard zones (PostGIS `ST_Intersects`), so routes never end inside a hazard.

Each computed route reports `distance_m`, `duration_s` (from per-road speeds), `starts_in_hazard`, `traverses_hazard` (crosses a hazard zone other than the one it starts or ends in), `hazard_avoided` and `blocked_edges_avoided`, plus a `geometry` LineString that follows the streets. The `RoutingAgent` routes from the event epicentre to the first recommended shelter and from up to three incident reports to the first recommended shelter (or hospital, when casualties are reported), using the facility coordinates stored in PostGIS.
