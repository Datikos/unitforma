"""Worker entry points for the mapping module (plan §12.3 ``mapping.propose_revision_diff``)."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.mapping import service
from unitforma.tenants.models import DocumentRevision

log = structlog.get_logger()


async def propose_revision_diff(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> dict:
    """Build (or rebuild) the diff proposal for a processed revision."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one()
        if rev.processing_status not in ("done", "partial"):
            return {"skipped": rev.processing_status}
        proposal = await service.build_proposal(db, tenant_id, rev, None)
        if proposal is None:
            return {"proposal": None}
        return {"proposal": str(proposal.id), "summary": proposal.summary}
