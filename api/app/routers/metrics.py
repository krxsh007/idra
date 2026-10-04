from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import require_responder
from app.db.models.users import User
from app.eval.harness import evaluation_harness

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/eval")
async def get_eval_metrics(
    refresh: bool = Query(default=False, description="Re-run evaluation harness if True"),
    _current_user: User = Depends(require_responder),
) -> dict[str, Any]:
    """Return the latest evaluation harness metrics results (RESPONDER+)."""
    if not refresh:
        cached = evaluation_harness.load_latest()
        if cached is not None:
            return cached

    return await evaluation_harness.run_all(write_disk=True)
