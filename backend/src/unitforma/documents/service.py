"""Documents, revisions and sheets (plan §5.3, §13)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.storage.service import get_storage, object_key, safe_filename
from unitforma.tenants.models import Building, Document, DocumentRevision, Sheet

ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "model/gltf-binary": ".glb",
    "application/x-step": ".ifc",
    "application/octet-stream": "",
}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


async def create_document(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    data: dict[str, Any],
    actor: tuple[uuid.UUID, str],
) -> Document:
    if data.get("building_id"):
        b = (
            await db.execute(
                select(Building).where(
                    Building.id == data["building_id"], Building.project_id == project_id
                )
            )
        ).scalar_one_or_none()
        if b is None:
            raise ProblemError(422, "Building does not belong to this project")
    doc = Document(
        id=new_id(),
        tenant_id=tenant_id,
        project_id=project_id,
        building_id=data.get("building_id"),
        kind=data["kind"],
        title=data["title"],
        visibility=data.get("visibility", "internal"),
        source=data.get("source") or {},
    )
    db.add(doc)
    await db.flush()
    await write_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="document",
        entity_id=doc.id,
        action="create",
        after={"kind": doc.kind, "title": doc.title},
    )
    return doc


async def get_document(db: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    d = (
        await db.execute(
            select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
        )
    ).scalar_one_or_none()
    if d is None:
        raise ProblemError(404, "Document not found")
    return d


async def create_upload_intent(
    db: AsyncSession,
    doc: Document,
    *,
    file_name: str,
    content_type: str,
    byte_size: int,
    uploaded_by: uuid.UUID,
    source_note: str | None,
) -> tuple[DocumentRevision, str]:
    """Reserve the next revision and return a presigned PUT URL. The revision stays ``pending``
    until ``complete_upload`` confirms the object exists."""
    if content_type not in ALLOWED_MIME:
        raise ProblemError(415, "Unsupported file type", content_type)
    if byte_size <= 0 or byte_size > MAX_UPLOAD_BYTES:
        raise ProblemError(413, "File too large")
    next_no = (
        await db.execute(
            select(func.coalesce(func.max(DocumentRevision.revision_no), 0) + 1).where(
                DocumentRevision.document_id == doc.id
            )
        )
    ).scalar_one()
    rev_id = new_id()
    key = object_key(
        doc.tenant_id,
        doc.project_id,
        "documents",
        str(doc.id),
        f"r{next_no}-{rev_id.hex[:8]}",
        safe_filename(file_name),
    )
    rev = DocumentRevision(
        id=rev_id,
        tenant_id=doc.tenant_id,
        document_id=doc.id,
        revision_no=next_no,
        object_key=key,
        file_name=safe_filename(file_name),
        mime=content_type,
        byte_size=byte_size,
        uploaded_by=uploaded_by,
        source_note=source_note,
        processing_status="pending",
        supersedes_revision_id=doc.current_revision_id,
    )
    db.add(rev)
    await db.flush()
    return rev, get_storage().presign_put(key, content_type)


async def get_revision(
    db: AsyncSession, tenant_id: uuid.UUID, revision_id: uuid.UUID
) -> DocumentRevision:
    r = (
        await db.execute(
            select(DocumentRevision).where(
                DocumentRevision.tenant_id == tenant_id, DocumentRevision.id == revision_id
            )
        )
    ).scalar_one_or_none()
    if r is None:
        raise ProblemError(404, "Revision not found")
    return r


async def complete_upload(
    db: AsyncSession, rev: DocumentRevision, actor: tuple[uuid.UUID, str]
) -> DocumentRevision:
    if rev.processing_status != "pending":
        return rev
    info = get_storage().head(rev.object_key)
    if info is None:
        raise ProblemError(
            409, "Upload not found in storage", "Upload the file to the presigned URL first"
        )
    rev.byte_size = info.size
    rev.processing_status = "queued"
    doc = await get_document(db, rev.tenant_id, rev.document_id)
    doc.current_revision_id = rev.id
    await write_audit(
        db,
        tenant_id=rev.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="document_revision",
        entity_id=rev.id,
        action="upload",
        after={
            "document_id": str(doc.id),
            "revision_no": rev.revision_no,
            "file_name": rev.file_name,
            "bytes": info.size,
        },
    )
    return rev


async def list_documents(
    db: AsyncSession, project_id: uuid.UUID
) -> list[tuple[Document, DocumentRevision | None]]:
    rows = await db.execute(
        select(Document, DocumentRevision)
        .outerjoin(DocumentRevision, DocumentRevision.id == Document.current_revision_id)
        .where(Document.project_id == project_id)
        .order_by(Document.kind, Document.title)
    )
    return [(d, r) for d, r in rows]


async def list_revisions(db: AsyncSession, document_id: uuid.UUID) -> list[DocumentRevision]:
    rows = await db.execute(
        select(DocumentRevision)
        .where(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.revision_no.desc())
    )
    return list(rows.scalars())


async def list_sheets(db: AsyncSession, revision_id: uuid.UUID) -> list[Sheet]:
    rows = await db.execute(
        select(Sheet).where(Sheet.revision_id == revision_id).order_by(Sheet.page_no)
    )
    return list(rows.scalars())


async def get_sheet(db: AsyncSession, tenant_id: uuid.UUID, sheet_id: uuid.UUID) -> Sheet:
    s = (
        await db.execute(select(Sheet).where(Sheet.tenant_id == tenant_id, Sheet.id == sheet_id))
    ).scalar_one_or_none()
    if s is None:
        raise ProblemError(404, "Sheet not found")
    return s


async def sheet_project_id(db: AsyncSession, sheet: Sheet) -> uuid.UUID:
    return (
        await db.execute(
            select(Document.project_id)
            .join(DocumentRevision, DocumentRevision.document_id == Document.id)
            .where(DocumentRevision.id == sheet.revision_id)
        )
    ).scalar_one()


async def assign_floor(
    db: AsyncSession,
    sheet: Sheet,
    floor_id: uuid.UUID | None,
    version: int,
    actor: tuple[uuid.UUID, str],
) -> Sheet:
    """Single-floor assignment (the common case): replaces the sheet's floors with one, or none."""
    from unitforma.documents import assignments

    items = [{"floor_id": floor_id, "region": None}] if floor_id is not None else []
    await assignments.set_floors(db, sheet, items, version, actor)
    return sheet


def signed_urls(sheet: Sheet) -> dict[str, str | None]:
    st = get_storage()
    return {
        "raster_url": st.presign_get(sheet.raster_key) if sheet.raster_key else None,
        "thumbnail_url": st.presign_get(sheet.thumbnail_key) if sheet.thumbnail_key else None,
        "extract_url": st.presign_get(sheet.extract_key) if sheet.extract_key else None,
    }
