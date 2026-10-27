"""Classify pass (ADR-0025 Decision 5 "classify", Decision 8): a document whose kind neither the
name nor the content gave is shown to the image provider, one drawing page at a time, behind
``UF_AI_CLASSIFY`` and a daily cap. Text-only pages never leave the host: a permit decision
names people (ADR-0007 Decision 3); only pages with line work are sent, resized to 1024 px."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from sqlalchemy import func, select

from unitforma.audit.service import write_audit
from unitforma.autopilot import rules
from unitforma.autopilot.passes.common import current_sheets
from unitforma.autopilot.service import Context, session
from unitforma.core.settings import get_settings
from unitforma.documents import jobs as documents_jobs
from unitforma.mapping import service as mapping
from unitforma.renders.provider import ProviderError, get_provider
from unitforma.storage.service import get_storage
from unitforma.tenants.models import AuditLog, Document

STEP = "classify"
AUDIT_ACTION = "classify_ai"


async def used_today(db, tenant_id) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await db.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == AUDIT_ACTION,
                AuditLog.at >= start,
            )
        )
    ).scalar_one()


def shrink(png: bytes, max_edge: int = rules.CLASSIFY_MAX_EDGE_PX) -> tuple[bytes, str]:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGB")
        if max(im.size) > max_edge:
            k = max_edge / max(im.size)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80, optimize=True)
        return buf.getvalue(), "image/jpeg"


def parse_kind(answer: str) -> str | None:
    word = answer.strip().strip(".").strip().lower().replace(" ", "_").replace("-", "_")
    for kind in rules.CLASSIFY_KINDS:
        if word == kind or word.startswith(kind):
            return kind
    return None


def page_is_drawing(n_vectors: int, n_chars: int) -> bool:
    """A page leaves the host only when it is a drawing (ADR-0007 Decision 3): enough line work,
    and, when its text is long (dimension strings, notes, the title block of a real elevation
    sheet run to 4 700 characters), many times more line work than text. A permit decision has no
    line work; an area schedule has table rules, a few hundred, under thousands of characters."""
    if n_vectors < rules.CLASSIFY_MIN_VECTORS:
        return False
    if n_chars <= rules.CLASSIFY_MAX_TEXT_CHARS:
        return True
    return n_vectors >= rules.CLASSIFY_MIN_VECTORS_PER_CHAR * n_chars


async def run(ctx: Context) -> None:
    s = get_settings()
    if not s.ai_classify:
        return
    provider = get_provider()
    if provider is None:
        return
    async with session(ctx) as db:
        used = await used_today(db, ctx.tenant_id)
        pages: list[tuple[Document, str]] = []
        seen: set = set()
        kept: list[str] = []
        for sheet, doc in await current_sheets(db, ctx.project_id):
            if doc.kind_source != "pending" or doc.id in seen or not sheet.raster_key:
                continue
            seen.add(doc.id)
            if (sheet.hints or {}).get("kind") == "text_sheet":
                kept.append(doc.title)  # a text sheet: never sent out
                continue
            extract = mapping.load_extract(sheet)
            vectors = extract.get("vectors") or {}
            n_vectors = sum(int(v or 0) for v in vectors.values())
            n_chars = len((extract.get("text") or "").strip())
            if not page_is_drawing(n_vectors, n_chars):
                kept.append(doc.title)
                continue
            pages.append((doc, sheet.raster_key))
    if kept:
        ctx.decide(
            STEP,
            "skipped",
            f"{len(kept)} document(s) kept on the host",
            "Their first page reads like a document, not a drawing (little line work for its "
            "text), so it was not sent for classification: "
            + ", ".join(kept[:6])
            + (" …" if len(kept) > 6 else "")
            + ". Set the kind on the Documents page",
            needs_you=True,
        )
    if not pages:
        return
    budget = max(0, s.ai_classify_daily_limit - used)
    if budget <= 0:
        ctx.decide(
            STEP,
            "skipped",
            f"{len(pages)} document(s) wait for the daily classification cap",
            f"{used} of {s.ai_classify_daily_limit} pages classified today "
            "(UF_AI_CLASSIFY_DAILY_LIMIT); set their kind on the Documents page or run tomorrow",
            needs_you=True,
        )
        return
    changed = False
    for doc, raster_key in pages[:budget]:
        try:
            image, mime = shrink(get_storage().get_bytes(raster_key))
            answer = await provider.describe(image, mime, rules.CLASSIFY_PROMPT)
        except (ProviderError, Exception) as e:  # noqa: BLE001 - one page must not stop the rest
            ctx.decide(
                STEP,
                "error",
                f"{doc.title}: classification failed",
                str(e)[:300],
                needs_you=True,
                entity_type="document",
                entity_id=doc.id,
            )
            continue
        kind = parse_kind(answer)
        async with session(ctx) as db:
            row = (
                await db.execute(select(Document).where(Document.id == doc.id))
            ).scalar_one_or_none()
            if row is None or row.kind_source != "pending":
                continue
            await write_audit(
                db,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.actor[0],
                actor_role=ctx.actor[1],
                entity_type="document",
                entity_id=row.id,
                action=AUDIT_ACTION,
                before={"kind": row.kind},
                after={"answer": answer[:80], "kind": kind},
            )
            if kind is None:
                ctx.decide(
                    STEP,
                    "skipped",
                    f"{doc.title}: the model could not name a kind",
                    f"Answer: '{answer[:60]}'. Set the kind on the Documents page",
                    needs_you=True,
                    entity_type="document",
                    entity_id=row.id,
                )
                continue
            row.kind, row.kind_source = kind, "ai"
            changed = True
        ctx.decide(
            STEP,
            "accepted",
            f"{doc.title}: {kind}",
            f"Kind named by {provider.name} from the first drawing page",
            confidence=rules.CLASSIFY_CONFIDENCE,
            entity_type="document",
            entity_id=doc.id,
        )
    if len(pages) > budget:
        ctx.decide(
            STEP,
            "skipped",
            f"{len(pages) - budget} document(s) over the daily classification cap",
            "Set their kind on the Documents page or run again tomorrow",
            needs_you=True,
        )
    if changed:
        # newly recognised floor plans propose floors for their pages
        await documents_jobs.resuggest_floors(ctx.tenant_id, ctx.project_id)
