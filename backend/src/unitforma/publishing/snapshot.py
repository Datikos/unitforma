"""Snapshot builder: the only code path that produces public portal data (plan §6.6, §9.3).

Everything public is copied in from allow-lists — unit sales data through
``sales.service.public_view``, branding and portal settings through ``sanitise_*`` — so a
new internal column cannot leak by default. Assets the portal shows (floor plans, the site
plan, the massing model, public media) are copied under ``pub/`` and referenced by an opaque
name; the publication row maps names to storage keys and the portal API only serves names
listed in the publication it is serving.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.geometry import massing
from unitforma.geometry import service as geometry
from unitforma.sales import rules
from unitforma.sales import service as sales
from unitforma.storage.service import get_storage
from unitforma.tenants.models import (
    Building,
    Floor,
    PaymentPlan,
    Project,
    Promotion,
    Publication,
    PublishedUnit,
    Sheet,
    Tenant,
    Unit,
    UnitBoundary,
    UnitMedia,
)

log = structlog.get_logger()

PLAN_MAX_EDGE = 2400
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
EMAIL = re.compile(r"^[^@\s<>]{1,64}@[^@\s<>]{1,190}$")
URL = re.compile(r"^https://[^\s<>\"']{3,200}$")
TEXT_LIMITS = {
    "display_name": 120,
    "tagline": 200,
    "contact_phone": 50,
    "legal_text": 4000,
}
MEDIA_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "application/pdf": "pdf",
}


# --- sanitising (allow-lists) ------------------------------------------------------------------
def sanitise_branding(*layers: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in layers:
        for k, v in (layer or {}).items():
            if not isinstance(v, str) or not v.strip():
                continue
            v = v.strip()
            if k in ("primary_color", "accent_color") and HEX.match(v):
                out[k] = v.lower()
            elif k == "contact_email" and EMAIL.match(v):
                out[k] = v
            elif k == "website" and URL.match(v):
                out[k] = v
            elif k in TEXT_LIMITS:
                out[k] = v[: TEXT_LIMITS[k]]
    return out


def sanitise_portal_settings(ps: dict[str, Any] | None) -> dict[str, Any]:
    ps = ps or {}
    out: dict[str, Any] = {}
    for k, limit in (("hero_text", 2000), ("construction_stage", 80), ("completion", 80)):
        v = ps.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:limit]
    return out


# --- assets ----------------------------------------------------------------------------------
class Assets:
    def __init__(self, tenant_id: uuid.UUID, project_id: uuid.UUID, slug: str):
        self.prefix = f"pub/{tenant_id}/{project_id}"
        self.slug = slug
        self.items: dict[str, str] = {}  # public name -> storage key
        self.storage = get_storage()

    def put(self, data: bytes, ext: str, content_type: str) -> str:
        name = f"{hashlib.sha256(data).hexdigest()[:24]}.{ext}"
        key = f"{self.prefix}/{name}"
        if name not in self.items and self.storage.head(key) is None:
            self.storage.put_bytes(key, data, content_type)
        self.items[name] = key
        return name

    def copy(self, src_key: str, name: str) -> str:
        key = f"{self.prefix}/{name}"
        if name not in self.items and self.storage.head(key) is None:
            self.storage.copy(src_key, key)
        self.items[name] = key
        return name

    def url(self, name: str) -> str:
        return f"/api/v1/portal/projects/{self.slug}/assets/{name}"


Crop = tuple[float, float, float, float]


def plan_image(raster_png: bytes, crop: Crop | None = None) -> tuple[bytes, int, int]:
    """Portal-sized floor/site plan: WebP, long edge ≤ 2400 px (plan §7.3 budgets).

    ``crop`` (normalised x0, y0, x1, y1) keeps one floor's part of a sheet that shows several.
    """
    from PIL import Image

    with Image.open(io.BytesIO(raster_png)) as im:
        im = im.convert("RGB")
        if crop is not None:
            x0, y0, x1, y1 = crop
            im = im.crop(
                (
                    round(x0 * im.width),
                    round(y0 * im.height),
                    round(x1 * im.width),
                    round(y1 * im.height),
                )
            )
        im.thumbnail((PLAN_MAX_EDGE, PLAN_MAX_EDGE))
        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=82, method=4)
        return buf.getvalue(), im.width, im.height


def _plan_asset(
    assets: Assets, sheet: Sheet, cache: dict[Any, dict], crop: Crop | None = None
) -> dict | None:
    key = (sheet.id, crop)
    if key in cache:
        return cache[key]
    if not sheet.raster_key:
        return None
    try:
        data, w, h = plan_image(get_storage().get_bytes(sheet.raster_key), crop)
    except Exception as e:  # noqa: BLE001 - a missing raster only hides that plan
        log.warning("publishing.plan_unavailable", sheet_id=str(sheet.id), error=str(e))
        return None
    ref = {"asset": assets.put(data, "webp", "image/webp"), "width": w, "height": h}
    ref["url"] = assets.url(ref["asset"])
    cache[key] = ref
    return ref


def crop_for(rings: list[list[list[float]]], pad: float = 0.03) -> Crop | None:
    """The part of a sheet holding one floor's units, padded; None when it is most of the sheet."""
    pts = [p for r in rings for p in (r or [])]
    if not pts:
        return None
    x0 = max(0.0, min(p[0] for p in pts) - pad)
    y0 = max(0.0, min(p[1] for p in pts) - pad)
    x1 = min(1.0, max(p[0] for p in pts) + pad)
    y1 = min(1.0, max(p[1] for p in pts) + pad)
    if (x1 - x0) * (y1 - y0) > 0.8 or x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return (round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4))


def recrop(ring: list[list[float]] | None, crop: Crop | None) -> list[list[float]] | None:
    """A sheet-normalised ring in the coordinates of the cropped plan image."""
    if ring is None or crop is None:
        return ring
    x0, y0, x1, y1 = crop
    return [[round((x - x0) / (x1 - x0), 5), round((y - y0) / (y1 - y0), 5)] for x, y in ring]


# --- builder -----------------------------------------------------------------------------------
async def build(
    db: AsyncSession, project: Project, *, status: str, actor_id: uuid.UUID | None
) -> tuple[Publication, dict[str, Any]]:
    """Build an immutable snapshot of the project's public data and its read model rows."""
    tenant = (await db.execute(select(Tenant).where(Tenant.id == project.tenant_id))).scalar_one()
    units = list(
        (
            await db.execute(
                select(Unit).where(
                    Unit.project_id == project.id,
                    Unit.lifecycle_status != "removed",
                    Unit.publication_status.in_(("published", "hidden")),
                )
            )
        ).scalars()
    )
    unit_ids = [u.id for u in units]
    listed = {u.id for u in units if u.publication_status == "published"}
    rows = await sales.inventory(db, project, unit_ids=unit_ids) if unit_ids else []
    rows_by_id = {r["unit_id"]: r for r in rows}

    plans = {
        p.id: p
        for p in (
            await db.execute(select(PaymentPlan).where(PaymentPlan.project_id == project.id))
        ).scalars()
    }
    promos = {
        p.id: p
        for p in (
            await db.execute(select(Promotion).where(Promotion.project_id == project.id))
        ).scalars()
    }
    media_by_unit: dict[uuid.UUID, list[UnitMedia]] = {}
    if unit_ids:
        for m in (
            await db.execute(
                select(UnitMedia)
                .where(UnitMedia.unit_id.in_(unit_ids), UnitMedia.status == "ready")
                .order_by(UnitMedia.sort_order, UnitMedia.created_at)
            )
        ).scalars():
            media_by_unit.setdefault(m.unit_id, []).append(m)

    version_no = (
        await db.execute(
            select(func.coalesce(func.max(Publication.version_no), 0) + 1).where(
                Publication.project_id == project.id
            )
        )
    ).scalar_one()
    pub_id = uuid.uuid4()
    assets = Assets(project.tenant_id, project.id, project.slug)
    plan_cache: dict[Any, dict] = {}

    # floors: for each floor the sheet holding most current boundaries of public units
    boundaries = (
        list(
            await db.execute(
                select(UnitBoundary, Sheet)
                .join(Sheet, Sheet.id == UnitBoundary.sheet_id)
                .where(UnitBoundary.unit_id.in_(unit_ids), UnitBoundary.is_current.is_(True))
            )
        )
        if unit_ids
        else []
    )
    # keyed by the unit's floor: one sheet may show several floors (plan §13.2)
    floor_of_unit = {u.id: u.floor_id for u in units}
    sheets_per_floor: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    sheet_by_id: dict[uuid.UUID, Sheet] = {}
    for b, s in boundaries:
        fid = floor_of_unit.get(b.unit_id)
        if fid is None:
            continue
        sheet_by_id[s.id] = s
        sheets_per_floor.setdefault(fid, {}).setdefault(s.id, 0)
        sheets_per_floor[fid][s.id] += 1
    floor_sheet = {f: max(c, key=c.get) for f, c in sheets_per_floor.items()}
    ring_on_sheet = {(b.unit_id, b.sheet_id): b.polygon.get("ring") for b, _s in boundaries}
    # a sheet shared by several floors is cropped to each floor's units
    shared = {sid for sid in sheet_by_id if sum(sid in c for c in sheets_per_floor.values()) > 1}
    floor_crop: dict[uuid.UUID, Crop | None] = {}
    for fid, sid in floor_sheet.items():
        floor_crop[fid] = (
            crop_for(
                [
                    ring_on_sheet.get((u.id, sid))
                    for u in units
                    if u.floor_id == fid and (u.id, sid) in ring_on_sheet
                ]
            )
            if sid in shared
            else None
        )

    # unit public views + read model rows
    unit_docs: dict[uuid.UUID, dict[str, Any]] = {}
    read_rows: list[PublishedUnit] = []
    for u in sorted(units, key=lambda x: x.code):
        row = rows_by_id.get(u.id)
        if row is None:
            continue
        plan = plans.get(row["payment_plan_id"]) if row["payment_plan_id"] else None
        unit_promos = [promos[p] for p in row["promotion_ids"] if p in promos]
        media = media_by_unit.get(u.id, [])
        view = sales.public_view(row, plan, unit_promos, media)
        media_items = {m.id: m for m in media}
        for item in view.get("media", []):
            m = media_items[uuid.UUID(item["id"])]
            ext = MEDIA_EXT.get(m.mime, "bin")
            name = assets.copy(m.object_key, f"m-{m.id.hex}.{ext}")
            item.pop("id", None)  # internal ids are not needed by the portal
            item["url"] = assets.url(name)
            item["mime"] = m.mime
        sheet_id = floor_sheet.get(u.floor_id)
        if sheet_id is not None:
            crop = floor_crop.get(u.floor_id)
            ref = _plan_asset(assets, sheet_by_id[sheet_id], plan_cache, crop)
            ring = recrop(ring_on_sheet.get((u.id, sheet_id)), crop)
            if ref is not None:
                view["plan"] = {**ref, "ring": ring}
        view["floor_name"] = row["floor_name"]
        view["listed"] = u.id in listed
        unit_docs[u.id] = view
        price = view.get("price") or {}
        read_rows.append(
            PublishedUnit(
                id=uuid.uuid4(),
                tenant_id=project.tenant_id,
                publication_id=pub_id,
                project_id=project.id,
                unit_id=u.id,
                code=u.code,
                building_code=row["building_code"],
                floor_level=row["floor_level"],
                unit_type=u.unit_type,
                availability=row["availability"],
                listed=u.id in listed,
                price_amount=Decimal(price["amount"]) if price.get("amount") else None,
                currency=price.get("currency"),
                area_m2=row["price_area_m2"] if view.get("areas") is not None else None,
                rooms=view.get("rooms", {}).get("rooms") if view.get("rooms") else None,
                bedrooms=view.get("rooms", {}).get("bedrooms") if view.get("rooms") else None,
                sort_order=len(read_rows),
                data=view,
            )
        )

    # buildings & floors (only floors with public units)
    buildings = list(
        (
            await db.execute(
                select(Building)
                .where(Building.project_id == project.id)
                .order_by(Building.sort_order, Building.code)
            )
        ).scalars()
    )
    floors = list(
        (
            await db.execute(
                select(Floor)
                .join(Building, Building.id == Floor.building_id)
                .where(Building.project_id == project.id)
                .order_by(Floor.level)
            )
        ).scalars()
    )
    units_by_floor: dict[uuid.UUID, list[Unit]] = {}
    for u in units:
        if u.id in unit_docs:
            units_by_floor.setdefault(u.floor_id, []).append(u)
    building_docs = []
    for b in buildings:
        fdocs = []
        for f in [f for f in floors if f.building_id == b.id]:
            fu = sorted(units_by_floor.get(f.id, []), key=lambda x: x.code)
            if not fu:
                continue
            sheet_id = floor_sheet.get(f.id)
            crop = floor_crop.get(f.id)
            ref = _plan_asset(assets, sheet_by_id[sheet_id], plan_cache, crop) if sheet_id else None
            fdocs.append(
                {
                    "level": f.level,
                    "name": f.display_name,
                    "plan": ref,
                    "units": [
                        {
                            "id": str(u.id),
                            "code": u.code,
                            "unit_type": u.unit_type,
                            "availability": unit_docs[u.id]["availability"],
                            "ring": recrop(ring_on_sheet.get((u.id, sheet_id)), crop)
                            if sheet_id
                            else None,
                        }
                        for u in fu
                        if u.id in listed
                    ],
                }
            )
        if fdocs:
            building_docs.append({"code": b.code, "name": b.name, "kind": b.kind, "floors": fdocs})

    site = await _site(db, project, assets, {d["code"] for d in building_docs}, plan_cache)
    massing_ref = await _massing(db, project, assets, listed)

    listed_docs = [unit_docs[u] for u in unit_docs if u in listed]
    prices = [
        Decimal(d["price"]["amount"])
        for d in listed_docs
        if d.get("price") and d["price"]["amount"]
    ]
    currencies = {d["price"]["currency"] for d in listed_docs if d.get("price")}
    areas = [Decimal(r.area_m2) for r in read_rows if r.listed and r.area_m2 is not None]
    stats = {
        "units": len(listed_docs),
        "available": sum(1 for d in listed_docs if d["availability"] == "available"),
        "price_from": (
            {"amount": format(min(prices), "f"), "currency": next(iter(currencies))}
            if prices and len(currencies) == 1
            else None
        ),
        "area_min": format(min(areas), "f") if areas else None,
        "area_max": format(max(areas), "f") if areas else None,
        "rooms": sorted(
            {d["rooms"]["rooms"] for d in listed_docs if d.get("rooms") and d["rooms"]["rooms"]}
        ),
        "unit_types": sorted({d["unit_type"] for d in listed_docs}),
    }
    public_plans = [
        {"name": p.name, "description": p.description, "schedule": p.schedule}
        for p in plans.values()
        if p.is_public and p.is_active
    ]
    public_promos = [
        rules.to_json(
            {
                "name": p.name,
                "kind": p.kind,
                "value": p.value,
                "terms": p.terms,
                "valid_from": p.valid_from,
                "valid_to": p.valid_to,
            }
        )
        for p in promos.values()
        if p.is_public and p.is_active
    ]
    now = datetime.now(UTC)
    doc = rules.to_json(
        {
            "schema": 1,
            "publication": {
                "id": pub_id,
                "version_no": version_no,
                "status": status,
                "built_at": now,
            },
            "tenant": {"name": tenant.name, "slug": tenant.slug},
            "branding": sanitise_branding(
                tenant.branding, (project.portal_settings or {}).get("branding")
            ),
            "project": {
                "slug": project.slug,
                "name": project.name,
                "description": project.description,
                "address": {
                    k: v
                    for k, v in (project.address or {}).items()
                    if k in ("line1", "line2", "city", "region", "postcode", "country")
                    and isinstance(v, str)
                },
                "currency": project.currency,
                "area_definitions": [
                    {k: a.get(k) for k in ("key", "label", "description")}
                    for a in (project.area_definitions or [])
                    if isinstance(a, dict)
                ],
                "price_area_type": rules.resolve_price_area_type(project, None),
                **sanitise_portal_settings(project.portal_settings),
            },
            "stats": stats,
            "site": site,
            "buildings": building_docs,
            "massing": massing_ref,
            "payment_plans": public_plans,
            "promotions": public_promos,
        }
    )
    data = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
    snapshot_key = f"t/{project.tenant_id}/p/{project.id}/publications/{pub_id}.json"
    get_storage().put_bytes(snapshot_key, data, "application/json")
    pub = Publication(
        id=pub_id,
        tenant_id=project.tenant_id,
        project_id=project.id,
        version_no=version_no,
        status=status,
        snapshot_key=snapshot_key,
        summary={**stats, "bytes": len(data), "assets": len(assets.items)},
        assets=assets.items,
        created_by=actor_id,
        published_at=now if status == "published" else None,
    )
    db.add(pub)
    await db.flush()
    for r in read_rows:
        db.add(r)
    await db.flush()
    return pub, doc


async def _site(
    db: AsyncSession,
    project: Project,
    assets: Assets,
    public_codes: set[str],
    cache: dict[Any, dict],
) -> dict[str, Any] | None:
    """Site plan image with building footprints placed by their site transforms (plan §3.5)."""
    sheet_id = (project.site_frame or {}).get("sheet_id")
    sheet = None
    if sheet_id:
        try:
            sheet = (
                await db.execute(select(Sheet).where(Sheet.id == uuid.UUID(str(sheet_id))))
            ).scalar_one_or_none()
        except ValueError:
            sheet = None
    ref = _plan_asset(assets, sheet, cache) if sheet is not None else None
    cal = sheet.calibration if sheet is not None else None
    fps = await geometry.footprints(db, project)
    out_buildings = []
    for f in fps:
        if f["code"] not in public_codes:
            continue
        ring = None
        if (
            f["ring_m"]
            and cal
            and cal.get("m_per_px")
            and sheet.raster_width
            and sheet.raster_height
            and f["placement_status"] != "unplaced"
        ):
            place = massing.Placement.from_dict(f["site_transform"])
            m = cal["m_per_px"]
            ring = []
            for p in f["ring_m"]:
                x, y = place.apply((float(p[0]), float(p[1])))
                ring.append(
                    [
                        round(x / (m * sheet.raster_width), 5),
                        round(y / (m * sheet.raster_height), 5),
                    ]
                )
        out_buildings.append(
            {
                "code": f["code"],
                "name": f["name"],
                "floors": f["floors"],
                "height_m": f["height_m"],
                "ring": ring,
            }
        )
    if ref is None and not out_buildings:
        return None
    return {"plan": ref, "buildings": out_buildings}


async def _massing(
    db: AsyncSession, project: Project, assets: Assets, listed: set[uuid.UUID]
) -> dict[str, Any] | None:
    """A public GLB with only listed units and only public node extras."""
    if not listed:
        return None
    buildings, _stats = await geometry.collect(db, project)
    keep = {str(u) for u in listed}
    public_buildings = []
    for b in buildings:
        units = [u for u in b.units if u.unit_id in keep]
        for u in units:
            u.extras = {}
        if units:
            b.units = units
            b.extras = {}
            public_buildings.append(b)
    if not public_buildings:
        return None
    data, stats = massing.build_glb(public_buildings, {"project": project.slug})
    name = assets.put(data, "glb", "model/gltf-binary")
    return {
        "asset": name,
        "url": assets.url(name),
        "bytes": stats["bytes"],
        "units": stats["units"],
        "disclaimer": massing.DISCLAIMER,
    }
