from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Literal

import structlog

from app.agents.base import AgentFailure, BaseAgent, RunContext
from app.core.config import settings
from app.db.models.enums import AgentName
from app.gis.spatial import get_nearby_facilities
from app.rag.retriever import retriever
from app.schemas.assistant import (
    CitizenAgentCitation,
    CitizenAgentLLMOutput,
    CitizenQueryRequest,
    CitizenQueryResponse,
    NearestFacilityItem,
)

logger = structlog.get_logger(__name__)

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "citizen.md"

OFFICIAL_HELPLINES = {"112", "1077", "1070", "108", "104", "101", "100"}

SAFE_FALLBACK_TEXT = (
    "For your safety, please contact official emergency services immediately. "
    "National Emergency Helpline: 112 | Tamil Nadu State Disaster Control: 1070 | "
    "Chennai District Disaster Control: 1077 | Medical Emergency: 108. "
    "Please follow instructions from local authorities and first responders."
)

DISCLAIMER_TEXT = (
    "DISCLAIMER: IDRA Citizen Assistant provides automated advisory information "
    "based on published disaster management guidelines. In an immediate life-threatening "
    "emergency, call 112 or 1077 immediately. Automated advice does not replace official "
    "emergency services instructions."
)

# Deterministic escalation regex patterns
LIFE_THREATENING_PATTERN = re.compile(
    r"\b("
    r"trapped|marooned|drowning|swept\s+away|washed\s+away|"
    r"unconscious|unresponsive|not\s+breathing|cardiac\s+arrest|heart\s+attack|"
    r"electrocution|electric\s+shock|live\s+wire|sparking\s+wire|"
    r"severe\s+bleeding|profuse\s+bleeding|hemorrhage|"
    r"save\s+us|we\s+are\s+dying|dying|urgent\s+rescue|send\s+boat\s+immediately|"
    r"water\s+rising\s+fast|water\s+at\s+neck|water\s+reaching\s+ceiling"
    r")\b",
    re.IGNORECASE,
)

URGENT_PATTERN = re.compile(
    r"\b("
    r"rising\s+water|water\s+level\s+rising|water\s+entering\s+house|water\s+inside\s+house|"
    r"stranded|submerged|chest\s+pain|broken\s+bone|severe\s+injury|"
    r"elderly\s+stuck|baby\s+stuck|infant\s+stuck|need\s+ambulance|need\s+rescue"
    r")\b",
    re.IGNORECASE,
)

CERTAINTY_PATTERN = re.compile(
    r"\b(guarantee|guaranteed|definitely)\b",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r"https?://[^\s)\]]+|www\.[^\s)\]]+", re.IGNORECASE)

# Pattern to detect potential phone numbers (e.g. 7-12 digits or formatted numbers)
PHONE_CANDIDATE_PATTERN = re.compile(
    r"(?:\+?91[\s-]?)?[6-9]\d{9}|\b\d{3,4}[\s-]?\d{3,4}[\s-]?\d{3,4}\b|\b\d{7,12}\b"
)


def check_escalation(
    query: str,
) -> tuple[bool, str | None, Literal["NONE", "URGENT", "LIFE_THREATENING"]]:
    """Deterministically detect life-threatening or urgent indicators in text."""
    if LIFE_THREATENING_PATTERN.search(query):
        return (
            True,
            "Detected life-threatening emergency keywords in citizen query.",
            "LIFE_THREATENING",
        )
    if URGENT_PATTERN.search(query):
        return (
            True,
            "Detected urgent rescue or medical assistance indicators in citizen query.",
            "URGENT",
        )
    return False, None, "NONE"


def check_output_safety(text: str, allowed_urls: set[str]) -> list[str]:
    """Validate generated answer against unauthorized phones, URLs, and certainty words."""
    violations: list[str] = []

    # 1. Absolute certainty language
    if CERTAINTY_PATTERN.search(text):
        violations.append("Contains forbidden absolute-certainty language (guarantee/definitely).")

    # 2. Unauthorized URLs
    found_urls = URL_PATTERN.findall(text)
    for url in found_urls:
        clean_url = url.strip(".,;:\"'")
        if clean_url not in allowed_urls:
            violations.append(f"Contains unauthorized URL: {clean_url}")

    # 3. Unauthorized phone numbers
    found_phones = PHONE_CANDIDATE_PATTERN.findall(text)
    for candidate in found_phones:
        digits_only = re.sub(r"\D", "", candidate)
        # Check if digits match any official helpline exactly
        if digits_only not in OFFICIAL_HELPLINES:
            # Avoid flagging years like 2024/2026 or simple distance values
            if len(digits_only) >= 7 or (
                len(digits_only) in (3, 4, 5) and digits_only not in OFFICIAL_HELPLINES
            ):
                violations.append(f"Contains unauthorized phone number: {candidate}")

    return violations


class CitizenAssistanceAgent(BaseAgent[CitizenQueryRequest, CitizenQueryResponse]):
    """Agent that answers citizen safety queries grounded in SOP guidelines."""

    def __init__(self) -> None:
        super().__init__(
            agent_name=AgentName.CITIZEN_ASSISTANCE,
            response_schema=CitizenQueryResponse,
        )

    async def _execute(
        self, ctx: RunContext, input_data: CitizenQueryRequest
    ) -> CitizenQueryResponse | AgentFailure:
        log = logger.bind(
            agent=self.agent_name.value,
            session_id=str(input_data.session_id) if input_data.session_id else None,
        )

        # 1. Deterministic escalation check (cannot be bypassed by LLM)
        is_escalated, esc_reason, safety_flag = check_escalation(input_data.query)

        # 2. Nearest facility lookup if location is available
        nearest_facs: list[NearestFacilityItem] = []
        if input_data.location is not None and ctx.db is not None:
            try:
                fac_results = await get_nearby_facilities(
                    db=ctx.db,
                    lon=input_data.location.lon,
                    lat=input_data.location.lat,
                    radius_m=settings.DEFAULT_SHELTER_SEARCH_RADIUS_M,
                    facility_type=None,
                    is_operational=True,
                    limit=3,
                )
                for fr in fac_results:
                    nearest_facs.append(
                        NearestFacilityItem(
                            facility_id=fr.facility.id,
                            name=fr.facility.name,
                            facility_type=fr.facility.facility_type,
                            distance_m=round(fr.distance_m, 1),
                            capacity_provenance="SIMULATED",
                        )
                    )
            except Exception as e:
                log.warning("facility_lookup_failed", error=str(e))

        # 3. RAG Retrieval with score floor check
        rag_query = input_data.query
        chunks = []
        if ctx.db is not None:
            try:
                chunks = await retriever.search(
                    db=ctx.db,
                    query=rag_query,
                    top_k=settings.RAG_TOP_K_CITIZEN,
                )
            except Exception as e:
                log.warning("citizen_rag_retrieval_failed", error=str(e))

        # INVARIANT: If RAG produces 0 chunks above score floor ->
        # ZERO LLM CALLS -> Return safe fallback
        if not chunks:
            log.info("citizen_rag_below_floor_using_safe_fallback", query=input_data.query[:50])
            fallback_answer = SAFE_FALLBACK_TEXT
            if is_escalated:
                fallback_answer = (
                    "URGENT: Emergency indicators detected. Please reach high ground immediately. "
                    + SAFE_FALLBACK_TEXT
                )
            return CitizenQueryResponse(
                session_id=input_data.session_id or uuid.uuid4(),
                answer=fallback_answer,
                citations=[],
                nearest_facilities=nearest_facs,
                escalated=is_escalated,
                escalation_reason=esc_reason,
                safety_flag=safety_flag,
                disclaimer=DISCLAIMER_TEXT,
            )

        # Prepare citations from retrieved chunks
        sop_lines: list[str] = []
        citations_list: list[CitizenAgentCitation] = []
        allowed_urls: set[str] = set()

        for c in chunks:
            citations_list.append(
                CitizenAgentCitation(
                    chunk_id=c.chunk_id,
                    document_title=c.doc_title,
                    quoted_span=c.content[:200],
                    relevance_score=c.hybrid_score,
                )
            )
            sop_lines.append(f"- [Chunk {c.chunk_id}] ({c.doc_title}): {c.content}")

        sop_context_str = "\n".join(sop_lines)
        facs_json = json.dumps([f.model_dump(mode="json") for f in nearest_facs], indent=2)

        # 4. Construct prompt with structural XML fencing
        template = (
            PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
            if PROMPT_TEMPLATE_PATH.exists()
            else ""
        )
        prompt = (
            template.replace("{sop_context}", sop_context_str)
            .replace("{facilities_json}", facs_json)
            .replace("{history_json}", "[]")
            .replace("{user_query}", input_data.query)
        )

        # 5. LLM structured execution with output safety verification & repair retry
        answer_text = SAFE_FALLBACK_TEXT
        if ctx.llm is not None:
            try:
                llm_res: CitizenAgentLLMOutput = await ctx.llm.structured(
                    prompt=prompt,
                    response_schema=CitizenAgentLLMOutput,
                    temperature=settings.LLM_TEMPERATURE_REASONING,
                )
                answer_candidate = llm_res.answer

                # Validate output safety filters
                safety_violations = check_output_safety(answer_candidate, allowed_urls)

                if safety_violations and ctx.max_repair_retries > 0:
                    log.warning("output_safety_filter_triggered", violations=safety_violations)
                    repair_prompt = (
                        f"{prompt}\n\n"
                        f"[REPAIR REQUIRED]: Your previous response contained safety violations:\n"
                        f"{chr(10).join(safety_violations)}\n"
                        f"Please regenerate without certainty words (e.g. guarantee/definitely), "
                        f"without unauthorized phone numbers (only 112, 1070, 1077, 108 allowed), "
                        f"and without external URLs."
                    )
                    repaired_res: CitizenAgentLLMOutput = await ctx.llm.structured(
                        prompt=repair_prompt,
                        response_schema=CitizenAgentLLMOutput,
                        temperature=0.0,
                    )
                    # Verify repaired candidate
                    repaired_violations = check_output_safety(repaired_res.answer, allowed_urls)
                    if not repaired_violations:
                        answer_candidate = repaired_res.answer
                    else:
                        log.warning("repair_retry_failed_using_safe_fallback")
                        answer_candidate = SAFE_FALLBACK_TEXT

                answer_text = answer_candidate
            except Exception as e:
                log.warning("llm_generation_failed_degrading_to_fallback", error=str(e))
                answer_text = SAFE_FALLBACK_TEXT

        # If urgent, ensure escalation guidance is stated in answer
        if is_escalated and "112" not in answer_text:
            answer_text = f"{answer_text} In this emergency, please call 112 or 1077 immediately."

        return CitizenQueryResponse(
            session_id=input_data.session_id or uuid.uuid4(),
            answer=answer_text,
            citations=citations_list,
            nearest_facilities=nearest_facs,
            escalated=is_escalated,
            escalation_reason=esc_reason,
            safety_flag=safety_flag,
            disclaimer=DISCLAIMER_TEXT,
        )


citizen_agent = CitizenAssistanceAgent()
