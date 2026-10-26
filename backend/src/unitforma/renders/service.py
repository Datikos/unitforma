"""Generated 3D plan renders: request, worker steps, review (ADR-0017 Decision 3).

A request writes one ``unit_renders`` row and defers ``renders.generate``; the worker crops the
unit's outline from its sheet, asks the provider for the image and stores it as a private
``unit_media`` row (``kind = plan_render``, ``is_ai_generated``); a reviewer approves (the media
becomes public and, through the layout code, serves every unit with the same plan) or rejects
(the media is deleted). Nothing reaches buyers before the review.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.core.settings import get_settings
from unitforma.jobs.app import app as jobs
from unitforma.renders.provider import GeneratedImage
from unitforma.sales import media as media_service
from unitforma.storage.service import get_storage, object_key
from unitforma.tenants.models import Sheet, Unit, UnitBoundary, UnitMedia, UnitRender

Actor = tuple[uuid.UUID, str]

PROMPT = (
    "Create a photorealistic 3D isometric cutaway view (dollhouse style, seen from above at about "
    "45 degrees) of the apartment shown in the attached architectural floor plan. Keep the exact "
    "wall layout, room proportions, door and window positions as drawn; do not add or remove "
    "rooms. "
    "Furnish every room according to its function on the plan: bedrooms with beds, the living room "
    "with a sofa, the kitchen with cabinets, bathrooms with their fixtures, balconies with outdoor "
    "furniture. Light wooden floors, white walls, soft daylight, a plain white background. "
    "No text, no labels, no dimension lines, no people."
)
DISCLOSURE = "Generated from the floor plan by AI — furniture and finishes are illustrative"
CROP_MARGIN = 0.08  # of the outline's box, each side
CROP_MAX_PX = 1536
ACTIVE = ("queued", "running")
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def enabled() -> bool:
    return get_settings().ai_image_provider != "none"


async def used_today(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        await db.execute(
            select(func.count())
            .select_from(UnitRender)
            .where(UnitRender.tenant_id == tenant_id, UnitRender.created_at >= start)
        )
    ).scalar_one()


async def list_renders(
    db: AsyncSession, unit_id: uuid.UUID
) -> list[tuple[UnitRender, UnitMedia | None]]:
    rows = await db.execute(
        select(UnitRender, UnitMedia)
        .outerjoin(UnitMedia, UnitMedia.id == UnitRender.media_id)
        .where(UnitRender.unit_id == unit_id)
        .order_by(UnitRender.created_at.desc())
    )
    return [(r, m) for r, m in rows.all()]


async def get_render(
    db: AsyncSession, tenant_id: uuid.UUID, render_id: uuid.UUID
) -> tuple[UnitRender, UnitMedia | None]:
    row = (
        await db.execute(
            select(UnitRender, UnitMedia)
            .outerjoin(UnitMedia, UnitMedia.id == UnitRender.media_id)
            .where(UnitRender.tenant_id == tenant_id, UnitRender.id == render_id)
        )
    ).first()
    if row is None:
        raise ProblemError(404, "Render not found")
    return row[0], row[1]


async def overview(db: AsyncSession, unit: Unit) -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": enabled(),
        "provider": s.ai_image_provider,
        "model": s.ai_image_model,
        "daily_limit": s.ai_image_daily_limit,
        "used_today": await used_today(db, unit.tenant_id),
        "cost_per_image_usd": s.ai_image_cost_per_image_usd,
        "items": await list_renders(db, unit.id),
    }


async def current_outline(
    db: AsyncSession, unit_id: uuid.UUID
) -> tuple[UnitBoundary, Sheet] | None:
    """The unit's current outline and its sheet, approved first."""
    row = (
        await db.execute(
            select(UnitBoundary, Sheet)
            .join(Sheet, Sheet.id == UnitBoundary.sheet_id)
            .where(UnitBoundary.unit_id == unit_id, UnitBoundary.is_current.is_(True))
            .order_by((UnitBoundary.status == "approved").desc())
        )
    ).first()
    return (row[0], row[1]) if row is not None else None


async def request_render(
    db: AsyncSession, unit: Unit, note: str | None, actor: Actor
) -> UnitRender:
    """Validate, write the row, defer the job. The crop and the provider call run in the worker."""
    s = get_settings()
    if not enabled():
        raise ProblemError(
            409,
            "Generated renders are not configured",
            "Set UF_AI_IMAGE_PROVIDER=gemini and mount the ai_image_api_key secret",
        )
    if unit.lifecycle_status == "removed":
        raise ProblemError(409, "Unit is removed")
    outline = await current_outline(db, unit.id)
    if outline is None or not outline[1].raster_key:
        raise ProblemError(
            409,
            "The unit has no outline on a processed sheet",
            "Draw or approve its outline in the sheet editor first",
        )
    active = (
        await db.execute(
            select(func.count())
            .select_from(UnitRender)
            .where(UnitRender.unit_id == unit.id, UnitRender.status.in_(ACTIVE))
        )
    ).scalar_one()
    if active:
        raise ProblemError(409, "A render is already running for this unit")
    used = await used_today(db, unit.tenant_id)
    if used >= s.ai_image_daily_limit:
        raise ProblemError(
            429,
            "Daily render limit reached",
            f"{used} of {s.ai_image_daily_limit} requests today; raise UF_AI_IMAGE_DAILY_LIMIT",
        )
    clean = (note or "").strip() or None
    prompt = PROMPT + (f"\n\nAdditional instructions from the sales team: {clean}" if clean else "")
    r = UnitRender(
        id=new_id(),
        tenant_id=unit.tenant_id,
        project_id=unit.project_id,
        unit_id=unit.id,
        status="queued",
        provider=s.ai_image_provider,
        model=s.ai_image_model,
        prompt=prompt,
        note=clean,
        requested_by=actor[0],
    )
    db.add(r)
    await db.flush()
    await db.refresh(r)
    await _audit(db, r, actor, "request", {"note": clean, "model": r.model})
    await jobs.configure_task(name="renders.generate", queue="docs").defer_async(
        tenant_id=str(unit.tenant_id), render_id=str(r.id)
    )
    return r


async def approve(db: AsyncSession, r: UnitRender, media: UnitMedia | None, actor: Actor):
    if r.status != "review" or media is None:
        raise ProblemError(409, "Only a render awaiting review can be approved")
    media.is_public = True
    media.version += 1
    r.status = "approved"
    r.reviewed_by = actor[0]
    r.reviewed_at = datetime.now(UTC)
    await _audit(db, r, actor, "approve", {"media_id": str(media.id)})
    return r


async def reject(db: AsyncSession, r: UnitRender, media: UnitMedia | None, actor: Actor):
    if r.status not in ("review", "failed"):
        raise ProblemError(409, "Only a render awaiting review or a failed one can be rejected")
    if media is not None:
        await media_service.delete(db, media, actor)
    r.media_id = None
    r.status = "rejected"
    r.reviewed_by = actor[0]
    r.reviewed_at = datetime.now(UTC)
    await _audit(db, r, actor, "reject", None)
    return r


def crop_plan(
    raster: bytes,
    ring: list[list[float]],
    margin: float = CROP_MARGIN,
    max_px: int = CROP_MAX_PX,
) -> bytes:
    """The outline's bounding box plus ``margin`` with everything outside the ring painted white,
    so the model draws this apartment and not its neighbours; PNG, at most ``max_px`` on the long
    side."""
    from PIL import Image, ImageDraw

    xs = [float(p[0]) for p in ring]
    ys = [float(p[1]) for p in ring]
    if len(ring) < 3:
        raise ValueError("outline needs three points")
    with Image.open(io.BytesIO(raster)) as im:
        im = im.convert("RGB")
        w, h = im.size
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        box = (
            max(0, round((min(xs) - bw * margin) * w)),
            max(0, round((min(ys) - bh * margin) * h)),
            min(w, round((max(xs) + bw * margin) * w)),
            min(h, round((max(ys) + bh * margin) * h)),
        )
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            raise ValueError("outline is too small on the sheet")
        part = im.crop(box)
        pts = [(x * w - box[0], y * h - box[1]) for x, y in zip(xs, ys, strict=True)]
        mask = Image.new("L", part.size, 0)
        ImageDraw.Draw(mask).polygon(pts, fill=255)
        out = Image.composite(part, Image.new("RGB", part.size, (255, 255, 255)), mask)
        if max(out.size) > max_px:
            out.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


async def store_result(
    db: AsyncSession, r: UnitRender, unit: Unit, image: GeneratedImage
) -> UnitMedia:
    """The generated image becomes a private, labelled media item of the unit."""
    ext = MIME_EXT.get(image.mime, "png")
    mid = new_id()
    key = object_key(
        unit.tenant_id, unit.project_id, "media", str(unit.id), f"{mid.hex[:12]}-3d-plan.{ext}"
    )
    get_storage().put_bytes(key, image.data, image.mime)
    next_order = (
        await db.execute(
            select(func.coalesce(func.max(UnitMedia.sort_order), -1) + 1).where(
                UnitMedia.unit_id == unit.id
            )
        )
    ).scalar_one()
    m = UnitMedia(
        id=mid,
        tenant_id=unit.tenant_id,
        project_id=unit.project_id,
        unit_id=unit.id,
        kind="plan_render",
        object_key=key,
        file_name=f"3d-plan-{unit.code}.{ext}",
        mime=image.mime,
        byte_size=len(image.data),
        status="ready",
        sort_order=next_order,
        is_public=False,
        alt_text=f"Generated 3D view of {unit.code}",
        is_ai_generated=True,
        ai_disclosure_text=DISCLOSURE,
        uploaded_by=r.requested_by,
    )
    db.add(m)
    await db.flush()
    r.media_id = m.id
    r.status = "review"
    r.cost_usd = image.cost_usd
    r.finished_at = datetime.now(UTC)
    await _audit(
        db, r, (r.requested_by, "worker"), "generated", {"media_id": str(m.id), "mime": image.mime}
    )
    return m


async def _audit(
    db: AsyncSession, r: UnitRender, actor: tuple[uuid.UUID | None, str], action: str, after
) -> None:
    await write_audit(
        db,
        tenant_id=r.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_render",
        entity_id=r.id,
        action=action,
        after={"unit_id": str(r.unit_id), "status": r.status, **(after or {})},
    )
