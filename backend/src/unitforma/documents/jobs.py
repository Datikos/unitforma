"""Worker-side processing of uploaded revisions (plan §12.3)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.core.db import tenant_session
from unitforma.core.ids import new_id
from unitforma.documents import assignments, cad_dxf, classify, levels, processing
from unitforma.documents import service as documents_service
from unitforma.mapping.jobs import propose_revision_diff
from unitforma.storage.service import get_storage
from unitforma.tenants.models import (
    Building,
    Document,
    DocumentRevision,
    Floor,
    GeometryModel,
    Sheet,
)

log = structlog.get_logger()


async def _fix_model_kind(db: AsyncSession, document_id: uuid.UUID, kind: str) -> None:
    """ADR-0008 amendment: an IFC or GLB upload gets its model kind from the sniffed MIME type;
    a kind set by a person stays."""
    doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one()
    if doc.kind_source != "manual" and (doc.kind, doc.kind_source) != (kind, "type"):
        doc.kind, doc.kind_source = kind, "type"
        log.info("documents.classified", document_id=str(doc.id), kind=kind, by="type")


async def _same_file_before(db: AsyncSession, rev: DocumentRevision) -> tuple[str, int] | None:
    """(document title, revision no) of an earlier processed revision in the same project with
    this revision's checksum (ADR-0030 Decision 2); ``None`` when the file is new."""
    if not rev.sha256:
        return None
    project_id = (
        await db.execute(select(Document.project_id).where(Document.id == rev.document_id))
    ).scalar_one()
    row = (
        await db.execute(
            select(Document.title, DocumentRevision.revision_no)
            .join(Document, Document.id == DocumentRevision.document_id)
            .where(
                Document.project_id == project_id,
                DocumentRevision.sha256 == rev.sha256,
                DocumentRevision.processing_status == "done",
                DocumentRevision.id != rev.id,
            )
            .order_by(DocumentRevision.created_at)
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def _model_from_checksum(db: AsyncSession, rev: DocumentRevision) -> bool:
    """Whether the document's building already has a ready current IFC model built from a
    revision with this checksum; then the heavy conversion would only repeat itself."""
    building_id = (
        await db.execute(select(Document.building_id).where(Document.id == rev.document_id))
    ).scalar_one()
    if building_id is None:
        return False
    return (
        await db.execute(
            select(GeometryModel.id)
            .join(DocumentRevision, DocumentRevision.id == GeometryModel.revision_id)
            .where(
                GeometryModel.building_id == building_id,
                GeometryModel.kind == "ifc",
                GeometryModel.is_current.is_(True),
                GeometryModel.status == "ready",
                DocumentRevision.sha256 == rev.sha256,
            )
            .limit(1)
        )
    ).first() is not None


async def process_revision(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> dict:
    """Inspect the uploaded object, create sheets, rasterise and extract every page.

    Runs inside the worker (``documents.ingest_revision``) or synchronously from tests. Each page
    is processed in its own transaction so a failure leaves earlier pages usable.
    """
    storage = get_storage()
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(select(DocumentRevision).where(DocumentRevision.id == revision_id))
        ).scalar_one_or_none()
        if rev is None or rev.processing_status == "pending":
            # the request that queued this has not committed yet (ADR-0038)
            from unitforma.jobs.visibility import NotYetCommitted

            raise NotYetCommitted(f"revision {revision_id} not committed yet")
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
        if fixed := classify.kind_from_type(None, info.mime):
            # the content says model: the kind is fixed by the type, whatever the name said
            await _fix_model_kind(db, rev.document_id, fixed)
        twin = await _same_file_before(db, rev)
        if twin is not None:
            rev.processing_note = f"Same file as {twin[0]} rev {twin[1]}"[:300]
        if info.mime == "application/x-step":
            # an IFC model has no pages: the heavy worker converts it (ADR-0006 Phase C)
            if twin is not None and await _model_from_checksum(db, rev):
                # ADR-0030 Decision 2: the building already shows this very file
                rev.processing_status = "done"
                rev.page_count = 0
                return {"ifc": True, "status": "done", "duplicate": True}
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
    if processed:
        # the setup solver applies the confident proposals when the project asks for it
        # (ADR-0025 Decision 3); a run that finds other revisions processing waits
        from unitforma.autopilot.queue import queue_run

        run_id = await queue_run(tenant_id, project_id, "document_processed")
        if run_id is not None:
            result["autopilot_run_id"] = str(run_id)
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


async def resuggest_floors(tenant_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    """Re-run the page → floor suggestions for every current revision of a project from the
    markers stored in ``sheets.hints`` (ADR-0010): floors accepted from the proposal, or entered
    by hand, arrive after processing, and the sheets would otherwise stay unassigned until a new
    revision. Confirmed assignments are never touched (``replace_suggestions``)."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        rows = await db.execute(
            select(Document, DocumentRevision)
            .join(DocumentRevision, DocumentRevision.id == Document.current_revision_id)
            .where(
                Document.project_id == project_id,
                DocumentRevision.processing_status.in_(("done", "partial")),
            )
        )
        targets = [
            (d.id, r.id, d.building_id, d.kind)
            for d, r in rows
            if d.building_id is not None or d.kind == "floor_plan"
        ]
        per_revision: dict[uuid.UUID, tuple] = {}
        for _doc_id, rev_id, building_id, _kind in targets:
            sheets = (await db.execute(select(Sheet).where(Sheet.revision_id == rev_id))).scalars()
            markers: dict[int, list[levels.Marker]] = {}
            page_hints: dict[int, dict] = {}
            page_lines: dict[int, int] = {}
            for sh in sheets:
                hints = dict(sh.hints or {})
                page_hints[sh.page_no] = hints
                page_lines[sh.page_no] = int((hints.get("vectors") or {}).get("lines") or 0)
                markers[sh.page_no] = [
                    levels.Marker.from_dict(m) for m in hints.get("level_markers") or []
                ]
            per_revision[rev_id] = (building_id, markers, page_hints, page_lines)
    done = 0
    for rev_id, (building_id, markers, page_hints, page_lines) in per_revision.items():
        if not any(markers.values()) and not any(
            h.get("floor_numbers") for h in page_hints.values()
        ):
            continue
        await _suggest_floors(
            tenant_id, rev_id, project_id, building_id, markers, page_hints, page_lines
        )
        done += 1
    log.info("documents.floors_resuggested", project_id=str(project_id), revisions=done)
    return {"revisions": done}


# --------------------------------------------------------------------------- stuck revisions
# A revision is filed as "queued" by the API or the permit import and processed by the
# ``documents.ingest_revision`` job, deferred after the row is committed. A worker killed between
# the two (a restart past Docker's stop grace, a crash) leaves the row "queued" with no job; a
# job killed while running leaves the row "processing" with a job stuck in "doing" on a worker
# that no longer sends heartbeats (ADR-0016 Decision 8). ``requeue_stuck`` heals both.
STUCK_AFTER = timedelta(minutes=15)
MAX_TRIES = 3  # ingestion runs per revision before it is marked failed
WORKER_DEAD_AFTER_S = 60.0  # no heartbeat for this long = the worker is gone (it beats every 10 s)
INGEST_TASK = "documents.ingest_revision"

_JOBS_OF_REVISION = text(
    "SELECT j.id, j.status,"
    " (w.last_heartbeat IS NOT NULL"
    "  AND w.last_heartbeat > now() - make_interval(secs => :dead_s)) AS alive,"
    " (SELECT count(*) FROM procrastinate_events e"
    "  WHERE e.job_id = j.id AND e.type = 'started') AS started"
    " FROM procrastinate_jobs j LEFT JOIN procrastinate_workers w ON w.id = j.worker_id"
    " WHERE j.task_name IN (:task, 'geometry.ingest_ifc') AND j.args->>'revision_id' = :rid"
)
_FAIL_JOBS = text("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = ANY(:ids)")


async def _heal_revision(db, rev: DocumentRevision) -> str:
    """One stuck revision: ``live`` (a job in ``todo``, or running on a worker with a fresh
    heartbeat, will finish it), ``requeued`` (status reset to queued, the caller defers a new
    job) or ``failed`` (MAX_TRIES runs were lost). Jobs left ``doing`` by a dead worker are
    closed as failed so they never count as running again."""
    rows = (
        await db.execute(
            _JOBS_OF_REVISION,
            {"dead_s": WORKER_DEAD_AFTER_S, "task": INGEST_TASK, "rid": str(rev.id)},
        )
    ).all()
    if any(r.status == "todo" or (r.status == "doing" and r.alive) for r in rows):
        return "live"
    stale = [r.id for r in rows if r.status == "doing"]
    if stale:
        await db.execute(_FAIL_JOBS, {"ids": stale})
    tries = int(sum(r.started for r in rows))
    if tries >= MAX_TRIES:
        rev.processing_status = "failed"
        rev.processing_error = f"worker lost {tries} times; upload the file again"
        return "failed"
    rev.processing_status = "queued"
    rev.processing_error = None
    return "requeued"


async def defer_ingest(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> bool:
    """Queue the ingestion of a committed revision; False (logged) when the queue is unavailable."""
    try:
        from unitforma.jobs.app import app as jobs

        await jobs.configure_task(name=INGEST_TASK, queue="docs").defer_async(
            tenant_id=str(tenant_id), revision_id=str(revision_id)
        )
        return True
    except Exception as e:  # noqa: BLE001 - the sweep queues it again
        log.warning("documents.enqueue_failed", revision_id=str(revision_id), error=str(e))
        return False


async def requeue_document_if_stuck(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str | None:
    """Heal a document's current revision left ``queued`` or ``processing`` with no live job.
    The permit import calls this for every file it finds "existing": the file was filed by an
    import whose worker died before it deferred the ingestion. None when nothing is stuck."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(
                select(DocumentRevision)
                .join(Document, Document.current_revision_id == DocumentRevision.id)
                .where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if rev is None or rev.processing_status not in ("queued", "processing"):
            return None
        outcome = await _heal_revision(db, rev)
        rev_id = rev.id
    if outcome == "live":
        return None  # waiting its turn, or running: not stuck
    if outcome == "requeued" and not await defer_ingest(tenant_id, rev_id):
        outcome = "enqueue_failed"
    log.info("documents.revision_healed", revision_id=str(rev_id), outcome=outcome)
    return outcome


REPROCESSABLE = ("queued", "processing", "failed", "done", "partial")


async def reprocess_revision(tenant_id: uuid.UUID, revision_id: uuid.UUID) -> str:
    """Process again (ADR-0016 #F5, ADR-0031 Decision 6): the manual escape hatch next to the
    sweep, without its 15-minute wait or its MAX_TRIES stop, and the way a processed revision
    takes a newer extractor. Sheets, floor assignments, calibrations and boundaries stay
    (``process_revision`` updates sheets in place). Returns ``queued``, ``running`` (a job waits
    or runs on a live worker: nothing to do) or ``enqueue_failed``. The status is committed
    before the job is deferred, so the worker never reads the old one."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        rev = (
            await db.execute(
                select(DocumentRevision).where(DocumentRevision.id == revision_id).with_for_update()
            )
        ).scalar_one()
        rows = (
            await db.execute(
                _JOBS_OF_REVISION,
                {"dead_s": WORKER_DEAD_AFTER_S, "task": INGEST_TASK, "rid": str(rev.id)},
            )
        ).all()
        if any(r.status == "todo" or (r.status == "doing" and r.alive) for r in rows):
            return "running"
        stale = [r.id for r in rows if r.status == "doing"]
        if stale:
            await db.execute(_FAIL_JOBS, {"ids": stale})
        rev.processing_status = "queued"
        rev.processing_error = None
    outcome = "queued" if await defer_ingest(tenant_id, revision_id) else "enqueue_failed"
    log.info("documents.reprocess", revision_id=str(revision_id), outcome=outcome)
    return outcome


async def requeue_stuck(now: datetime | None = None) -> dict:
    """Periodic sweep (``documents.requeue_stuck``, every 10 minutes): every revision ``queued``
    or ``processing`` for longer than STUCK_AFTER whose ingestion is neither waiting nor running
    on a live worker is queued again, up to MAX_TRIES runs, then marked failed."""
    cutoff = (now or datetime.now(UTC)) - STUCK_AFTER
    out = {"requeued": 0, "failed": 0, "live": 0, "enqueue_failed": 0}
    to_defer: list[tuple[uuid.UUID, uuid.UUID]] = []
    async with tenant_session(None, scope="platform") as db:
        revs = (
            (
                await db.execute(
                    select(DocumentRevision)
                    .where(
                        DocumentRevision.processing_status.in_(("queued", "processing")),
                        DocumentRevision.updated_at < cutoff,
                    )
                    .order_by(DocumentRevision.created_at)
                )
            )
            .scalars()
            .all()
        )
        for rev in revs:
            outcome = await _heal_revision(db, rev)
            out[outcome] += 1
            if outcome == "requeued":
                to_defer.append((rev.tenant_id, rev.id))
            else:
                log.info("documents.revision_healed", revision_id=str(rev.id), outcome=outcome)
    for tenant_id, rev_id in to_defer:
        if not await defer_ingest(tenant_id, rev_id):
            out["requeued"] -= 1
            out["enqueue_failed"] += 1
    if sum(out.values()):
        log.info("documents.stuck_swept", **out)
    return out
