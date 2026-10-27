"""Gallery pass (ADR-0025 Decision 5 "gallery"): processed render documents still internal go
public, so their pages form the portal gallery (ADR-0016 Decision 1)."""

from __future__ import annotations

from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.documents import service as documents
from unitforma.tenants.models import Document, DocumentRevision

STEP = "gallery"


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        rows = await db.execute(
            select(Document)
            .join(DocumentRevision, DocumentRevision.id == Document.current_revision_id)
            .where(
                Document.project_id == ctx.project_id,
                Document.kind == "render",
                Document.visibility == "internal",
                DocumentRevision.processing_status.in_(("done", "partial")),
            )
            .order_by(Document.title)
        )
        titles = []
        ids = []
        done_before = ctx.seen(STEP)
        for doc in rows.scalars():
            if str(doc.id) in done_before:
                continue  # a person set it back to internal: theirs
            await documents.update_document(db, doc, {"visibility": "public"}, ctx.actor)
            titles.append(doc.title)
            ids.append(doc.id)
        if titles:
            ctx.decide(
                STEP,
                "accepted",
                f"{len(titles)} render document(s) public",
                "Their pages form the portal gallery with the next publication: "
                + ", ".join(titles[:6])
                + (" …" if len(titles) > 6 else ""),
                confidence=rules.GALLERY_CONFIDENCE,
                entity_ids=ids,
            )
