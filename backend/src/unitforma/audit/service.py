"""Append-only audit log written in the same transaction as the change (plan §5.3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.ids import new_id
from unitforma.tenants.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    row = AuditLog(
        id=new_id(),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        request_id=request_id,
    )
    session.add(row)
    return row
