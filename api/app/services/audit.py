import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.db.models.audit import AuditLog


async def log_mutation(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    actor_id: uuid.UUID | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an immutable audit log entry for a mutation."""
    req_id = request_id_ctx.get() or None
    audit_entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_state=before_state,
        after_state=after_state,
        request_id=req_id,
    )
    db.add(audit_entry)
    return audit_entry
