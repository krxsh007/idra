from __future__ import annotations

import pytest
from app.eval.datasets import (
    load_all_datasets,
    load_assessment_cases,
    load_citizen_queries,
    load_conflict_cases,
    load_facility_cases,
    load_resource_cases,
    load_retrieval_queries,
    load_routing_cases,
    load_ui_study_results,
)
from app.eval.harness import evaluation_harness


def test_all_eight_eval_datasets_load_and_match_cardinality() -> None:
    """Verify all 8 committed evaluation datasets exist and satisfy Artifact 13 cardinalities."""
    all_ds = load_all_datasets()
    assert len(all_ds) == 8

    ret = load_retrieval_queries()
    assert len(ret["queries"]) == 40
    assert len(ret["out_of_domain_queries"]) == 5
    assert ret["inter_annotator_agreement"]["cohens_kappa"] >= 0.80

    ass = load_assessment_cases()
    assert len(ass["cases"]) == 20
    assert ass["inter_annotator_agreement"]["cohens_kappa"] >= 0.80

    rot = load_routing_cases()
    assert len(rot["detour_cases"]) == 10
    assert len(rot["enclosure_cases"]) == 5

    fac = load_facility_cases()
    assert len(fac["cases"]) == 10
    assert len([c for c in fac["cases"] if c["facility_type"] == "SHELTER"]) == 5
    assert len([c for c in fac["cases"] if c["facility_type"] == "HOSPITAL"]) == 5

    res = load_resource_cases()
    assert len(res["cases"]) == 10

    cit = load_citizen_queries()
    assert len(cit["urgent_queries"]) == 15
    assert len(cit["non_urgent_queries"]) == 15
    assert len(cit["injection_queries"]) == 5

    conf = load_conflict_cases()
    assert len(conf["cases"]) == 8

    ui = load_ui_study_results()
    assert ui["study_status"] == "AWAITING_HUMAN_PARTICIPANTS"
    assert ui["measured_human_metrics"]["sus_mean_score"] is None
    assert ui["measured_human_metrics"]["task_completion_rate"] is None


@pytest.mark.asyncio
async def test_evaluation_harness_deterministic_across_repeated_runs() -> None:
    """Verify the evaluation harness produces identical metric values across repeated runs."""
    run_1 = await evaluation_harness.run_all(write_disk=False)
    run_2 = await evaluation_harness.run_all(write_disk=False)

    assert run_1["summary"]["total_automated_metrics"] == 34
    assert (
        run_1["summary"]["passed_automated_metrics"] == run_2["summary"]["passed_automated_metrics"]
    )

    deterministic_suites = ["rag_eval", "agent_eval", "gis_eval", "system_eval"]
    for suite_name in deterministic_suites:
        metrics_1 = run_1["suites"][suite_name]["metrics"]
        metrics_2 = run_2["suites"][suite_name]["metrics"]
        assert set(metrics_1.keys()) == set(metrics_2.keys())
        for m_key in metrics_1:
            if "latency" in m_key:
                assert metrics_1[m_key]["passed"] is True
                assert metrics_2[m_key]["passed"] is True
            else:
                assert (
                    metrics_1[m_key]["value"] == metrics_2[m_key]["value"]
                ), f"Non-deterministic value for {suite_name}.{m_key}"
                assert metrics_1[m_key]["passed"] == metrics_2[m_key]["passed"]
