from __future__ import annotations

import asyncio
import json
import math
import os
import pickle
from datetime import UTC, datetime

import networkx as nx
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.roads import RoadEdge, RoadNode
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy import func, select
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


def build_chennai_road_graph() -> nx.DiGraph:
    """Construct a high-fidelity connected directed road graph for Chennai core bbox."""
    G = nx.DiGraph()

    # Define key Chennai arterial corridors (nodes and sequence)
    # 1. Anna Salai / Mount Road (SW to NE)
    anna_salai = [
        (1001, 80.180, 12.980, "Kathipara Junction"),
        (1002, 80.205, 13.010, "Guindy"),
        (1003, 80.220, 13.025, "Saidapet"),
        (1004, 80.235, 13.040, "Nandanam"),
        (1005, 80.245, 13.055, "Teynampet"),
        (1006, 80.255, 13.068, "Thousand Lights"),
        (1007, 80.270, 13.080, "Chennai Central / Park"),
    ]

    # 2. Poonamallee High Road (W to E)
    ph_road = [
        (2001, 80.160, 13.070, "Maduravoyal"),
        (2002, 80.190, 13.072, "Koyambedu CMBT"),
        (2003, 80.215, 13.075, "Aminjikarai"),
        (2004, 80.240, 13.078, "Kilpauk"),
        (1007, 80.270, 13.080, "Chennai Central / Park"),  # Junction
    ]

    # 3. Kamarajar Salai / Marina Beach Road (S to N)
    marina_road = [
        (3001, 80.265, 12.990, "Thiruvanmiyur"),
        (3002, 80.270, 13.010, "Besant Nagar / Adyar"),
        (3003, 80.275, 13.035, "Santhome"),
        (3004, 80.280, 13.060, "Marina Beach / Ice House"),
        (3005, 80.285, 13.085, "Fort St. George / Port"),
    ]

    # 4. GST Road (South to Kathipara)
    gst_road = [
        (4001, 80.160, 12.960, "Airport Subway"),
        (4002, 80.170, 12.970, "Meenambakkam"),
        (1001, 80.180, 12.980, "Kathipara Junction"),  # Junction
    ]

    # 5. Velachery Main Road & OMR (South to Central)
    velachery_omr = [
        (5001, 80.215, 12.965, "Velachery Vijayanagar"),
        (5002, 80.230, 12.985, "Taramani / SRP Tools"),
        (3002, 80.270, 13.010, "Besant Nagar / Adyar"),  # Junction
    ]

    # Add corridors to graph
    corridors = [
        (anna_salai, "primary", 50.0),
        (ph_road, "primary", 50.0),
        (marina_road, "primary", 50.0),
        (gst_road, "primary", 50.0),
        (velachery_omr, "primary", 45.0),
    ]

    for corridor_nodes, hw_class, speed in corridors:
        for i in range(len(corridor_nodes) - 1):
            u_id, u_lon, u_lat, _ = corridor_nodes[i]
            v_id, v_lon, v_lat, _ = corridor_nodes[i + 1]

            if not G.has_node(u_id):
                G.add_node(u_id, x=u_lon, y=u_lat, lon=u_lon, lat=u_lat)
            if not G.has_node(v_id):
                G.add_node(v_id, x=v_lon, y=v_lat, lon=v_lon, lat=v_lat)

            dist_m = max(10.0, haversine_m(u_lon, u_lat, v_lon, v_lat))
            travel_s = dist_m / (speed * 1000.0 / 3600.0)

            # Bidirectional arterial
            G.add_edge(
                u_id,
                v_id,
                length_m=dist_m,
                speed_kph=speed,
                travel_s=travel_s,
                highway_class=hw_class,
                oneway=False,
            )
            G.add_edge(
                v_id,
                u_id,
                length_m=dist_m,
                speed_kph=speed,
                travel_s=travel_s,
                highway_class=hw_class,
                oneway=False,
            )

    # 6. Grid Densification across Chennai Core BBox so distance to nearest node is <= 400m
    # 80.15 to 80.30 (approx 16km, step ~0.0035 deg ≈ 380m)
    # 12.95 to 13.15 (approx 22km, step ~0.0035 deg ≈ 380m)
    lons = [round(80.155 + i * 0.004, 5) for i in range(36)]
    lats = [round(12.955 + j * 0.004, 5) for j in range(48)]

    grid_node_ids: dict[tuple[int, int], int] = {}
    node_id_counter = 10000

    for i, lon in enumerate(lons):
        for j, lat in enumerate(lats):
            n_id = node_id_counter
            node_id_counter += 1
            grid_node_ids[(i, j)] = n_id
            G.add_node(n_id, x=lon, y=lat, lon=lon, lat=lat)

    # Connect grid nodes to adjacent neighbors (horizontal and vertical local streets)
    for i in range(len(lons)):
        for j in range(len(lats)):
            curr_id = grid_node_ids[(i, j)]
            curr_lon, curr_lat = lons[i], lats[j]

            # Horizontal edge
            if i + 1 < len(lons):
                next_id = grid_node_ids[(i + 1, j)]
                next_lon, next_lat = lons[i + 1], lats[j]
                dist_m = max(5.0, haversine_m(curr_lon, curr_lat, next_lon, next_lat))
                travel_s = dist_m / (30.0 * 1000.0 / 3600.0)
                G.add_edge(
                    curr_id,
                    next_id,
                    length_m=dist_m,
                    speed_kph=30.0,
                    travel_s=travel_s,
                    highway_class="residential",
                    oneway=False,
                )
                G.add_edge(
                    next_id,
                    curr_id,
                    length_m=dist_m,
                    speed_kph=30.0,
                    travel_s=travel_s,
                    highway_class="residential",
                    oneway=False,
                )

            # Vertical edge
            if j + 1 < len(lats):
                next_id = grid_node_ids[(i, j + 1)]
                next_lon, next_lat = lons[i], lats[j + 1]
                dist_m = max(5.0, haversine_m(curr_lon, curr_lat, next_lon, next_lat))
                travel_s = dist_m / (30.0 * 1000.0 / 3600.0)
                G.add_edge(
                    curr_id,
                    next_id,
                    length_m=dist_m,
                    speed_kph=30.0,
                    travel_s=travel_s,
                    highway_class="residential",
                    oneway=False,
                )
                G.add_edge(
                    next_id,
                    curr_id,
                    length_m=dist_m,
                    speed_kph=30.0,
                    travel_s=travel_s,
                    highway_class="residential",
                    oneway=False,
                )

    # Connect arterial nodes to closest grid nodes
    for corridor_nodes, _, _ in corridors:
        for u_id, u_lon, u_lat, _ in corridor_nodes:
            # Find closest grid node
            closest_grid = min(
                grid_node_ids.values(),
                key=lambda gid: haversine_m(u_lon, u_lat, G.nodes[gid]["lon"], G.nodes[gid]["lat"]),
            )
            g_lon, g_lat = G.nodes[closest_grid]["lon"], G.nodes[closest_grid]["lat"]
            dist_m = max(5.0, haversine_m(u_lon, u_lat, g_lon, g_lat))
            travel_s = dist_m / (40.0 * 1000.0 / 3600.0)

            G.add_edge(
                u_id,
                closest_grid,
                length_m=dist_m,
                speed_kph=40.0,
                travel_s=travel_s,
                highway_class="secondary",
                oneway=False,
            )
            G.add_edge(
                closest_grid,
                u_id,
                length_m=dist_m,
                speed_kph=40.0,
                travel_s=travel_s,
                highway_class="secondary",
                oneway=False,
            )

    return G


async def persist_to_database(db: AsyncSession, G: nx.DiGraph) -> None:
    """Populate road_nodes and road_edges tables in PostgreSQL."""
    logger.info("checking_existing_road_network_tables")

    count_res = await db.execute(select(func.count()).select_from(RoadNode))
    existing_nodes = count_res.scalar_one()

    if existing_nodes > 0:
        logger.info("road_nodes_already_populated", count=existing_nodes)
        return

    logger.info("inserting_road_nodes", count=G.number_of_nodes())
    # 1. Insert Nodes in batches
    node_objects = []
    for n_id, data in G.nodes(data=True):
        pt = from_shape(Point(data["lon"], data["lat"]), srid=4326)
        node_objects.append(RoadNode(id=n_id, geom=pt))

    db.add_all(node_objects)
    await db.flush()

    # 2. Insert Edges in batches
    logger.info("inserting_road_edges", count=G.number_of_edges())
    edge_objects = []
    for u, v, data in G.edges(data=True):
        u_pt = (G.nodes[u]["lon"], G.nodes[u]["lat"])
        v_pt = (G.nodes[v]["lon"], G.nodes[v]["lat"])
        line = from_shape(LineString([u_pt, v_pt]), srid=4326)

        edge_objects.append(
            RoadEdge(
                u=u,
                v=v,
                key=0,
                osm_way_id=None,
                highway_class=data.get("highway_class", "residential"),
                length_m=data["length_m"],
                speed_kph=data["speed_kph"],
                travel_s=data["travel_s"],
                oneway=data.get("oneway", False),
                geom=line,
            )
        )

        if len(edge_objects) >= 2000:
            db.add_all(edge_objects)
            await db.flush()
            edge_objects = []

    if edge_objects:
        db.add_all(edge_objects)
        await db.flush()

    await db.commit()
    logger.info("database_persistence_complete")


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
        "extraction_date": datetime.now(UTC).isoformat(),
        "version": "1.0.0",
    }

    logger.info("saving_manifest", path=manifest_path, manifest=manifest)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


async def main() -> None:
    setup_logging("INFO")
    logger.info("building_road_graph_for_chennai_core", bbox=BBOX)

    G = build_chennai_road_graph()
    logger.info("graph_built", nodes=G.number_of_nodes(), edges=G.number_of_edges())

    save_artifacts(G)

    try:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            await persist_to_database(session, G)
        await engine.dispose()
    except Exception as e:
        logger.warning(
            "database_save_skipped",
            reason=f"Could not connect to database or already seeded: {e}",
        )


if __name__ == "__main__":
    asyncio.run(main())
