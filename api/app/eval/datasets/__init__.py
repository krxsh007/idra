from __future__ import annotations

import json
import os
from typing import Any

DATASETS_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_FILES = {
    "retrieval_queries": "retrieval_queries.json",
    "assessment_cases": "assessment_cases.json",
    "routing_cases": "routing_cases.json",
    "facility_cases": "facility_cases.json",
    "resource_cases": "resource_cases.json",
    "citizen_queries": "citizen_queries.json",
    "conflict_cases": "conflict_cases.json",
    "ui_study_results": "ui_study_results.json",
}


def _load_json(filename: str) -> dict[str, Any]:
    path = os.path.join(DATASETS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def load_retrieval_queries() -> dict[str, Any]:
    """Load the 40 labelled RAG retrieval queries dataset."""
    return _load_json(DATASET_FILES["retrieval_queries"])


def load_assessment_cases() -> dict[str, Any]:
    """Load the 20 expert-labelled disaster assessment cases dataset."""
    return _load_json(DATASET_FILES["assessment_cases"])


def load_routing_cases() -> dict[str, Any]:
    """Load the 15 GIS routing cases (10 detour + 5 enclosure)."""
    return _load_json(DATASET_FILES["routing_cases"])


def load_facility_cases() -> dict[str, Any]:
    """Load the 10 facility matching cases (shelter split + hospital specialization)."""
    return _load_json(DATASET_FILES["facility_cases"])


def load_resource_cases() -> dict[str, Any]:
    """Load the 10 resource allocation cases."""
    return _load_json(DATASET_FILES["resource_cases"])


def load_citizen_queries() -> dict[str, Any]:
    """Load the 30 citizen assistance queries (15 urgent + 15 non-urgent) + injection tests."""
    return _load_json(DATASET_FILES["citizen_queries"])


def load_conflict_cases() -> dict[str, Any]:
    """Load the 8 conflict resolution test cases."""
    return _load_json(DATASET_FILES["conflict_cases"])


def load_ui_study_results() -> dict[str, Any]:
    """Load the UI human-factors evaluation instrument and recorded cohort results."""
    return _load_json(DATASET_FILES["ui_study_results"])


def load_all_datasets() -> dict[str, dict[str, Any]]:
    """Load all eight evaluation datasets."""
    return {name: _load_json(fname) for name, fname in DATASET_FILES.items()}
