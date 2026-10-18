from __future__ import annotations

import gc
import json
import math
import os
import pickle
from typing import Any

import networkx as nx
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from app.core.config import settings
from app.core.logging import logger


def _exclude_from_gc() -> None:
    """Move the (large, long-lived) graph out of the cyclic GC's working set.

    The city graph is millions of objects; without this, every full collection walks all of
    them and stalls whichever route computation triggered it for hundreds of milliseconds.
    """
    gc.collect()
    gc.freeze()


class RoadGraphManager:
    _instance: RoadGraphManager | None = None
    _graph: nx.DiGraph | None = None
    _manifest: dict[str, Any] | None = None
    _unavailable: bool = False
    _edge_tree: STRtree | None = None
    _edge_pairs: list[tuple[int, int]] = []
    _node_arrays: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
    _node_xy: dict[int, tuple[float, float]] | None = None

    @classmethod
    def get_instance(cls) -> RoadGraphManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_unavailable(self, unavailable: bool) -> None:
        self._unavailable = unavailable

    def load_graph(self) -> None:
        """Load the road network graph and validate its manifest bounding box."""
        if self._unavailable:
            raise RuntimeError("ROAD_GRAPH_UNAVAILABLE")
        self._edge_tree = None
        self._node_arrays = None
        self._node_xy = None
        artifacts_dir = os.path.join(os.path.dirname(__file__), "../../../artifacts")
        pkl_path = os.path.join(artifacts_dir, "road_graph.pkl")
        manifest_path = os.path.join(artifacts_dir, "road_graph_manifest.json")

        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    self._manifest = json.load(f)
                logger.info("road_graph_manifest_loaded", manifest=self._manifest)

                # Validate bounding box
                expected_bbox = [float(x.strip()) for x in settings.STUDY_AREA_BBOX.split(",")]
                manifest_bbox = self._manifest.get("bbox", []) if self._manifest else []
                if len(manifest_bbox) == 4 and len(expected_bbox) == 4:
                    pairs = zip(manifest_bbox, expected_bbox, strict=False)
                    mismatch = any(abs(m - e) > 0.01 for m, e in pairs)
                    if mismatch:
                        logger.error(
                            "manifest_bbox_mismatch",
                            expected=expected_bbox,
                            manifest=manifest_bbox,
                        )
                        raise ValueError(
                            f"Road graph manifest bbox {manifest_bbox} != {expected_bbox}"
                        )
            except Exception as e:
                logger.warning("manifest_validation_error", error=str(e))
                if isinstance(e, ValueError):
                    raise

        if os.path.exists(pkl_path):
            try:
                logger.info("loading_road_graph_pickle", path=pkl_path)
                with open(pkl_path, "rb") as f:
                    self._graph = pickle.load(f)
                logger.info(
                    "road_graph_loaded_successfully",
                    nodes=self._graph.number_of_nodes(),
                    edges=self._graph.number_of_edges(),
                )
                _exclude_from_gc()
                return
            except Exception as e:
                logger.error("road_graph_pickle_load_failed", error=str(e))

        # No pickle (fresh clone): build from the committed OSM extract and cache it.
        logger.info("building_road_graph_from_osm_extract")
        from scripts.seed.load_road_network import build_road_graph, save_artifacts

        self._graph = build_road_graph()
        save_artifacts(self._graph)
        _exclude_from_gc()
        with open(manifest_path, encoding="utf-8") as f:
            self._manifest = json.load(f)

    def get_graph(self) -> nx.DiGraph:
        if self._unavailable:
            raise RuntimeError("ROAD_GRAPH_UNAVAILABLE")
        if self._graph is None:
            self.load_graph()
        assert self._graph is not None
        return self._graph

    def node_arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Node ids, longitudes and latitudes as arrays for vectorised nearest-node lookup."""
        if self._node_arrays is None:
            G = self.get_graph()
            ids = np.fromiter(G.nodes, dtype=np.int64, count=G.number_of_nodes())
            lons = np.array([G.nodes[n].get("lon", G.nodes[n].get("x")) for n in ids], float)
            lats = np.array([G.nodes[n].get("lat", G.nodes[n].get("y")) for n in ids], float)
            self._node_arrays = (ids, lons, lats)
        return self._node_arrays

    def node_xy(self) -> dict[int, tuple[float, float]]:
        """Node positions in metres on a local equirectangular plane (for A* distance bounds)."""
        if self._node_xy is None:
            ids, lons, lats = self.node_arrays()
            r = 6371000.0
            lat0 = math.radians(float(lats.mean())) if len(lats) else 0.0
            xs = np.radians(lons) * math.cos(lat0) * r
            ys = np.radians(lats) * r
            self._node_xy = {
                int(n): (float(x), float(y)) for n, x, y in zip(ids, xs, ys, strict=True)
            }
        return self._node_xy

    def edges_intersecting(self, geom: BaseGeometry) -> set[tuple[int, int]]:
        """Directed (u, v) pairs whose street geometry intersects `geom` (e.g. a hazard polygon)."""
        G = self.get_graph()
        if self._edge_tree is None:
            pairs: list[tuple[int, int]] = []
            lines: list[LineString] = []
            for u, v, data in G.edges(data=True):
                if u > v and G.has_edge(v, u):
                    continue  # index each two-way street once
                geometry = data.get("geometry") or [
                    [G.nodes[n]["lon"], G.nodes[n]["lat"]] for n in (u, v)
                ]
                pairs.append((u, v))
                lines.append(LineString(geometry))
            self._edge_pairs = pairs
            self._edge_tree = STRtree(lines)

        hits: set[tuple[int, int]] = set()
        for idx in self._edge_tree.query(geom, predicate="intersects"):
            u, v = self._edge_pairs[int(idx)]
            hits.add((u, v))
            hits.add((v, u))
        return hits

    @property
    def is_loaded(self) -> bool:
        return not self._unavailable and self._graph is not None

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes() if self._graph is not None else 0

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges() if self._graph is not None else 0

    @property
    def manifest(self) -> dict[str, Any]:
        return self._manifest or {}


road_graph_manager = RoadGraphManager.get_instance()
