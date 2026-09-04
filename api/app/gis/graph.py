from __future__ import annotations

import json
import os
import pickle
from typing import Any

import networkx as nx

from app.core.config import settings
from app.core.logging import logger


class RoadGraphManager:
    _instance: RoadGraphManager | None = None
    _graph: nx.DiGraph | None = None
    _manifest: dict[str, Any] | None = None

    @classmethod
    def get_instance(cls) -> RoadGraphManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_graph(self) -> None:
        """Load the road network graph and validate its manifest bounding box."""
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
                manifest_bbox = self._manifest.get("bbox", [])
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
                return
            except Exception as e:
                logger.error("road_graph_pickle_load_failed", error=str(e))

        # Fallback: Construct minimal connected graph in-memory if artifact is missing
        logger.info("building_fallback_in_memory_road_graph")
        from scripts.load_road_network import build_chennai_road_graph

        self._graph = build_chennai_road_graph()
        self._manifest = {
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "bbox": [float(x.strip()) for x in settings.STUDY_AREA_BBOX.split(",")],
        }

    def get_graph(self) -> nx.DiGraph:
        if self._graph is None:
            self.load_graph()
        assert self._graph is not None
        return self._graph

    @property
    def is_loaded(self) -> bool:
        return self._graph is not None

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
