"""Queries the passes share."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.tenants.models import Document, DocumentRevision, Sheet


async def current_sheets(
    db: AsyncSession, project_id: uuid.UUID, *, kinds: tuple[str, ...] | None = None
) -> list[tuple[Sheet, Document]]:
    """Every sheet of a current, processed revision of the project, in document and page order;
    excluded pages and reprints are left out."""
    q = (
        select(Sheet, Document)
        .join(DocumentRevision, DocumentRevision.id == Sheet.revision_id)
        .join(Document, Document.id == DocumentRevision.document_id)
        .where(
            Document.project_id == project_id,
            Document.current_revision_id == DocumentRevision.id,
            DocumentRevision.processing_status.in_(("done", "partial")),
            Sheet.excluded.is_(False),
        )
        .order_by(Document.title, Sheet.page_no)
    )
    if kinds:
        q = q.where(Document.kind.in_(kinds))
    out = []
    for sheet, doc in await db.execute(q):
        if (sheet.hints or {}).get("duplicate_of"):
            continue
        out.append((sheet, doc))
    return out


def page_label(doc: Document, sheet: Sheet) -> str:
    return f"{doc.title} p.{sheet.page_no}"
