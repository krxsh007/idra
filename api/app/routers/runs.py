from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException, ErrorCode
from app.core.security import require_responder
from app.db.models.base import utc_now
from app.db.models.enums import AgentName, RunStatus
from app.db.models.runs import AgentRun
from app.db.models.users import User
from app.db.session import get_db
from app.llm.client import get_llm_client
from app.orchestration.engine import orchestration_engine
from app.schemas.runs import (
    AgentOutputResponse,
    RunDetailResponse,
    RunListResponse,
    TriggerRunRequest,
)

router = APIRouter(tags=["Orchestration Runs"])


async def _execute_event_run(
    event_id: uuid.UUID,
    force: bool,
    db: AsyncSession,
    current_user: User,
) -> Any:
    if not force:
        active_stmt = select(AgentRun).where(
            AgentRun.event_id == event_id,
            AgentRun.status == RunStatus.RUNNING,
        )
        active_res = await db.execute(active_stmt)
        existing_active = active_res.scalar_one_or_none()
        if isinstance(existing_active, AgentRun):
            raise AppException(
                code=ErrorCode.CONFLICT,
                message=f"An active run is already in progress for event {event_id}",
                status_code=status.HTTP_409_CONFLICT,
            )

    llm = get_llm_client()
    try:
        run_record = await orchestration_engine.run_pipeline(
            event_id=event_id,
            triggered_by=current_user.id,
            db=db,
            llm=llm,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    # Re-fetch with loaded outputs
    stmt = (
        select(AgentRun).options(selectinload(AgentRun.outputs)).where(AgentRun.id == run_record.id)
    )
    res = await db.execute(stmt)
    full_run = res.scalar_one()
    return full_run


@router.post(
    "/runs",
    response_model=RunDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger multi-agent orchestration pipeline (JSON payload)",
)
async def trigger_run(
    body: TriggerRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    return await _execute_event_run(
        event_id=body.event_id,
        force=body.force,
        db=db,
        current_user=current_user,
    )


@router.post(
    "/events/{event_id}/runs",
    response_model=RunDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger multi-agent orchestration pipeline for an event",
)
async def trigger_event_run(
    event_id: uuid.UUID,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_responder),
) -> Any:
    return await _execute_event_run(
        event_id=event_id,
        force=force,
        db=db,
        current_user=current_user,
    )


def _with_live_outputs(run: AgentRun) -> RunDetailResponse:
    """Serialize a run; while it is still running, include agents that have already finished.

    Outputs are persisted when the whole pipeline completes, so without this an in-progress run
    shows no results until the very end.
    """
    detail = RunDetailResponse.model_validate(run)
    if run.status != RunStatus.RUNNING or detail.outputs:
        return detail
    live = [
        AgentOutputResponse(
            id=uuid.uuid4(),
            agent=AgentName(rec["agent"]),
            status=rec["status"],
            payload=rec.get("payload"),
            latency_ms=rec.get("latency_ms"),
            error_code=rec.get("error_code"),
            error_message=rec.get("error_message"),
            created_at=utc_now(),
        )
        for rec in orchestration_engine.get_live_outputs(str(run.id))
    ]
    return detail.model_copy(update={"outputs": live})


@router.get(
    "/events/{event_id}/runs",
    response_model=RunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all orchestration runs for a disaster event",
)
async def list_event_runs(
    event_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    count_stmt = select(func.count(AgentRun.id)).where(AgentRun.event_id == event_id)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AgentRun)
        .options(selectinload(AgentRun.outputs))
        .where(AgentRun.event_id == event_id)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = (await db.execute(stmt)).scalars().all()

    return {
        "items": [_with_live_outputs(run) for run in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/runs/{run_id}",
    response_model=RunDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed results and agent outputs for a specific run",
)
async def get_run_detail(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(AgentRun).options(selectinload(AgentRun.outputs)).where(AgentRun.id == run_id)
    res = await db.execute(stmt)
    run_record = res.scalar_one_or_none()
    if not run_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )
    return _with_live_outputs(run_record)


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream real-time Server-Sent Events (SSE) progress for a run",
)
async def stream_run_progress(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    run_id_str = str(run_id)
    in_mem_events = orchestration_engine.get_run_events(run_id_str)

    if not in_mem_events:
        stmt = select(AgentRun).options(selectinload(AgentRun.outputs)).where(AgentRun.id == run_id)
        res = await db.execute(stmt)
        run_record = res.scalar_one_or_none()
        if not run_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent run {run_id} not found",
            )
        events_to_stream: list[dict[str, Any]] = [
            {"event": "run_started", "run_id": run_id_str, "status": "RUNNING"}
        ]
        for out in getattr(run_record, "outputs", []):
            events_to_stream.append(
                {
                    "event": "agent_completed",
                    "run_id": run_id_str,
                    "agent": out.agent.value if hasattr(out.agent, "value") else str(out.agent),
                    "status": out.status.value if hasattr(out.status, "value") else str(out.status),
                    "latency_ms": out.latency_ms,
                    "error_code": out.error_code,
                }
            )
        events_to_stream.append(
            {
                "event": "run_completed",
                "run_id": run_id_str,
                "status": (
                    run_record.status.value
                    if hasattr(run_record.status, "value")
                    else str(run_record.status)
                ),
                "total_latency_ms": run_record.total_latency_ms,
            }
        )
    else:
        events_to_stream = in_mem_events

    async def event_generator() -> AsyncGenerator[str, None]:
        for ev in events_to_stream:
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
