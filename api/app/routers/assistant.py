from __future__ import annotations

import hashlib
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from geoalchemy2.functions import ST_GeomFromText
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentFailure, RunContext
from app.agents.citizen_assistance import (
    DISCLAIMER_TEXT,
    SAFE_FALLBACK_TEXT,
    citizen_agent,
)
from app.core.config import settings
from app.core.ratelimit import limit_public_assistant
from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.enums import AgentName, Provenance, ReportSource
from app.db.models.events import IncidentReport
from app.db.session import get_db
from app.gis.validation import point_to_wkt
from app.llm.client import get_llm_client
from app.schemas.assistant import CitizenQueryRequest, CitizenQueryResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Citizen Assistant"])


@router.post(
    "/assistant/query",
    response_model=CitizenQueryResponse,
    dependencies=[Depends(limit_public_assistant)],
    summary="Public conversational assistant for disaster safety queries",
)
async def query_assistant(
    req: CitizenQueryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CitizenQueryResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    client_hash = hashlib.sha256(client_ip.encode()).hexdigest()

    # 1. Manage Chat Session
    session: ChatSession | None = None
    if req.session_id is not None:
        stmt = select(ChatSession).where(ChatSession.id == req.session_id)
        res = await db.execute(stmt)
        session = res.scalar_one_or_none()

    if session is None:
        session = ChatSession(
            id=req.session_id or uuid.uuid4(),
            event_id=req.event_id,
            client_hash=client_hash,
        )
        db.add(session)
        await db.flush()

    req.session_id = session.id

    # 2. Record User Message
    user_msg = ChatMessage(
        session_id=session.id,
        role="USER",
        content=req.query,
        escalated=False,
    )
    db.add(user_msg)
    await db.flush()

    # 3. Execute Citizen Assistance Agent
    start_time = time.perf_counter()
    llm = get_llm_client()
    ctx = RunContext(
        event_id=req.event_id,
        agent_name=AgentName.CITIZEN_ASSISTANCE,
        db=db,
        llm=llm,
        timeout_s=float(settings.AGENT_TIMEOUT_CITIZEN_S),
    )

    result = await citizen_agent.run(ctx, req)
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    if isinstance(result, AgentFailure):
        logger.warning(
            "citizen_agent_failure_fallback",
            code=result.code,
            message=result.message,
        )
        response = CitizenQueryResponse(
            session_id=session.id,
            answer=SAFE_FALLBACK_TEXT,
            citations=[],
            nearest_facilities=[],
            escalated=False,
            escalation_reason=None,
            safety_flag="NONE",
            disclaimer=DISCLAIMER_TEXT,
        )
    else:
        response = result

    # 4. Handle Escalation to Incident Reports
    if response.escalated:
        report_lon = req.location.lon if req.location else 80.250
        report_lat = req.location.lat if req.location else 13.050
        wkt = point_to_wkt(report_lon, report_lat)
        geom = ST_GeomFromText(wkt, 4326)

        escalated_report = IncidentReport(
            event_id=req.event_id,
            source=ReportSource.CITIZEN,
            body=req.query,
            location=geom,
            casualties_reported=(response.safety_flag == "LIFE_THREATENING"),
            data_provenance=Provenance.REAL,
        )
        db.add(escalated_report)
        logger.info(
            "citizen_report_escalated",
            session_id=str(session.id),
            safety_flag=response.safety_flag,
        )

    # 5. Record Assistant Message Turn
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="ASSISTANT",
        content=response.answer,
        citations=[c.model_dump(mode="json") for c in response.citations],
        escalated=response.escalated,
        latency_ms=latency_ms,
    )
    db.add(assistant_msg)
    await db.commit()

    return response
