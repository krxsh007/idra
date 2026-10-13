from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, SeverityLevel
from app.gis.clustering import ClusterResult, cluster_incident_reports
from app.llm.guards import check_forbidden_language
from app.rag.retriever import retriever
from app.schemas.agents.planning import (
    PlanningCitation,
    PrioritizedZone,
    RescuePlanningInput,
    RescuePlanningOutput,
)
from app.schemas.events import EpicenterPoint

logger = structlog.get_logger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "planning.md"


class RescuePlanningAgent(BaseAgent[RescuePlanningInput, RescuePlanningOutput]):
    """Agent that produces prioritized rescue zones and operational sequences."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.RESCUE_PLANNING,
            response_schema=RescuePlanningOutput,
        )

    async def _execute(
        self,
        ctx: RunContext,
        input_data: RescuePlanningInput,
    ) -> RescuePlanningOutput | AgentFailure:
        log = logger.bind(agent=self.agent_name.value, event_id=str(input_data.event.id))
        log.info("rescue_planning_started")

        # 1. Skip if severity is LOW per PRD 8.3
        if input_data.assessment_severity == SeverityLevel.LOW:
            log.info("rescue_planning_skipped_low_severity")
            return RescuePlanningOutput(
                prioritized_zones=[],
                operation_sequence=["Monitor situation; no immediate tactical rescue required."],
                citations=[],
                origin="DETERMINISTIC_COMPUTATION",
            )

        # 2. Cluster reports into spatial zones deterministically
        clusters = cluster_incident_reports(
            input_data.reports,
            input_data.hazard_zones,
            eps_m=500.0,
            min_points=2,
        )
        if not clusters:
            log.info("rescue_planning_no_clusters")
            return RescuePlanningOutput(
                prioritized_zones=[],
                operation_sequence=["No active incident report clusters to sequence."],
                citations=[],
                origin="DETERMINISTIC_COMPUTATION",
            )

        # 3. Sort clusters by life-safety criteria:
        #    1) Casualties reported
        #    2) Accessibility: BLOCKED first, then CONSTRAINED, then ACCESSIBLE
        #    3) Descending people affected
        def cluster_rank_key(c: ClusterResult) -> tuple[int, int, int]:
            access_rank = (
                0
                if c.accessibility == "BLOCKED"
                else (1 if c.accessibility == "CONSTRAINED" else 2)
            )
            cas_rank = 0 if c.has_casualties else 1
            return (cas_rank, access_rank, -c.people_estimate)

        clusters.sort(key=cluster_rank_key)
        top_clusters = clusters[:8]

        # 4. Deterministic initial prioritized zones with unique contiguous priorities 1..N
        prioritized_zones: list[PrioritizedZone] = []
        for idx, c in enumerate(top_clusters, start=1):
            if c.has_casualties and c.accessibility == "BLOCKED":
                rat = (
                    f"Confirmed casualties and impassable hazard zone; immediate boat-based "
                    f"rescue extraction required for ~{c.people_estimate} people."
                )
            elif c.has_casualties:
                rat = (
                    f"Casualties reported requiring urgent medical evacuation and triage "
                    f"for ~{c.people_estimate} people."
                )
            elif c.accessibility == "BLOCKED":
                rat = (
                    f"Impassable inundation surrounding sector; watercraft access required "
                    f"for ~{c.people_estimate} stranded residents."
                )
            elif c.accessibility == "CONSTRAINED":
                rat = (
                    f"Constrained perimeter near hazard zone; perimeter staging required "
                    f"for ~{c.people_estimate} residents."
                )
            else:
                rat = (
                    f"Accessible sector with ~{c.people_estimate} affected residents "
                    f"requiring staged transport."
                )

            prioritized_zones.append(
                PrioritizedZone(
                    zone_label=f"Sector {idx} ({c.accessibility})",
                    centroid=EpicenterPoint(lon=c.centroid_lon, lat=c.centroid_lat),
                    priority=idx,
                    people_estimate=c.people_estimate,
                    accessibility=c.accessibility,  # type: ignore[arg-type]
                    rationale=rat,
                    report_ids=[r.id for r in c.reports],
                )
            )

        # 5. SOP Retrieval
        sop_citations: list[PlanningCitation] = []
        sop_context_str = "Standard emergency rescue procedures apply."
        query = (
            f"{input_data.event.disaster_type.value} rescue operation prioritization and sequencing"
        )

        if ctx.db is not None:
            try:
                chunks = await retriever.search(
                    db=ctx.db,
                    query=query,
                    top_k=5,
                    disaster_type=input_data.event.disaster_type,
                )
                if chunks:
                    sop_lines = []
                    for chunk in chunks:
                        sop_citations.append(
                            PlanningCitation(
                                chunk_id=chunk.chunk_id,
                                document_title=chunk.doc_title,
                                quoted_span=chunk.content[:200],
                                relevance_score=chunk.hybrid_score,
                            )
                        )
                        sop_lines.append(f"- [{chunk.doc_title}]: {chunk.content[:300]}")
                    sop_context_str = "\n".join(sop_lines)
            except Exception as e:
                log.warning("sop_retrieval_failed", error=str(e))

        # 6. Build deterministic baseline operation sequence
        op_seq = [
            (
                f"Deploy primary rescue team to {prioritized_zones[0].zone_label} "
                "for priority life-safety response."
            ),
        ]
        if len(prioritized_zones) > 1:
            op_seq.append(
                f"Stage perimeter evacuation resources at {prioritized_zones[1].zone_label}."
            )
        op_seq.extend(
            [
                "Confirm reception facility capacity before initiating mass transfers.",
                "Re-survey all operational sectors post-extraction and re-prioritize.",
            ]
        )

        # 7. LLM refinement if LLMClient is present and configured
        if ctx.llm and PROMPT_TEMPLATE_PATH.exists():
            try:
                template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
                clusters_payload = [z.model_dump(mode="json") for z in prioritized_zones]
                hazards_payload = [hz.model_dump(mode="json") for hz in input_data.hazard_zones]
                event_payload = input_data.event.model_dump(mode="json")

                prompt = (
                    template.replace("{event_json}", json.dumps(event_payload, indent=2))
                    .replace("{clusters_json}", json.dumps(clusters_payload, indent=2))
                    .replace("{hazards_json}", json.dumps(hazards_payload, indent=2))
                    .replace("{sop_context}", sop_context_str)
                )

                llm_res: RescuePlanningOutput = await asyncio.wait_for(
                    ctx.llm.structured(prompt=prompt, response_schema=RescuePlanningOutput),
                    timeout=ctx.llm_budget_s,
                )

                # Validate LLM output: ensure contiguous priorities and no forbidden language
                if llm_res and llm_res.prioritized_zones and len(llm_res.operation_sequence) >= 2:
                    forbid = check_forbidden_language(
                        " ".join(llm_res.operation_sequence)
                        + " "
                        + " ".join(z.rationale for z in llm_res.prioritized_zones)
                    )
                    if not forbid:
                        # Enforce contiguous priorities 1..N
                        for i, z in enumerate(llm_res.prioritized_zones, start=1):
                            z.priority = i
                        if not llm_res.citations and sop_citations:
                            llm_res.citations = sop_citations
                        return llm_res
            except Exception as e:
                log.warning("llm_rescue_planning_fallback", error=str(e))

        return RescuePlanningOutput(
            prioritized_zones=prioritized_zones,
            operation_sequence=op_seq,
            citations=sop_citations,
            origin="AI_GENERATED" if sop_citations else "DETERMINISTIC_COMPUTATION",
        )
