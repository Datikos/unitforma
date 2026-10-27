"""Placement pass (ADR-0025 Decision 5 "placement"): an unplaced building's footprint is laid
over every closed face of the calibrated site plan whose area is close to it; the best rotation
and translation by IoU become the ``site_transform``, confirmed above one threshold and left as
a draft (needs you) above a lower one.

The footprint is the union of apartment outlines, so stair cores are notches the site plan's
envelope lacks; the first real projects tune the two thresholds (ADR-0025 D3)."""

from __future__ import annotations

import math
import uuid
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon
from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.geometry import service as geometry_service
from unitforma.inventory import geometry
from unitforma.mapping import service as mapping
from unitforma.mapping import suggest
from unitforma.projects import service as projects
from unitforma.tenants.models import Building, Project, Sheet

STEP = "placement"


def site_faces(sheet: Sheet) -> list[Polygon]:
    """Closed faces of the site sheet in site metres (the calibration's frame)."""
    extract = mapping.load_extract(sheet)
    cal = sheet.calibration or {}
    if not extract or not cal.get("m_per_px"):
        return []
    cands = suggest.closed_loops(
        extract, page_m=mapping.sheet_metres(sheet, extract), min_area=0.0002, max_area=0.6
    )
    out = []
    for c in cands:
        try:
            p = Polygon(geometry.ring_to_metres(c.ring, cal)).buffer(0)
        except (ValueError, TypeError, KeyError):
            continue
        if not p.is_empty and p.geom_type == "Polygon":
            out.append(p)
    return out


def _placed(poly: Polygon, angle_deg: float, tx: float, ty: float) -> Polygon:
    """``Placement.apply``: p' = (tx, ty) + R(angle) p."""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return affinity.affine_transform(poly, [c, -s, s, c, tx, ty])


def _fit_at(foot: Polygon, face: Polygon, angle: float) -> tuple[float, float, float]:
    """Translation that puts the rotated footprint's centroid on the face's, and the IoU."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    fc, cf = foot.centroid, face.centroid
    tx = cf.x - (c * fc.x - s * fc.y)
    ty = cf.y - (s * fc.x + c * fc.y)
    placed = _placed(foot, angle, tx, ty)
    union = placed.union(face).area
    iou = placed.intersection(face).area / union if union > 0 else 0.0
    return iou, tx, ty


def best_fit(foot: Polygon, faces: list[Polygon]) -> dict[str, Any] | None:
    area = foot.area
    best: dict[str, Any] | None = None
    for face in faces:
        if abs(face.area - area) / max(face.area, area) > rules.PLACEMENT_AREA_TOLERANCE:
            continue
        coarse = max(
            (
                (_fit_at(foot, face, ang), ang)
                for ang in _angles(0.0, 360.0, rules.PLACEMENT_COARSE_STEP_DEG)
            ),
            key=lambda t: t[0][0],
        )
        (iou, tx, ty), ang = coarse
        lo, hi = ang - rules.PLACEMENT_COARSE_STEP_DEG, ang + rules.PLACEMENT_COARSE_STEP_DEG
        for fine in _angles(lo, hi, rules.PLACEMENT_FINE_STEP_DEG):
            f_iou, f_tx, f_ty = _fit_at(foot, face, fine)
            if f_iou > iou:
                iou, tx, ty, ang = f_iou, f_tx, f_ty, fine
        if best is None or iou > best["iou"]:
            best = {"iou": iou, "tx": tx, "ty": ty, "rotation_deg": ang % 360.0}
    return best


def _angles(lo: float, hi: float, step: float) -> list[float]:
    n = int(round((hi - lo) / step))
    return [lo + i * step for i in range(n)]


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        sid = (project.site_frame or {}).get("sheet_id")
        if not sid:
            return
        try:
            sheet = (
                await db.execute(select(Sheet).where(Sheet.id == uuid.UUID(str(sid))))
            ).scalar_one_or_none()
        except ValueError:
            sheet = None
        if sheet is None or not (sheet.calibration or {}).get("m_per_px"):
            return
        faces = site_faces(sheet)
        targets = [
            f
            for f in await geometry_service.footprints(db, project)
            if f["placement_status"] == "unplaced" and f["ring_m"]
        ]
        if not targets:
            return
        if not faces:
            ctx.decide(
                STEP,
                "skipped",
                "Site plan has no closed outlines",
                "Nothing on the site plan's line work matches a building; place the "
                f"{len(targets)} building(s) by hand on Site placement",
                needs_you=True,
            )
            return
        for f in targets:
            foot = Polygon(f["ring_m"]).buffer(0)
            fit = best_fit(foot, faces) if not foot.is_empty else None
            if fit is None or fit["iou"] < rules.PLACEMENT_DRAFT_IOU:
                ctx.decide(
                    STEP,
                    "skipped",
                    f"Building {f['code']}: no matching outline on the site plan",
                    (
                        f"Best overlap {fit['iou']:.2f}"
                        if fit
                        else "No face of the site plan has a similar area"
                    )
                    + "; place it by hand on Site placement",
                    needs_you=True,
                    entity_type="building",
                    entity_id=f["building_id"],
                )
                continue
            status = "confirmed" if fit["iou"] >= rules.PLACEMENT_CONFIRM_IOU else "draft"
            b = (
                await db.execute(select(Building).where(Building.id == f["building_id"]))
            ).scalar_one()
            if b.placement_status != "unplaced":
                continue
            await projects.update_building(
                db,
                b,
                {
                    "site_transform": {
                        "tx": round(fit["tx"], 3),
                        "ty": round(fit["ty"], 3),
                        "rotation_deg": round(fit["rotation_deg"], 2),
                        "scale": 1.0,
                        "elevation": 0.0,
                    },
                    "placement_status": status,
                },
                b.version,
                ctx.actor,
            )
            ctx.decide(
                STEP,
                "accepted",
                f"Building {f['code']} placed ({status})",
                f"Footprint matched a site plan outline with {fit['iou']:.2f} overlap at "
                f"{fit['rotation_deg']:.1f}°"
                + ("" if status == "confirmed" else "; confirm or adjust it on Site placement"),
                confidence=fit["iou"],
                needs_you=status != "confirmed",
                entity_type="building",
                entity_id=b.id,
            )
