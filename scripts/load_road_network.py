from __future__ import annotations

import asyncio
import gzip
import json
import math
import os
import pickle
from datetime import UTC, datetime
from typing import Any

import httpx
import networkx as nx
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.roads import RoadEdge, RoadNode
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BBOX = [80.15, 12.95, 80.30, 13.15]  # min_lon, min_lat, max_lon, max_lat


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Compute haversine distance in meters between two lon/lat points."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Committed, gzipped Overpass extract (© OpenStreetMap contributors, ODbL) so builds work offline.
OSM_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "../data/osm/chennai_roads_overpass.json.gz"
)

# Drivable OSM road classes; footpaths, service roads and tracks are excluded.
HIGHWAY_SPEED_KPH = {
    "motorway": 60.0,
    "trunk": 50.0,
    "primary": 40.0,
    "secondary": 35.0,
    "tertiary": 30.0,
    "unclassified": 25.0,
    "residential": 20.0,
    "living_street": 15.0,
}
HIGHWAY_RANK = {name: rank for rank, name in enumerate(HIGHWAY_SPEED_KPH)}


def _base_class(highway: str) -> str:
    return highway.removesuffix("_link")


def fetch_overpass_roads(cache_path: str = OSM_CACHE_PATH) -> dict[str, Any]:
    """Download drivable OSM ways inside BBOX (cached on disk after the first download)."""
    if os.path.exists(cache_path):
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            return json.load(f)

    classes = "|".join(f"{c}|{c}_link" for c in HIGHWAY_SPEED_KPH)
    min_lon, min_lat, max_lon, max_lat = BBOX
    query = (
        f'[out:json][timeout:180];way["highway"~"^({classes})$"]'
        f"({min_lat},{min_lon},{max_lat},{max_lon});out geom;"
    )
    logger.info("downloading_osm_roads", url=OVERPASS_URL, bbox=BBOX)
    resp = httpx.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=240,
        headers={"User-Agent": "IDRA-research-prototype/1.0"},
    )
    resp.raise_for_status()
    data = resp.json()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with gzip.open(cache_path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def build_graph_from_osm(osm: dict[str, Any]) -> nx.DiGraph:
    """Build a simplified, connected road graph from Overpass `out geom` ways.

    Raw OSM nodes are collapsed so graph nodes are only junctions and dead ends; each edge
    keeps the full street geometry so routes follow the real road shape. Only the largest
    connected component is kept, so every snapped point can reach every other.
    """
    min_lon, min_lat, max_lon, max_lat = BBOX

    def in_bbox(lon: float, lat: float) -> bool:
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    coords: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, set[int]] = {}
    segments: dict[tuple[int, int], dict[str, Any]] = {}

    for way in osm.get("elements", []):
        if way.get("type") != "way" or "geometry" not in way:
            continue
        highway = _base_class(way.get("tags", {}).get("highway", ""))
        if highway not in HIGHWAY_SPEED_KPH:
            continue
        name = way.get("tags", {}).get("name")
        for (a, pa), (b, pb) in zip(
            zip(way["nodes"], way["geometry"], strict=False),
            zip(way["nodes"][1:], way["geometry"][1:], strict=False),
            strict=False,
        ):
            if a == b or not (in_bbox(pa["lon"], pa["lat"]) and in_bbox(pb["lon"], pb["lat"])):
                continue
            coords[a] = (pa["lon"], pa["lat"])
            coords[b] = (pb["lon"], pb["lat"])
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
            key = (min(a, b), max(a, b))
            prev = segments.get(key)
            if prev is None or HIGHWAY_RANK[highway] < HIGHWAY_RANK[prev["highway"]]:
                segments[key] = {"highway": highway, "name": name, "way_id": way["id"]}

    # Largest connected component (undirected) so routing never strands on an island
    seen: set[int] = set()
    largest: set[int] = set()
    for start in adjacency:
        if start in seen:
            continue
        component = {start}
        stack = [start]
        while stack:
            for nbr in adjacency[stack.pop()]:
                if nbr not in component:
                    component.add(nbr)
                    stack.append(nbr)
        seen |= component
        if len(component) > len(largest):
            largest = component

    keep = {n for n in largest if len(adjacency[n]) != 2}
    G = nx.DiGraph()
    for n in keep:
        lon, lat = coords[n]
        G.add_node(n, x=lon, y=lat, lon=lon, lat=lat)

    visited: set[tuple[int, int]] = set()
    for u in keep:
        for first in adjacency[u]:
            if (min(u, first), max(u, first)) in visited:
                continue
            chain = [u, first]
            while chain[-1] not in keep:
                prev, cur = chain[-2], chain[-1]
                chain.append(next(n for n in adjacency[cur] if n != prev))
            v = chain[-1]
            keys = [(min(x, y), max(x, y)) for x, y in zip(chain, chain[1:], strict=False)]
            visited.update(keys)
            if u == v:
                continue  # closed loop back to the same junction adds no connectivity

            geometry = [list(coords[n]) for n in chain]
            length_m = sum(
                haversine_m(*coords[x], *coords[y]) for x, y in zip(chain, chain[1:], strict=False)
            )
            best = min((segments[k] for k in keys), key=lambda seg: HIGHWAY_RANK[seg["highway"]])
            speed = HIGHWAY_SPEED_KPH[best["highway"]]
            name = next((segments[k]["name"] for k in keys if segments[k]["name"]), None)
            length_m = max(length_m, 1.0)
            attrs = {
                "length": length_m,
                "length_m": length_m,
                "speed_kph": speed,
                "travel_s": length_m / (speed * 1000.0 / 3600.0),
                "highway_class": best["highway"],
                "name": name,
                "osm_way_id": best["way_id"],
                "oneway": False,
            }
            # Parallel streets between the same two junctions: keep the shorter one
            if G.has_edge(u, v) and G[u][v]["length"] <= length_m:
                continue
            G.add_edge(u, v, geometry=geometry, **attrs)
            G.add_edge(v, u, geometry=geometry[::-1], **attrs)

    return G


async def persist_to_database(db: AsyncSession, G: nx.DiGraph) -> None:
    """Replace road_nodes and road_edges in PostgreSQL with the graph (edges keep street shape)."""
    logger.info("replacing_road_network_tables")
    await db.execute(delete(RoadEdge))
    await db.execute(delete(RoadNode))

    node_rows = [
        {"id": int(n), "geom": from_shape(Point(d["lon"], d["lat"]), srid=4326)}
        for n, d in G.nodes(data=True)
    ]
    for i in range(0, len(node_rows), 5000):
        await db.execute(insert(RoadNode), node_rows[i : i + 5000])
    logger.info("road_nodes_inserted", count=len(node_rows))

    edge_rows = [
        {
            "u": int(u),
            "v": int(v),
            "key": 0,
            "osm_way_id": d.get("osm_way_id"),
            "highway_class": d["highway_class"],
            "length_m": d["length_m"],
            "speed_kph": d["speed_kph"],
            "travel_s": d["travel_s"],
            "oneway": d["oneway"],
            "geom": from_shape(LineString(d["geometry"]), srid=4326),
        }
        for u, v, d in G.edges(data=True)
    ]
    for i in range(0, len(edge_rows), 5000):
        await db.execute(insert(RoadEdge), edge_rows[i : i + 5000])
    logger.info("road_edges_inserted", count=len(edge_rows))

    await db.commit()


def save_artifacts(G: nx.DiGraph) -> None:
    """Save road_graph.pkl and road_graph_manifest.json to artifacts/."""
    artifacts_dir = os.path.join(os.path.dirname(__file__), "../artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)

    pkl_path = os.path.join(artifacts_dir, "road_graph.pkl")
    manifest_path = os.path.join(artifacts_dir, "road_graph_manifest.json")

    logger.info("saving_graph_pickle", path=pkl_path)
    with open(pkl_path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

    manifest = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "bbox": BBOX,
        "source": (
            "OpenStreetMap drivable roads via Overpass API (© OpenStreetMap contributors, ODbL)"
        ),
        "extraction_date": G.graph.get("osm_timestamp"),
        "built_at": datetime.now(UTC).isoformat(),
        "version": "2.0.0",
    }

    logger.info("saving_manifest", path=manifest_path, manifest=manifest)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def build_road_graph() -> nx.DiGraph:
    """Build the routing graph from the (cached) OSM extract."""
    osm = fetch_overpass_roads()
    G = build_graph_from_osm(osm)
    G.graph["osm_timestamp"] = osm.get("osm3s", {}).get("timestamp_osm_base")
    return G


async def main() -> None:
    setup_logging("INFO")
    logger.info("building_road_graph_for_chennai_core", bbox=BBOX)

    G = build_road_graph()
    logger.info("graph_built", nodes=G.number_of_nodes(), edges=G.number_of_edges())

    save_artifacts(G)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        await persist_to_database(session, G)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
