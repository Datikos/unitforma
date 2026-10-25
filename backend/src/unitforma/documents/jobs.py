"""Worker-side processing of uploaded revisions (plan §12.3)."""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.core.ids import new_id
from unitforma.documents import assignments, cad_dxf, levels, processing
from unitforma.documents import service as documents_service
from unitforma.mapping.jobs import propose_revision_diff
from unitforma.storage.service import get_storage
from unitforma.tenants.models import Building, Document, DocumentRevision, Floor, Sheet

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
        cad: cad_dxf.DxfDrawing | None = None
        try:
            info = processing.inspect(data, rev.mime)
            if info.mime == cad_dxf.MIME:
                cad = cad_dxf.DxfDrawing(data)  # parsed once for every layout (ADR-0006)
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
        if info.mime == "application/x-step":
            # an IFC model has no pages: the heavy worker converts it (ADR-0006 Phase C)
            rev.processing_status = "queued"
            try:
                from unitforma.jobs.app import app as jobs

                await jobs.configure_task(
                    name="geometry.ingest_ifc", queue="geometry-heavy"
                ).defer_async(tenant_id=str(tenant_id), revision_id=str(revision_id))
            except Exception as e:  # noqa: BLE001 - visible to the reviewer, re-run by hand
                rev.processing_status = "failed"
                rev.processing_error = f"could not queue IFC ingestion: {e}"[:2000]
            return {"ifc": True, "status": rev.processing_status}
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
        mime, page_count, building_id, project_id, doc_kind, document_id = (
            info.mime,
            info.page_count,
            doc.building_id,
            doc.project_id,
            doc.kind,
            doc.id,
        )

    processed = 0
    markers: dict[int, list[levels.Marker]] = {}
    page_hints: dict[int, dict] = {}
    page_lines: dict[int, int] = {}
    for page_no in range(1, page_count + 1):
        try:
            if cad is not None:
                png, thumb, w, h = cad.rasterize(page_no)
                extract = cad.extract(page_no)
            else:
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
            # a DXF with units arrives calibrated; a reviewer's own calibration is never replaced
            if cad is not None and sheet.calibration_status == "none":
                cal = cad.calibration(page_no, w, h)
                if cal:
                    sheet.calibration, sheet.calibration_status = cal, "calibrated"
        markers[page_no] = levels.markers_from_words(extract.get("words") or [])
        page_hints[page_no] = extract["hints"]
        page_lines[page_no] = int((extract.get("vectors") or {}).get("lines") or 0)
        processed += 1

    # ADR-0008: the pages may say what the file is; a kind set by a person is never replaced
    if processed:
        async with tenant_session(tenant_id, scope="tenant") as db:
            doc = (
                await db.execute(select(Document).where(Document.id == document_id))
            ).scalar_one()
            if documents_service.classify_from_pages(
                doc,
                [
                    {**page_hints[n], "vector_lines": page_lines.get(n, 0)}
                    for n in sorted(page_hints)
                ],
                mime,
            ):
                log.info(
                    "documents.classified", document_id=str(doc.id), kind=doc.kind, by="content"
                )
            doc_kind = doc.kind
    # a building's documents, or floor plans filed at project level (a multi-block set);
    # site plans, renders and schedules show no floor
    if processed and (building_id or doc_kind == "floor_plan"):
        await _suggest_floors(
            tenant_id, revision_id, project_id, building_id, markers, page_hints, page_lines
        )

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


async def _suggest_floors(
    tenant_id: uuid.UUID,
    revision_id: uuid.UUID,
    project_id: uuid.UUID,
    building_id: uuid.UUID | None,
    markers: dict[int, list[levels.Marker]],
    page_hints: dict[int, dict],
    page_lines: dict[int, int],
) -> None:
    """Page → floor suggestions for the whole revision (plan §13.2 "Page → floor").

    Level markers that repeat in the title block are dropped across pages first; each page's
    remaining markers suggest the floors with matching elevations, each with the part of the
    sheet nearest its marker. Floor words ("Level 3") and a lone ±0.00 keep working on
    projects without elevations. Confirmed assignments are never replaced.
    """
    kept = levels.drop_repeated(markers)
    duplicates = duplicate_pages(page_hints, kept)
    async with tenant_session(tenant_id, scope="tenant") as db:
        floors = [
            levels.FloorRef(
                id=f.id,
                building_id=f.building_id,
                level=f.level,
                elevation_m=float(f.elevation_m) if f.elevation_m is not None else None,
            )
            for f in (
                await db.execute(
                    select(Floor)
                    .join(Building, Building.id == Floor.building_id)
                    .where(Building.project_id == project_id)
                )
            ).scalars()
        ]
        sheets = {
            s.page_no: s
            for s in (
                await db.execute(select(Sheet).where(Sheet.revision_id == revision_id))
            ).scalars()
        }
        for page_no, page_markers in kept.items():
            sheet = sheets.get(page_no)
            if sheet is None:
                continue
            hints = dict(page_hints.get(page_no) or {})
            hints["level_markers"] = [m.as_dict() for m in page_markers]
            if page_no in duplicates:
                hints["duplicate_of"] = duplicates[page_no]
            sheet.hints = hints
            if sheet.excluded or page_no in duplicates:
                continue  # a reprint gets its floors from the reviewer, if they map it at all
            suggestions: list[dict] = []
            stacked = levels.is_stacked(page_markers)
            if page_markers and not stacked:
                matched = levels.match_floors(page_markers, floors, building_id)
                aspect = (
                    float(sheet.height_pt) / float(sheet.width_pt)
                    if sheet.width_pt and sheet.height_pt
                    else 1.0
                )
                suggestions = levels.floor_regions(matched, aspect=aspect)
            # projects without elevations: floor words, or a lone ±0.00 (entrance level);
            # never on text-only sheets (code-compliance tables mention floors too)
            if (
                not suggestions
                and building_id
                and page_lines.get(page_no, 0) > 0
                and not stacked
                and (
                    hints.get("floor_numbers") or not any(f.elevation_m is not None for f in floors)
                )
            ):
                level = processing.suggest_floor_level(
                    {**hints, "levels": [m.text for m in page_markers]}
                )
                own = [f for f in floors if f.building_id == building_id and f.level == level]
                if level is not None and own:
                    suggestions = [{"floor_id": own[0].id, "marker": None, "region": None}]
            if suggestions:
                await assignments.replace_suggestions(db, sheet, suggestions, "level_marker")


def duplicate_pages(
    page_hints: dict[int, dict],
    markers: dict[int, list[levels.Marker]] | None = None,
    *,
    min_labels: int = 3,
) -> dict[int, int]:
    """Pages that reprint an earlier page's units (fire-safety, egress or accessibility sets).

    Two pages show the same plan when ≥ 80 % of the smaller unit-label set (≥ ``min_labels``
    keys) is on the other page — a reprint may lose labels drawn as outlines — and their
    level markers do not contradict: different floors of a building that numbers units per
    floor ("Apt 1–8" on every floor) carry different levels. The later page points at the
    first. Reprints keep their sheet but get no floor suggestions; the documents page offers
    to exclude them.
    """
    keys: dict[int, set[str]] = {}
    for page_no in sorted(page_hints):
        by_kind = (page_hints[page_no] or {}).get("unit_labels") or {}
        ks = {f"{k}:{v}" for k, vs in by_kind.items() if k != "numbered" for v in vs}
        if len(ks) >= min_labels:
            keys[page_no] = ks
    values = {p: {round(m.value, 2) for m in (markers or {}).get(p, [])} for p in keys}
    out: dict[int, int] = {}
    pages = sorted(keys)
    for i, p in enumerate(pages):
        for q in pages[:i]:
            if q in out:
                continue
            small = min(len(keys[p]), len(keys[q]))
            if len(keys[p] & keys[q]) / small < 0.8:
                continue
            if values[p] and values[q] and not values[p] & values[q]:
                continue  # same unit numbers, different levels: another floor
            out[p] = q
            break
    return out
