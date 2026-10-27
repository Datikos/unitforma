"""Project bootstrap from a building permit (ADR-0007 Decisions 4 to 7).

``preview`` fetches and shows; ``start_import`` creates the project, one building and the import
row; the worker body ``import_attachments`` pulls the current drawings through the ordinary
upload path so ingest, sheets and floor suggestions are the same as for a manual upload.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.documents import jobs as documents_jobs
from unitforma.documents import service as documents
from unitforma.projects import service as projects
from unitforma.regulatory import tasge
from unitforma.storage.service import get_storage
from unitforma.tenants.models import Document, Project, RegulatoryImport

log = structlog.get_logger()

WORKER_ROLE = "system"


class Fetcher(Protocol):
    async def fetch_record(self, doc_id: int) -> dict[str, Any]: ...
    async def download(self, url: str) -> bytes: ...


_fetcher: Fetcher | None = None


def get_fetcher() -> Fetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = tasge.TasgeClient()
    return _fetcher


def set_fetcher(f: Fetcher | None) -> None:
    """Tests swap the registry client for a fake."""
    global _fetcher
    _fetcher = f


# --------------------------------------------------------------------------- preview
async def fetch_normalised(reference: str) -> dict[str, Any]:
    doc_id = tasge.extract_document_id(reference)
    rec = await get_fetcher().fetch_record(doc_id)
    return tasge.normalise(rec)


def preview_of(record: dict[str, Any]) -> dict[str, Any]:
    attachments = tasge.classify_attachments(record)
    return {
        "source": record["source"],
        "permit": record["permit"],
        "nomenclature": record.get("nomenclature") or {},
        "class_calculator": record.get("class_calculator") or [],
        "parcels": record.get("parcels") or [],
        "technical_indicators": record.get("technical_indicators") or [],
        "heights": tasge.heights(record),
        "suggestions": {
            "name": tasge.suggest_name(record),
            "slug": tasge.suggest_slug(record),
            "building_code": tasge.suggest_building_code(record),
        },
        "attachments": attachments,
        "counts": {
            "import": sum(1 for a in attachments if not a["skip_reason"]),
            "skip": sum(1 for a in attachments if a["skip_reason"]),
        },
    }


async def preview(reference: str) -> dict[str, Any]:
    return preview_of(await fetch_normalised(reference))


# --------------------------------------------------------------------------- import
# An import still "importing" after this long has lost its worker (restart, crash); the next
# refresh closes it as failed instead of being refused forever.
STALE_AFTER = timedelta(minutes=20)


async def start_import(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: tuple[uuid.UUID, str],
    reference: str,
    slug: str | None,
    name: str | None,
    building_code: str | None,
    default_currency: str,
    setup_auto: dict[str, Any] | None = None,
) -> tuple[Project, Any, RegulatoryImport]:
    """Project + one building + summary + import row (status ``importing``). The caller enqueues
    the worker task; floors are left to the user (Decision 5) unless the setup solver is switched
    on for the project (ADR-0025 Decision 1), which the imported drawings' processing triggers."""
    record = await fetch_normalised(reference)
    permit = record["permit"]
    # the explanatory note stays in the import record: project.description is buyer-visible
    project = await projects.create_project(
        db,
        tenant_id=tenant_id,
        data={
            "slug": slug or tasge.suggest_slug(record),
            "name": name or tasge.suggest_name(record),
            "address": {"line1": permit["address"]} if permit.get("address") else {},
        },
        actor=actor,
        default_currency=default_currency,
    )
    building = await projects.create_building(
        db, project, {"code": building_code or tasge.suggest_building_code(record)}, actor
    )
    row = _new_import(tenant_id, project, record, actor[0])
    db.add(row)
    project.regulatory = tasge.summary(record, row.id)
    if setup_auto is not None:
        from unitforma.autopilot.service import set_auto_settings

        set_auto_settings(
            project,
            enabled=bool(setup_auto.get("enabled", True)),
            approve_sheets=bool(setup_auto.get("approve_sheets", True)),
            actor=actor,
        )
    await db.flush()
    await _audit(db, row, actor, "create", record)
    # server-side updated_at changed on flush; load it now so the response can be serialised
    await db.refresh(project)
    return project, building, row


async def refresh(
    db: AsyncSession, project: Project, actor: tuple[uuid.UUID, str]
) -> RegulatoryImport:
    """Fetch the permit again; the worker adds only attachments not yet imported (Decision 7)."""
    current = project.regulatory or {}
    if current.get("source") != tasge.SYSTEM or not current.get("external_id"):
        raise ProblemError(422, "Project was not imported from a permit")
    running = list(
        (
            await db.execute(
                select(RegulatoryImport).where(
                    RegulatoryImport.project_id == project.id,
                    RegulatoryImport.status == "importing",
                )
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    for r in running:
        started = r.started_at or r.created_at
        if started is not None and now - started < STALE_AFTER:
            raise ProblemError(409, "An import is still running for this project")
        # the worker never reported back (restart, crash): close the row so the refresh can run
        r.status = "failed"
        r.error = f"worker did not finish within {int(STALE_AFTER.total_seconds() // 60)} minutes"
        r.finished_at = now
    record = await fetch_normalised(str(current["external_id"]))
    row = _new_import(project.tenant_id, project, record, actor[0])
    db.add(row)
    project.regulatory = tasge.summary(record, row.id)
    await db.flush()
    await _audit(db, row, actor, "refresh", record)
    return row


async def list_imports(db: AsyncSession, project_id: uuid.UUID) -> list[RegulatoryImport]:
    rows = await db.execute(
        select(RegulatoryImport)
        .where(RegulatoryImport.project_id == project_id)
        .order_by(RegulatoryImport.created_at.desc())
    )
    return list(rows.scalars())


def _new_import(
    tenant_id: uuid.UUID, project: Project, record: dict[str, Any], user_id: uuid.UUID
) -> RegulatoryImport:
    return RegulatoryImport(
        id=new_id(),
        tenant_id=tenant_id,
        project_id=project.id,
        source=tasge.SYSTEM,
        external_id=str(record["source"]["document_id"]),
        status="importing",
        requested_by=user_id,
        started_at=datetime.now(UTC),
        record=record,
        stats={},
    )


async def _audit(
    db: AsyncSession,
    row: RegulatoryImport,
    actor: tuple[uuid.UUID, str],
    action: str,
    record: dict[str, Any],
) -> None:
    await write_audit(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="regulatory_import",
        entity_id=row.id,
        action=action,
        after={
            "source": row.source,
            "external_id": row.external_id,
            "project_id": str(row.project_id),
            "attachments": len(record.get("attachments") or []),
        },
    )


# --------------------------------------------------------------------------- worker body
async def import_attachments(tenant_id: uuid.UUID, import_id: uuid.UUID) -> dict[str, Any]:
    """Download every current, importable attachment that this project does not have yet and
    file it as a document revision; each file in its own transaction (Decision 6)."""
    async with tenant_session(tenant_id, scope="tenant") as db:
        row = (
            await db.execute(select(RegulatoryImport).where(RegulatoryImport.id == import_id))
        ).scalar_one()
        if row.status != "importing":
            return {"skipped": row.status}
        project_id, requested_by, external_id = row.project_id, row.requested_by, row.external_id
        plan = tasge.classify_attachments(row.record)
        existing = {
            int(src["attached_file_id"]): doc_id
            for doc_id, src in await db.execute(
                select(Document.id, Document.source).where(Document.project_id == project_id)
            )
            if isinstance(src, dict)
            and src.get("system") == tasge.SYSTEM
            and src.get("attached_file_id") is not None
        }
    actor = (requested_by, WORKER_ROLE)
    stats: dict[str, list[dict[str, Any]]] = {
        "imported": [],
        "existing": [],
        "skipped": [],
        "failed": [],
    }
    for a in plan:
        brief = {"attached_file_id": a["attached_file_id"], "file_name": a["file_name"]}
        if a["skip_reason"]:
            stats["skipped"].append({**brief, "reason": a["skip_reason"]})
            continue
        if a["attached_file_id"] in existing:
            # filed by an earlier import whose worker died before it queued the ingestion
            # (Decision 8): queue it now instead of leaving it "queued" for ever
            healed = await documents_jobs.requeue_document_if_stuck(
                tenant_id, existing[a["attached_file_id"]]
            )
            stats["existing"].append({**brief, "healed": healed} if healed else brief)
            continue
        try:
            data = await get_fetcher().download(a["download_url"])
        except Exception as e:  # noqa: BLE001 - one failed file must not stop the others
            stats["failed"].append({**brief, "error": str(e)[:200]})
            continue
        mime = tasge.IMPORTABLE_EXTENSIONS[a["extension"]]
        try:
            async with tenant_session(tenant_id, scope="tenant") as db:
                doc = await documents.create_document(
                    db,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    data={
                        "kind": a["kind"],
                        "title": (a["fieldset"] or a["file_name"] or "Permit file")[:200],
                        "source": {
                            "system": tasge.SYSTEM,
                            "document_id": int(external_id),
                            "fieldset_id": a["fieldset_id"],
                            "attached_file_id": a["attached_file_id"],
                            "download_url": a["download_url"],
                        },
                    },
                    actor=actor,
                )
                rev, _ = await documents.create_upload_intent(
                    db,
                    doc,
                    file_name=a["file_name"] or f"{a['attached_file_id']}{a['extension']}",
                    content_type=mime,
                    byte_size=len(data),
                    uploaded_by=requested_by,
                    source_note=f"tas.ge permit {external_id}, file {a['attached_file_id']}",
                )
                get_storage().put_bytes(rev.object_key, data, mime)
                rev = await documents.complete_upload(db, rev, actor)
                rev_id = rev.id
                stats["imported"].append(
                    {**brief, "document_id": str(doc.id), "revision_id": str(rev_id)}
                )
        except Exception as e:  # noqa: BLE001
            log.warning("regulatory.file_failed", import_id=str(import_id), error=str(e))
            stats["failed"].append({**brief, "error": str(e)[:200]})
            continue
        # queued right after this file's commit, not after the last download (Decision 8): a
        # worker lost mid-import leaves at most one revision for the sweep to queue again
        await documents_jobs.defer_ingest(tenant_id, rev_id)
    async with tenant_session(tenant_id, scope="tenant") as db:
        row = (
            await db.execute(select(RegulatoryImport).where(RegulatoryImport.id == import_id))
        ).scalar_one()
        row.status = "done"
        row.stats = stats
        row.finished_at = datetime.now(UTC)
    # every file's ingestion queues a solver run too; this one covers an import that found
    # nothing new to download (ADR-0025 Decision 3)
    from unitforma.autopilot.queue import queue_run

    await queue_run(tenant_id, project_id, "permit_import", requested_by=requested_by)
    return {k: len(v) for k, v in stats.items()}
