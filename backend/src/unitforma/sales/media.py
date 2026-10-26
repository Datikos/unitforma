"""Unit and layout media: presigned upload, ordering, visibility and the AI-generated flag
(plan §5.3). A media row is owned by one unit or by one layout (ADR-0022 Decision 3); every
function here takes the owner and the rest of the flow is the same."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.storage.service import get_storage, object_key, safe_filename
from unitforma.tenants.models import Unit, UnitLayout, UnitMedia

ALLOWED_MEDIA = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "application/pdf",
}
MAX_MEDIA_BYTES = 500 * 1024 * 1024
DEFAULT_AI_DISCLOSURE = "AI-generated visualisation — not a photograph of the finished unit"

Actor = tuple[uuid.UUID, str]
Owner = Unit | UnitLayout


def owner_filter(unit_id: uuid.UUID | None = None, layout_id: uuid.UUID | None = None):
    if (unit_id is None) == (layout_id is None):
        raise ValueError("media are listed per unit or per layout")
    return UnitMedia.unit_id == unit_id if unit_id else UnitMedia.layout_id == layout_id


def owner_of(owner: Owner) -> dict[str, uuid.UUID | None]:
    if isinstance(owner, UnitLayout):
        return {"unit_id": None, "layout_id": owner.id}
    return {"unit_id": owner.id, "layout_id": None}


async def list_media(
    db: AsyncSession, unit_id: uuid.UUID | None = None, *, layout_id: uuid.UUID | None = None
) -> list[UnitMedia]:
    rows = await db.execute(
        select(UnitMedia)
        .where(owner_filter(unit_id, layout_id))
        .order_by(UnitMedia.sort_order, UnitMedia.created_at)
    )
    return list(rows.scalars())


async def get_media(db: AsyncSession, tenant_id: uuid.UUID, media_id: uuid.UUID) -> UnitMedia:
    m = (
        await db.execute(
            select(UnitMedia).where(UnitMedia.tenant_id == tenant_id, UnitMedia.id == media_id)
        )
    ).scalar_one_or_none()
    if m is None:
        raise ProblemError(404, "Media not found")
    return m


def _ai_fields(data: dict[str, Any], current_text: str | None = None) -> None:
    if data.get("is_ai_generated"):
        data["ai_disclosure_text"] = (
            data.get("ai_disclosure_text") or current_text or DEFAULT_AI_DISCLOSURE
        )


def media_key(owner: Owner, name: str) -> str:
    """Object key of a media file: ``media/<unit id>/`` for a unit, ``media/layout/<layout id>/``
    for a layout."""
    parts = ("layout", str(owner.id)) if isinstance(owner, UnitLayout) else (str(owner.id),)
    return object_key(owner.tenant_id, owner.project_id, "media", *parts, name)


async def next_sort_order(db: AsyncSession, owner: Owner) -> int:
    return (
        await db.execute(
            select(func.coalesce(func.max(UnitMedia.sort_order), -1) + 1).where(
                owner_filter(**owner_of(owner))
            )
        )
    ).scalar_one()


async def create_intent(
    db: AsyncSession, owner: Owner, data: dict[str, Any], actor: Actor
) -> tuple[UnitMedia, str]:
    if data["content_type"] not in ALLOWED_MEDIA:
        raise ProblemError(415, "Unsupported media type", data["content_type"])
    if not 0 < data["byte_size"] <= MAX_MEDIA_BYTES:
        raise ProblemError(413, "File too large")
    if isinstance(owner, Unit) and owner.lifecycle_status == "removed":
        raise ProblemError(409, "Unit is removed")
    _ai_fields(data)
    next_order = await next_sort_order(db, owner)
    mid = new_id()
    key = media_key(owner, f"{mid.hex[:12]}-{safe_filename(data['file_name'])}")
    m = UnitMedia(
        id=mid,
        tenant_id=owner.tenant_id,
        project_id=owner.project_id,
        **owner_of(owner),
        kind=data["kind"],
        object_key=key,
        file_name=safe_filename(data["file_name"]),
        mime=data["content_type"],
        byte_size=data["byte_size"],
        status="pending",
        sort_order=next_order,
        is_public=data.get("is_public", False),
        alt_text=data.get("alt_text"),
        is_ai_generated=bool(data.get("is_ai_generated")),
        ai_disclosure_text=data.get("ai_disclosure_text"),
        uploaded_by=actor[0],
    )
    db.add(m)
    await db.flush()
    return m, get_storage().presign_put(key, data["content_type"])


async def complete(db: AsyncSession, m: UnitMedia, actor: Actor) -> UnitMedia:
    if m.status == "ready":
        return m
    info = get_storage().head(m.object_key)
    if info is None:
        raise ProblemError(
            409, "Upload not found in storage", "PUT the file to the upload URL first"
        )
    m.byte_size = info.size
    m.status = "ready"
    await _audit(db, m, actor, "upload", {"file_name": m.file_name, "kind": m.kind})
    return m


async def update(db: AsyncSession, m: UnitMedia, data: dict[str, Any], version: int, actor: Actor):
    if m.version != version:
        raise ProblemError(409, "Conflict", f"Media changed (current version {m.version})")
    if data.get("is_ai_generated") is False:
        data["ai_disclosure_text"] = None
    elif data.get("is_ai_generated") or (m.is_ai_generated and "ai_disclosure_text" in data):
        data["is_ai_generated"] = True
        _ai_fields(data, m.ai_disclosure_text)
    for k, v in data.items():
        setattr(m, k, v)
    m.version += 1
    await _audit(db, m, actor, "update", data)
    return m


async def reorder(
    db: AsyncSession, owner: Owner, ids: list[uuid.UUID], actor: Actor
) -> list[UnitMedia]:
    items = await list_media(db, **owner_of(owner))
    if sorted(map(str, ids)) != sorted(str(m.id) for m in items):
        raise ProblemError(422, "The order must list every media item of the owner exactly once")
    pos = {mid: i for i, mid in enumerate(ids)}
    for m in items:
        m.sort_order = pos[m.id]
    await write_audit(
        db,
        tenant_id=owner.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_media",
        entity_id=owner.id,
        action="reorder",
        after={"order": [str(i) for i in ids]},
    )
    return sorted(items, key=lambda m: m.sort_order)


async def delete(db: AsyncSession, m: UnitMedia, actor: Actor) -> None:
    await _audit(db, m, actor, "delete", {"file_name": m.file_name})
    await db.delete(m)
    try:
        get_storage().delete(m.object_key)
    except Exception:  # noqa: BLE001,S110 - an orphaned object is cleaned by retention later
        pass


def signed_url(m: UnitMedia) -> str | None:
    return get_storage().presign_get(m.object_key, expires=3600) if m.status == "ready" else None


async def _audit(db, m: UnitMedia, actor: Actor, action: str, after: dict[str, Any]) -> None:
    await write_audit(
        db,
        tenant_id=m.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="unit_media",
        entity_id=m.unit_id or m.layout_id,
        action=action,
        after={"media_id": str(m.id), **{k: v for k, v in after.items() if k != "content_type"}},
    )
