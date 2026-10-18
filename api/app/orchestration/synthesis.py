from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import structlog
from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.db.models.enums import AgentName
from app.llm.guards import check_forbidden_language
from app.schemas.agents.planning import PlanningCitation
from app.schemas.agents.synthesis import (
    SynthesisInput,
    SynthesisItem,
    SynthesisOutput,
)

logger = structlog.get_logger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "synthesis.md"


def _ends_with_name_prefix(phrase: str, allowed_name: str) -> bool:
    """True if `phrase` ends with the leading words of `allowed_name` (at least two).

    The facility regex also captures capitalised words before a name ("Dispatch Guindy
    Higher Secondary School"), and models often drop a trailing word ("... Camp").
    Anchoring on the name's first word keeps invented names ("Adyar Higher Secondary
    School") rejected.
    """
    phrase_words = phrase.lower().split()
    name_words = allowed_name.lower().split()
    for k in range(min(len(phrase_words), len(name_words)), 1, -1):
        if phrase_words[-k:] == name_words[:k]:
            return True
    return False


class SynthesisAgent(BaseAgent[SynthesisInput, SynthesisOutput]):
    """Synthesizes agent outputs into a prioritized briefing with consistency checking."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.SYNTHESIS,
            response_schema=SynthesisOutput,
        )

    def _build_deterministic_recommendations(
        self, input_data: SynthesisInput
    ) -> list[SynthesisItem]:
        """Map structured agent outputs to deterministic 5-level priority recommendations."""
        items: list[SynthesisItem] = []

        # 1. Life Safety: Casualty rescue & evacuation of BLOCKED zones (Priority 1)
        plan_out = input_data.planning_output or {}
        zones = plan_out.get("prioritized_zones", [])
        sop_cits = [PlanningCitation.model_validate(c) for c in plan_out.get("citations", [])]

        for z in zones:
            access = z.get("accessibility")
            z_label = z.get("zone_label", "Sector")
            p_est = z.get("people_estimate", 0)

            if access == "BLOCKED" or z.get("priority") == 1:
                items.append(
                    SynthesisItem(
                        priority=1,
                        agent=AgentName.RESCUE_PLANNING,
                        title=f"Life-Safety Rescue: {z_label}",
                        body=(
                            f"Deploy high-priority watercraft and rescue personnel to {z_label}. "
                            f"Impassable inundation affecting ~{p_est} stranded individuals."
                        ),
                        origin="DETERMINISTIC_COMPUTATION",
                        structured_ref={"zone_label": z_label, "people_estimate": p_est},
                        citations=sop_cits[:2],
                    )
                )
            elif access == "CONSTRAINED":
                # Priority 2: Evacuation of CONSTRAINED zones
                items.append(
                    SynthesisItem(
                        priority=2,
                        agent=AgentName.RESCUE_PLANNING,
                        title=f"Perimeter Evacuation: {z_label}",
                        body=(
                            f"Establish staging perimeter around {z_label} for staged evacuation "
                            f"of approximately {p_est} residents."
                        ),
                        origin="DETERMINISTIC_COMPUTATION",
                        structured_ref={"zone_label": z_label, "people_estimate": p_est},
                        citations=sop_cits[:1],
                    )
                )

        # 2. Hospitals (Priority 1 if casualties) and Shelters (Priority 2)
        fac_out = input_data.facilities_output or {}
        for h in fac_out.get("recommended_hospitals", []):
            h_name = h.get("name", "Hospital Depot")
            items.append(
                SynthesisItem(
                    priority=1,
                    agent=AgentName.HOSPITAL_RECOMMENDATION,
                    title=f"Medical Routing: {h_name}",
                    body=(
                        f"Direct trauma and emergency casualties to {h_name}. "
                        f"Available capacity: {h.get('available_capacity', 0)} beds. "
                        f"Proximity: {h.get('distance_m', 0):.0f}m."
                    ),
                    origin="DETERMINISTIC_COMPUTATION",
                    structured_ref={"facility_id": h.get("facility_id")},
                )
            )

        for s in fac_out.get("recommended_shelters", []):
            s_name = s.get("name", "Shelter Facility")
            items.append(
                SynthesisItem(
                    priority=2,
                    agent=AgentName.SHELTER_ALLOCATION,
                    title=f"Evacuation Reception: {s_name}",
                    body=(
                        f"Open emergency reception at {s_name} with "
                        f"{s.get('available_capacity', 0)} available capacity. "
                        f"Proximity: {s.get('distance_m', 0):.0f}m."
                    ),
                    origin="DETERMINISTIC_COMPUTATION",
                    structured_ref={"facility_id": s.get("facility_id")},
                )
            )

        # 3. Resources (Priority 3 for P1-2 zones, Priority 4 for remaining)
        res_out = input_data.resources_output or {}
        for alloc in res_out.get("allocations", []):
            prio = alloc.get("priority", 3)
            synth_prio = 3 if prio <= 2 else 4
            items.append(
                SynthesisItem(
                    priority=synth_prio,
                    agent=AgentName.RESOURCE_COORDINATION,
                    title=f"Dispatch {alloc.get('label')}: {alloc.get('target_zone_label')}",
                    body=(
                        f"Dispatch {alloc.get('quantity')} units of {alloc.get('resource_kind')} "
                        f"to {alloc.get('target_zone_label')}. {alloc.get('rationale', '')}"
                    ),
                    origin="DETERMINISTIC_COMPUTATION",
                    structured_ref={"resource_id": alloc.get("resource_id")},
                )
            )

        # 4. Monitoring & Re-survey (Priority 5)
        items.append(
            SynthesisItem(
                priority=5,
                agent=AgentName.DISASTER_ASSESSMENT,
                title="Continuous Situational Monitoring & Re-survey",
                body=(
                    f"Maintain telemetry monitoring on {input_data.event.name}. "
                    f"Conduct re-survey of sectors and update hazard perimeters hourly."
                ),
                origin="DETERMINISTIC_COMPUTATION",
                structured_ref={"event_id": str(input_data.event.id)},
            )
        )

        items.sort(key=lambda x: x.priority)
        return items

    def _validate_consistency(
        self,
        candidate_output: SynthesisOutput,
        allowed_facility_names: set[str],
    ) -> bool:
        """Verify candidate output does not invent facility names."""
        full_text = (
            candidate_output.executive_summary
            + " "
            + " ".join(r.title + " " + r.body for r in candidate_output.recommendations)
        )

        # Forbidden language check
        if check_forbidden_language(full_text):
            return False

        # Check for hallucinated facilities:
        # Match common facility keywords
        pattern = re.compile(
            r"\b([A-Z][a-zA-Z0-9\s]+(?:Hospital|Shelter|Center|Clinic|Depot|School|Hall|College))\b"
        )
        found_facilities = set(pattern.findall(full_text))

        for fac in found_facilities:
            # Check if fac or a significant substring is in allowed_facility_names
            cleaned = fac.strip()
            if len(cleaned) < 5:
                continue
            is_valid = any(
                cleaned.lower() in allowed.lower()
                or allowed.lower() in cleaned.lower()
                or _ends_with_name_prefix(cleaned, allowed)
                for allowed in allowed_facility_names
            )
            if not is_valid and allowed_facility_names:
                logger.warning("hallucinated_facility_detected", hallucinated=cleaned)
                return False

        return True

    async def _execute(
        self,
        ctx: RunContext,
        input_data: SynthesisInput,
    ) -> SynthesisOutput | AgentFailure:
        log = logger.bind(agent=self.agent_name.value, event_id=str(input_data.event.id))
        log.info("synthesis_started")

        # 1. Deterministic baseline recommendations
        deterministic_recs = self._build_deterministic_recommendations(input_data)

        # Collect allowed facility names for consistency check
        fac_out = input_data.facilities_output or {}
        allowed_facilities: set[str] = set()
        for h in fac_out.get("recommended_hospitals", []):
            if h.get("name"):
                allowed_facilities.add(h["name"])
        for s in fac_out.get("recommended_shelters", []):
            if s.get("name"):
                allowed_facilities.add(s["name"])

        conflicts_out = input_data.conflicts_output or {}
        conflicts_noted = conflicts_out.get("conflicts_resolved", []) + conflicts_out.get(
            "conflicts_detected", []
        )

        # Baseline summary
        assessment_out = input_data.assessment_output or {}
        baseline_summary = (
            f"IDRA Situational Briefing for {input_data.event.name}. "
            f"Assessed severity is {assessment_out.get('severity', 'UNKNOWN')} with "
            f"{assessment_out.get('estimated_people_affected', 0)} estimated affected population. "
            f"Identified {len(deterministic_recs)} prioritized operational recommendations across "
            f"rescue, facility reception, and resource coordination sectors."
        )

        baseline_output = SynthesisOutput(
            executive_summary=baseline_summary,
            recommendations=deterministic_recs,
            conflicts_noted=conflicts_noted,
        )

        # 2. LLM prose generation if LLMClient configured
        if ctx.llm and PROMPT_TEMPLATE_PATH.exists():
            template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
            prompt = (
                template.replace(
                    "{event_json}", json.dumps(input_data.event.model_dump(mode="json"), indent=2)
                )
                .replace("{assessment_json}", json.dumps(assessment_out, indent=2))
                .replace(
                    "{recommendations_json}",
                    json.dumps([r.model_dump(mode="json") for r in deterministic_recs], indent=2),
                )
                .replace("{conflicts_json}", json.dumps(conflicts_noted, indent=2))
            )

            # Try up to 2 attempts (1 initial + 1 repair regeneration), within the LLM budget
            # so a slow provider still leaves time to return the deterministic baseline.
            deadline = asyncio.get_running_loop().time() + ctx.llm_budget_s
            for attempt in range(2):
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    res: SynthesisOutput = await asyncio.wait_for(
                        ctx.llm.structured(prompt=prompt, response_schema=SynthesisOutput),
                        timeout=remaining,
                    )
                    if res and len(res.recommendations) > 0:
                        # Enforce priority locking from deterministic mapping
                        for idx, rec in enumerate(res.recommendations):
                            if idx < len(deterministic_recs):
                                rec.priority = deterministic_recs[idx].priority
                                rec.agent = deterministic_recs[idx].agent

                        if self._validate_consistency(res, allowed_facilities):
                            res.conflicts_noted = conflicts_noted
                            # Provenance is decided here, not by the model: it sees the
                            # deterministic draft (origin included) and tends to copy it.
                            for rec in res.recommendations:
                                rec.origin = "AI_GENERATED"
                            return res
                except Exception as e:
                    log.warning("synthesis_llm_attempt_failed", attempt=attempt, error=str(e))

        # Fallback to deterministic template
        log.info("synthesis_using_deterministic_template_fallback")
        return baseline_output
