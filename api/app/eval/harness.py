from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.eval.agent_eval import run_agent_evaluation
from app.eval.datasets import load_ui_study_results
from app.eval.gis_eval import run_gis_evaluation
from app.eval.rag_eval import run_rag_evaluation
from app.eval.system_eval import run_system_evaluation

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
DEFAULT_RESULTS_PATH = os.path.join(REPO_ROOT, "artifacts", "eval_results.json")


class EvaluationHarness:
    """Executes all evaluation suites and persists metrics to artifacts/eval_results.json."""

    def __init__(self, output_path: str = DEFAULT_RESULTS_PATH) -> None:
        self.output_path = output_path

    async def run_all(self, write_disk: bool = True) -> dict[str, Any]:
        """Execute RAG, Agent, GIS, System, and UI evaluation suites."""
        rag_res = run_rag_evaluation()
        gis_res = run_gis_evaluation()
        agent_res = await run_agent_evaluation()
        sys_res = await run_system_evaluation()
        ui_res = load_ui_study_results()

        all_metrics: dict[str, dict[str, Any]] = {}
        for suite in (rag_res, agent_res, gis_res, sys_res):
            for k, v in suite["metrics"].items():
                all_metrics[k] = {**v, "suite": suite["suite"]}

        total_automated = len(all_metrics)
        passed_automated = sum(1 for m in all_metrics.values() if m["passed"])

        payload: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "llm_backend": settings.LLM_BACKEND,
            "summary": {
                "total_automated_metrics": total_automated,
                "passed_automated_metrics": passed_automated,
                "missed_automated_metrics": total_automated - passed_automated,
                "pass_rate": round(passed_automated / max(total_automated, 1), 4),
                "ui_study_status": ui_res["study_status"],
            },
            "suites": {
                "rag_eval": rag_res,
                "agent_eval": agent_res,
                "gis_eval": gis_res,
                "system_eval": sys_res,
                "ui_study": ui_res,
            },
            "metrics": all_metrics,
        }

        if write_disk:
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

        return payload

    def load_latest(self) -> dict[str, Any] | None:
        """Load the most recently written evaluation results JSON if present."""
        if not os.path.exists(self.output_path):
            return None
        with open(self.output_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data


evaluation_harness = EvaluationHarness()
