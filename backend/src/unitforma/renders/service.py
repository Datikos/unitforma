"""Generated 3D plan renders: request, worker steps, review (ADR-0017 Decision 3).

A request writes one ``unit_renders`` row and defers ``renders.generate``; the worker crops the
unit's outline from its sheet, asks the provider for the image and stores it as a private
``unit_media`` row (``kind = plan_render``, ``is_ai_generated``); a reviewer approves (the media
becomes public) or rejects (the media is deleted). Nothing reaches buyers before the review.
A request made for a layout (ADR-0022 Decision 4) crops one member unit and stores the image as
media of the layout, so every unit linked to it shows the one reviewed view.
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
from unitforma.storage.service import get_storage
from unitforma.tenants.models import Sheet, Unit, UnitBoundary, UnitLayout, UnitMedia, UnitRender

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
JOINED_PROMPT = (
    " The plan shows two neighbouring apartments joined into one larger apartment. The partition "
    "wall between them already has a wide gap drawn in it: render that gap as an open passage with "
    "no wall and no door, so both parts read as one home with one continuous floor, while every "
    "outer wall, window and door stays as drawn."
)
DISCLOSURE = "Generated from the floor plan by AI — furniture and finishes are illustrative"
CROP_MARGIN = 0.08  # of the outline's box, each side
CROP_MAX_PX = 1536
# the opening cut into the shared wall of two joined units (pixels of the crop before scaling)
OPENING_SHARE = 0.4  # of the shared wall's length
OPENING_MIN_PX, OPENING_MAX_PX = 24, 220
OPENING_DEPTH = 0.05  # of the crop's short side, across the wall
WALL_TOLERANCE = 0.03  # of the crop's short side: how far apart two "shared" edges may lie
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
    db: AsyncSession, unit_id: uuid.UUID | None = None, *, layout_id: uuid.UUID | None = None
) -> list[tuple[UnitRender, UnitMedia | None]]:
    """Renders owned by a unit (its own, not those made for its layout) or by a layout."""
    owner = (
        UnitRender.layout_id == layout_id
        if layout_id is not None
        else (UnitRender.unit_id == unit_id) & UnitRender.layout_id.is_(None)
    )
    rows = await db.execute(
        select(UnitRender, UnitMedia)
        .outerjoin(UnitMedia, UnitMedia.id == UnitRender.media_id)
        .where(owner)
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


async def overview(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    unit_id: uuid.UUID | None = None,
    layout_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": enabled(),
        "provider": s.ai_image_provider,
        "model": s.ai_image_model,
        "daily_limit": s.ai_image_daily_limit,
        "used_today": await used_today(db, tenant_id),
        "cost_per_image_usd": s.ai_image_cost_per_image_usd,
        "items": await list_renders(db, unit_id, layout_id=layout_id),
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
    db: AsyncSession,
    unit: Unit,
    note: str | None,
    actor: Actor,
    partner: Unit | None = None,
    layout: UnitLayout | None = None,
) -> UnitRender:
    """Validate, write the row, defer the job. The crop and the provider call run in the worker.
    With ``partner`` (a unit of the same floor) the render shows both joined into one apartment
    (ADR-0017 E4); the image belongs to ``unit``. With ``layout`` the crop is still ``unit``'s
    outline but the image belongs to the layout (ADR-0022 Decision 4)."""
    s = get_settings()
    if layout is not None and (partner is not None or unit.layout_id != layout.id):
        raise ProblemError(422, "A layout render crops one of its own units, without a partner")
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
    if partner is not None:
        if partner.id == unit.id or partner.project_id != unit.project_id:
            raise ProblemError(422, "The joined unit must be another unit of this project")
        if partner.floor_id != unit.floor_id or partner.building_id != unit.building_id:
            raise ProblemError(422, "The joined unit must be on the same floor")
        p_outline = await current_outline(db, partner.id)
        if p_outline is None or p_outline[1].id != outline[1].id:
            raise ProblemError(
                409, "The joined unit has no outline on the same sheet", "Outline it first"
            )
    owner = UnitRender.layout_id == layout.id if layout else UnitRender.unit_id == unit.id
    active = (
        await db.execute(
            select(func.count()).select_from(UnitRender).where(owner, UnitRender.status.in_(ACTIVE))
        )
    ).scalar_one()
    if active:
        raise ProblemError(
            409, "A render is already running for this " + ("layout" if layout else "unit")
        )
    used = await used_today(db, unit.tenant_id)
    if used >= s.ai_image_daily_limit:
        raise ProblemError(
            429,
            "Daily render limit reached",
            f"{used} of {s.ai_image_daily_limit} requests today; raise UF_AI_IMAGE_DAILY_LIMIT",
        )
    clean = (note or "").strip() or None
    prompt = PROMPT + (JOINED_PROMPT if partner is not None else "")
    colour = ((unit.attributes or {}).get("wall_colour") or "").strip()
    if colour:
        prompt += f" The walls are painted {colour}."
    prompt += f"\n\nAdditional instructions from the sales team: {clean}" if clean else ""
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
        partner_unit_id=partner.id if partner is not None else None,
        layout_id=layout.id if layout is not None else None,
        requested_by=actor[0],
    )
    db.add(r)
    await db.flush()
    await db.refresh(r)
    await _audit(
        db,
        r,
        actor,
        "request",
        {
            "note": clean,
            "model": r.model,
            "partner_unit_id": str(partner.id) if partner else None,
            "layout_id": str(layout.id) if layout else None,
        },
    )
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


Pt = tuple[float, float]


def shared_wall(a: list[Pt], b: list[Pt], tolerance: float) -> tuple[Pt, Pt] | None:
    """The longest stretch where an edge of ``a`` runs along an edge of ``b`` (parallel within
    about 6 degrees and closer than ``tolerance``): the wall the two units share, as the segment
    between the two edges. None when the outlines do not touch."""
    import math

    def edges(r: list[Pt]) -> list[tuple[Pt, Pt]]:
        return [(r[i], r[(i + 1) % len(r)]) for i in range(len(r))]

    best: tuple[float, Pt, Pt] | None = None
    for p1, p2 in edges(a):
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        ux, uy = dx / length, dy / length  # along the edge
        nx, ny = -uy, ux  # across it
        for q1, q2 in edges(b):
            ex, ey = q2[0] - q1[0], q2[1] - q1[1]
            elen = math.hypot(ex, ey)
            if elen < 1e-9 or abs(ux * ex + uy * ey) / elen < 0.995:
                continue  # not parallel
            d1 = (q1[0] - p1[0]) * nx + (q1[1] - p1[1]) * ny
            d2 = (q2[0] - p1[0]) * nx + (q2[1] - p1[1]) * ny
            if abs(d1) > tolerance or abs(d2) > tolerance:
                continue  # parallel but not next to each other
            t1 = (q1[0] - p1[0]) * ux + (q1[1] - p1[1]) * uy
            t2 = (q2[0] - p1[0]) * ux + (q2[1] - p1[1]) * uy
            lo, hi = max(0.0, min(t1, t2)), min(length, max(t1, t2))
            if hi - lo <= 0 or (best and hi - lo <= best[0]):
                continue
            off = (d1 + d2) / 4  # halfway between the two edges
            s1 = (p1[0] + ux * lo + nx * off, p1[1] + uy * lo + ny * off)
            s2 = (p1[0] + ux * hi + nx * off, p1[1] + uy * hi + ny * off)
            best = (hi - lo, s1, s2)
    return (best[1], best[2]) if best else None


def crop_plan(
    raster: bytes,
    ring: list[list[float]],
    margin: float = CROP_MARGIN,
    max_px: int = CROP_MAX_PX,
    extra_rings: list[list[list[float]]] | None = None,
) -> bytes:
    """The outline's bounding box plus ``margin`` with everything outside the ring painted white,
    so the model draws this apartment and not its neighbours; PNG, at most ``max_px`` on the long
    side. With ``extra_rings`` (a joined unit) the shared wall gets a white gap: the model renders
    the drawing more faithfully than the prompt, so the opening is drawn into the plan itself."""
    import math

    from PIL import Image, ImageDraw

    rings = [ring, *(extra_rings or [])]
    if any(len(r) < 3 for r in rings):
        raise ValueError("outline needs three points")
    xs = [float(p[0]) for r in rings for p in r]
    ys = [float(p[1]) for r in rings for p in r]
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
        mask = Image.new("L", part.size, 0)
        draw = ImageDraw.Draw(mask)
        for r in rings:  # every joined unit stays visible, the rest is white
            draw.polygon([(float(x) * w - box[0], float(y) * h - box[1]) for x, y in r], fill=255)
        out = Image.composite(part, Image.new("RGB", part.size, (255, 255, 255)), mask)
        px = [[(float(x) * w - box[0], float(y) * h - box[1]) for x, y in r] for r in rings]
        short = min(part.size)
        for other in px[1:]:
            wall = shared_wall(px[0], other, short * WALL_TOLERANCE)
            if wall is None:
                continue
            (x1, y1), (x2, y2) = wall
            length = math.hypot(x2 - x1, y2 - y1)
            gap = min(OPENING_MAX_PX, max(OPENING_MIN_PX, length * OPENING_SHARE), length * 0.9)
            depth = max(8.0, short * OPENING_DEPTH)
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            nx, ny = -uy, ux
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            corners = [
                (cx - ux * gap / 2 - nx * depth / 2, cy - uy * gap / 2 - ny * depth / 2),
                (cx + ux * gap / 2 - nx * depth / 2, cy + uy * gap / 2 - ny * depth / 2),
                (cx + ux * gap / 2 + nx * depth / 2, cy + uy * gap / 2 + ny * depth / 2),
                (cx - ux * gap / 2 + nx * depth / 2, cy - uy * gap / 2 + ny * depth / 2),
            ]
            ImageDraw.Draw(out).polygon(corners, fill=(255, 255, 255))
        if max(out.size) > max_px:
            out.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


async def store_result(
    db: AsyncSession,
    r: UnitRender,
    unit: Unit,
    image: GeneratedImage,
    partner_code: str | None = None,
    layout: UnitLayout | None = None,
) -> UnitMedia:
    """The generated image becomes a private, labelled media item of the unit, or of the layout
    when the request was made for one."""
    ext = MIME_EXT.get(image.mime, "png")
    mid = new_id()
    owner: media_service.Owner = layout if layout is not None else unit
    key = media_service.media_key(owner, f"{mid.hex[:12]}-3d-plan.{ext}")
    get_storage().put_bytes(key, image.data, image.mime)
    next_order = await media_service.next_sort_order(db, owner)
    if layout is not None:
        alt = f"Generated 3D view of layout {layout.code}" + (
            f" ({layout.name})" if layout.name else ""
        )
        file_name = f"3d-plan-layout-{layout.code}.{ext}"
    elif partner_code:
        alt = f"Generated 3D view of {unit.code} joined with {partner_code}"
        file_name = f"3d-plan-{unit.code}.{ext}"
    else:
        alt = f"Generated 3D view of {unit.code}"
        file_name = f"3d-plan-{unit.code}.{ext}"
    m = UnitMedia(
        id=mid,
        tenant_id=unit.tenant_id,
        project_id=unit.project_id,
        **media_service.owner_of(owner),
        kind="plan_render",
        object_key=key,
        file_name=file_name,
        mime=image.mime,
        byte_size=len(image.data),
        status="ready",
        sort_order=next_order,
        is_public=False,
        alt_text=alt,
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
        after={
            "unit_id": str(r.unit_id),
            "layout_id": str(r.layout_id) if r.layout_id else None,
            "status": r.status,
            **(after or {}),
        },
    )
