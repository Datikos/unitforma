"""Worker-side processing of uploaded revisions (plan §12.3)."""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.core.ids import new_id
from unitforma.documents import processing
from unitforma.mapping.jobs import propose_revision_diff
from unitforma.storage.service import get_storage
from unitforma.tenants.models import Document, DocumentRevision, Floor, Sheet

log = structlog.get_logger()


async def process_revision(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> dict:
    """Inspect the uploaded object, create sheets, rasterise and extract every page.

    Runs inside the worker (``documents.ingest_revision``) or synchronously from tests. Each page
    is processed in its own transaction so a failure leaves earlier pages usable.
    """
    storage = get_storage()
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one()
        if rev.processing_status not in ("queued", "failed"):
            return {"skipped": rev.processing_status}
        rev.processing_status = "processing"
        rev.processing_error = None
        data = storage.get_bytes(rev.object_key)
        try:
            info = processing.inspect(data, rev.mime)
        except Exception as e:  # noqa: BLE001
            rev.processing_status = "failed"
            rev.processing_error = f"inspect: {e}"[:2000]
            return {"error": rev.processing_error}
        rev.sha256, rev.mime, rev.page_count, rev.byte_size = (
            info.sha256,
            info.mime,
            info.page_count,
            len(data),
        )
        existing = {
            s.page_no: s
            for s in (await db.execute(select(Sheet).where(Sheet.revision_id == rev.id))).scalars()
        }
        for p in info.pages:
            if p.page_no not in existing:
                db.add(
                    Sheet(
                        id=new_id(),
                        tenant_id=tenant_id,
                        revision_id=rev.id,
                        page_no=p.page_no,
                        width_pt=p.width_pt,
                        height_pt=p.height_pt,
                    )
                )
        doc = (
            await db.execute(select(Document).where(Document.id == rev.document_id))
        ).scalar_one()
        base_key = rev.object_key.rsplit("/", 1)[0]
        mime, page_count, building_id, project_id = (
            info.mime,
            info.page_count,
            doc.building_id,
            doc.project_id,
        )

    processed = 0
    for page_no in range(1, page_count + 1):
        try:
            png, thumb, w, h = processing.rasterize_page(data, mime, page_no)
            extract = processing.extract_page(data, mime, page_no)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "documents.page_failed", revision_id=str(revision_id), page=page_no, error=str(e)
            )
            continue
        raster_key = f"{base_key}/p{page_no:03d}.png"
        thumb_key = f"{base_key}/p{page_no:03d}.thumb.png"
        extract_key = f"{base_key}/p{page_no:03d}.extract.json"
        storage.put_bytes(raster_key, png, "image/png")
        storage.put_bytes(thumb_key, thumb, "image/png")
        storage.put_bytes(extract_key, json.dumps(extract).encode(), "application/json")
        async with tenant_session(tenant_id, scope="tenant") as db:
            sheet = (
                await db.execute(
                    select(Sheet).where(Sheet.revision_id == revision_id, Sheet.page_no == page_no)
                )
            ).scalar_one()
            sheet.raster_key, sheet.thumbnail_key, sheet.extract_key = (
                raster_key,
                thumb_key,
                extract_key,
            )
            sheet.raster_width, sheet.raster_height = w, h
            sheet.hints = extract["hints"]
            level = processing.suggest_floor_level(extract["hints"])
            if level is not None and building_id:
                fl = (
                    await db.execute(
                        select(Floor.id).where(
                            Floor.building_id == building_id, Floor.level == level
                        )
                    )
                ).first()
                if fl:
                    sheet.suggested_floor_id = fl[0]
                    if sheet.assignment_status == "unassigned":
                        sheet.assignment_status = "suggested"
        processed += 1

    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one()
        rev.processing_status = (
            "done" if processed == page_count else ("failed" if processed == 0 else "partial")
        )
        if rev.processing_status != "done":
            rev.processing_error = f"{processed}/{page_count} pages processed"
        supersedes = rev.supersedes_revision_id
    log.info(
        "documents.processed",
        revision_id=str(revision_id),
        pages=processed,
        of=page_count,
        project_id=str(project_id),
    )
    result: dict = {"pages": processed, "page_count": page_count}
    if processed and supersedes is not None:
        # a new revision of a mapped document → diff proposal for the reviewer (plan §13.3)
        try:
            result["diff"] = await propose_revision_diff(tenant_id, revision_id)
        except Exception as e:  # noqa: BLE001 - processing succeeded; the diff can be re-run
            log.warning("mapping.diff_failed", revision_id=str(revision_id), error=str(e))
            result["diff"] = {"error": str(e)[:500]}
    return result
