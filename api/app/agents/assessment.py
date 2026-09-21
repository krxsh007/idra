from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName, AgentStatus
from app.llm.guards import check_forbidden_language, fence_untrusted_input
from app.rag.retriever import retriever
from app.schemas.agents.assessment import (
    AssessmentInput,
    AssessmentOutput,
    Citation,
    CitationSourceType,
)

logger = structlog.get_logger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "assessment.md"


class DisasterAssessmentAgent(BaseAgent[AssessmentInput, AssessmentOutput]):
    """Agent that performs holistic disaster situation assessment using RAG and telemetry."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.DISASTER_ASSESSMENT,
            response_schema=AssessmentOutput,
        )

    async def _execute(
        self,
        ctx: RunContext,
        input_data: AssessmentInput,
    ) -> AssessmentOutput | AgentFailure:
        log = logger.bind(
            agent=self.agent_name.value,
            event_id=str(input_data.event.id),
        )

        # 1. SOP Context Retrieval
        query = (
            f"{input_data.event.disaster_type.value} response standard operating procedures "
            f"evacuation guidelines severity assessment"
        )
        if input_data.event.description:
            query = f"{query} {input_data.event.description}"

        chunks = await retriever.search(
            db=ctx.db,  # type: ignore[arg-type]
            query=query,
            top_k=5,
            disaster_type=input_data.event.disaster_type,
        )

        # 2. Invariant Check: No-LLM-Call Rule
        # If retrieval yielded no qualifying chunks (score_floor 0.35), return INSUFFICIENT_EVIDENCE
        if not chunks:
            log.warning(
                "assessment_aborted_insufficient_evidence",
                reason="No SOP chunks cleared score floor 0.35",
            )
            return AgentFailure(
                status=AgentStatus.INSUFFICIENT_EVIDENCE,
                code="INSUFFICIENT_EVIDENCE",
                message="No authoritative SOP guidelines found above score floor 0.35.",
                details={"query": query, "retrieved_chunks": 0},
            )

        # Format retrieved SOP chunks
        sop_context_lines = []
        for c in chunks:
            sop_context_lines.append(
                f"- [Chunk {c.chunk_id}] (Score: {c.hybrid_score:.2f}) {c.doc_title} "
                f"({c.section_path or 'General'}):\n{c.content}\n"
            )
        sop_context_str = "\n".join(sop_context_lines)

        # 3. Format telemetry and untrusted reports with XML fencing
        event_dict = {
            "id": str(input_data.event.id),
            "name": input_data.event.name,
            "disaster_type": input_data.event.disaster_type.value,
            "epicenter": {
                "lat": input_data.event.epicenter.lat,
                "lon": input_data.event.epicenter.lon,
            },
            "radius_m": input_data.event.radius_m,
            "description": input_data.event.description,
        }
        event_json = json.dumps(event_dict, indent=2)

        reports_list = []
        sum_reported_affected = 0
        any_casualties_in_reports = False

        for r in input_data.reports:
            if r.casualties_reported:
                any_casualties_in_reports = True
            if r.people_affected is not None and r.people_affected > 0:
                sum_reported_affected += r.people_affected

            # Untrusted citizen body is fenced
            fenced_body = fence_untrusted_input(r.body, label=f"report_{r.id}")
            reports_list.append({
                "id": str(r.id),
                "source": r.source.value,
                "location": {"lat": r.location.lat, "lon": r.location.lon},
                "casualties_reported": r.casualties_reported,
                "people_affected": r.people_affected,
                "content": fenced_body,
            })
        reports_json = json.dumps(reports_list, indent=2)

        hazards_list = []
        for hz in input_data.hazard_zones:
            hazards_list.append({
                "id": str(hz.id),
                "label": hz.label,
                "severity": hz.severity.value,
                "is_impassable": hz.is_impassable,
            })
        hazards_json = json.dumps(hazards_list, indent=2)
        weather_json = json.dumps(input_data.weather_context or {}, indent=2)

        # 4. Construct Prompt
        template = PROMPT_TEMPLATE_PATH.read_text()
        prompt = (
            template.replace("{event_json}", event_json)
            .replace("{reports_json}", reports_json)
            .replace("{hazards_json}", hazards_json)
            .replace("{weather_json}", weather_json)
            .replace("{sop_context}", sop_context_str)
        )

        # 5. Call LLM with automatic repair retry
        output = await self.call_llm_with_repair(
            ctx=ctx,
            prompt=prompt,
            system_instruction="You are an AI disaster response assessment expert.",
            temperature=0.1,
        )

        # 6. Post-processing Invariants & Guardrails
        # A. Forbidden language check
        forbidden_violations = check_forbidden_language(output.affected_area_summary)
        for factor in output.key_factors:
            forbidden_violations.extend(check_forbidden_language(factor))
        if forbidden_violations:
            log.warning("forbidden_language_detected", violations=forbidden_violations)

        # B. Clamp Rule: estimated_people_affected <= 10 * sum(reported people_affected)
        max_allowed_estimate = (
            10 * sum_reported_affected if sum_reported_affected > 0 else 500
        )
        if output.estimated_people_affected > max_allowed_estimate:
            log.warning(
                "clamping_estimated_people_affected",
                original=output.estimated_people_affected,
                clamped=max_allowed_estimate,
                sum_reported=sum_reported_affected,
            )
            output.estimated_people_affected = max_allowed_estimate

        # C. Evacuation Rule: Ensure key_factors references report or hazard
        if output.evacuation_recommended:
            has_report_or_hazard_ref = False
            for factor in output.key_factors:
                f_lower = factor.lower()
                if (
                    "report" in f_lower
                    or "hazard" in f_lower
                    or "water" in f_lower
                    or "flood" in f_lower
                    or "zone" in f_lower
                ):
                    has_report_or_hazard_ref = True
                    break
            if not has_report_or_hazard_ref:
                output.key_factors.append(
                    "Evacuation advised due to active hazard zones and incident reports."
                )
                if len(output.key_factors) > 5:
                    output.key_factors = output.key_factors[:5]

        # D. Casualties Reported alignment
        if any_casualties_in_reports and not output.casualties_reported:
            output.casualties_reported = True

        # E. Citation Fallback: Ensure at least one citation exists
        if not output.citations:
            top_chunk = chunks[0]
            output.citations = [
                Citation(
                    source_type=CitationSourceType.SOP,
                    source_id=str(top_chunk.chunk_id),
                    snippet=top_chunk.content[:200],
                    relevance_note="Top relevant SOP guideline for disaster type.",
                )
            ]

        output.visual_damage_indicator = input_data.visual_damage_indicator
        return output
