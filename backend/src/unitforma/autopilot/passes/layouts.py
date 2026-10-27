"""Layouts pass (ADR-0025 Decision 5 "layouts", Decision 6): apartments whose outlines coincide
form one proposed plan type in the registry (ADR-0022); mirrored flats form their own.

Shapes are compared in metres, centred, aligned on the minimum-area rectangle, in four
orientations and, for mirrors, reflected; IoU at or above ``LAYOUT_MIN_IOU`` joins a cluster.
Units a person linked are never touched; new units matching an earlier proposed layout join it."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

from shapely import affinity
from shapely.geometry import Polygon
from sqlalchemy import select

from unitforma.autopilot import rules
from unitforma.autopilot.service import Context, session
from unitforma.geometry import massing
from unitforma.sales import layouts as layout_service
from unitforma.tenants.models import Project, Unit, UnitBoundary, UnitLayout

STEP = "layouts"


@dataclass
class Shape:
    unit_id: uuid.UUID
    code: str
    area: float
    variants: list[Polygon]  # 0-3 rotations, 4-7 the mirror's rotations


def normalise(ring_m: list[list[float]]) -> list[Polygon] | None:
    """Centred, long side horizontal; the four orientations and their mirrors."""
    try:
        poly = Polygon(ring_m).buffer(0)
    except (ValueError, TypeError):
        return None
    if poly.is_empty or poly.area <= 0 or poly.geom_type != "Polygon":
        return None
    rect = massing.building_rectangle([list(poly.exterior.coords)[:-1]])
    if rect is None:
        return None
    (ax, ay), (bx, by) = rect[0], rect[1]
    angle = math.degrees(math.atan2(by - ay, bx - ax))
    c = poly.centroid
    base = affinity.translate(affinity.rotate(poly, -angle, origin=c), -c.x, -c.y)
    out = [affinity.rotate(base, k * 90, origin=(0, 0)) for k in range(4)]
    mirror = affinity.scale(base, xfact=-1, yfact=1, origin=(0, 0))
    out += [affinity.rotate(mirror, k * 90, origin=(0, 0)) for k in range(4)]
    return out


def match(a: Shape, b: Shape) -> tuple[float, bool]:
    """Best IoU of ``b``'s variants against ``a``'s first, and whether it needed the mirror."""
    if abs(a.area - b.area) / max(a.area, b.area) > rules.LAYOUT_AREA_TOLERANCE:
        return 0.0, False
    ref = a.variants[0]
    best, mirrored = 0.0, False
    for i, v in enumerate(b.variants):
        union = ref.union(v).area
        if union <= 0:
            continue
        iou = ref.intersection(v).area / union
        if iou > best:
            best, mirrored = iou, i >= 4
    return best, mirrored


class _Clusters:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        a, b = self.find(i), self.find(j)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def cluster(shapes: list[Shape]) -> tuple[list[list[int]], dict[int, int], dict[int, float]]:
    """Groups of indexes (direct matches), mirror relations between groups (by the group's first
    index) and the lowest IoU inside each group."""
    n = len(shapes)
    uf = _Clusters(n)
    mirrors: list[tuple[int, int, float]] = []
    lowest: dict[int, float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            iou, mirrored = match(shapes[i], shapes[j])
            if iou < rules.LAYOUT_MIN_IOU:
                continue
            if mirrored:
                mirrors.append((i, j, iou))
            else:
                uf.union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    for i in range(n):
        for j in range(i + 1, n):
            if uf.find(i) == uf.find(j):
                iou, _m = match(shapes[i], shapes[j])
                r = uf.find(i)
                lowest[r] = min(lowest.get(r, 1.0), iou)
    mirror_of: dict[int, int] = {}
    for i, j, _iou in mirrors:
        a, b = uf.find(i), uf.find(j)
        if a == b:
            continue
        big, small = (a, b) if len(groups[a]) >= len(groups[b]) else (b, a)
        mirror_of.setdefault(small, big)
    return [groups[r] for r in sorted(groups)], mirror_of, lowest


async def run(ctx: Context) -> None:
    async with session(ctx) as db:
        project = (
            await db.execute(select(Project).where(Project.id == ctx.project_id))
        ).scalar_one()
        rows = await db.execute(
            select(Unit, UnitBoundary)
            .join(UnitBoundary, UnitBoundary.unit_id == Unit.id)
            .where(
                Unit.project_id == ctx.project_id,
                Unit.unit_type == "apartment",
                Unit.lifecycle_status != "removed",
                Unit.layout_id.is_(None),
                UnitBoundary.is_current.is_(True),
                UnitBoundary.polygon_m.is_not(None),
            )
            .order_by(Unit.code)
        )
        shapes: list[Shape] = []
        seen: set[uuid.UUID] = set()
        grouped_before = ctx.seen(STEP)
        for u, b in rows:
            if u.id in seen or str(u.id) in grouped_before:
                continue  # grouped once already; a person unlinked it or deleted the layout
            variants = normalise((b.polygon_m or {}).get("ring") or [])
            if variants is None:
                continue
            seen.add(u.id)
            shapes.append(Shape(u.id, u.code, variants[0].area, variants))
        if len(shapes) < rules.LAYOUT_MIN_MEMBERS:
            return
        existing = list(
            (
                await db.execute(select(UnitLayout).where(UnitLayout.project_id == ctx.project_id))
            ).scalars()
        )
        taken = {lay.code.lower() for lay in existing}
        # the shape of each earlier proposed layout: its first member with an outline
        proposed_shapes: list[tuple[UnitLayout, Shape]] = []
        for lay in existing:
            if lay.source != "autopilot" or lay.status != "proposed":
                continue
            row = (
                await db.execute(
                    select(Unit, UnitBoundary)
                    .join(UnitBoundary, UnitBoundary.unit_id == Unit.id)
                    .where(
                        Unit.layout_id == lay.id,
                        Unit.lifecycle_status != "removed",
                        UnitBoundary.is_current.is_(True),
                        UnitBoundary.polygon_m.is_not(None),
                    )
                    .order_by(Unit.code)
                    .limit(1)
                )
            ).first()
            if row is None:
                continue
            variants = normalise((row[1].polygon_m or {}).get("ring") or [])
            if variants:
                proposed_shapes.append(
                    (lay, Shape(row[0].id, row[0].code, variants[0].area, variants))
                )

        groups, mirror_of, lowest = cluster(shapes)
        groups = [g for g in groups if len(g) >= rules.LAYOUT_MIN_MEMBERS]
        groups.sort(key=lambda g: (-len(g), shapes[g[0]].code))
        code_of_group: dict[int, str] = {}
        created: list[tuple[str, int, float, str | None]] = []
        joined: list[tuple[str, int]] = []
        for g in groups:
            root = g[0]
            rep = shapes[root]
            # an earlier proposed layout with this shape takes the new members
            hit = next(
                (
                    lay
                    for lay, sh in proposed_shapes
                    if match(sh, rep)[0] >= rules.LAYOUT_MIN_IOU and not match(sh, rep)[1]
                ),
                None,
            )
            if hit is not None:
                for i in g:
                    await _link(db, shapes[i].unit_id, hit.id)
                code_of_group[root] = hit.code
                joined.append((hit.code, len(g), [shapes[i].unit_id for i in g]))
                continue
            base_root = mirror_of.get(root)
            base_code = code_of_group.get(base_root) if base_root is not None else None
            code = _next_code(taken, base_code)
            taken.add(code.lower())
            code_of_group[root] = code
            iou = lowest.get(root, 1.0)
            lay = await layout_service.create(
                db,
                project,
                {
                    "code": code,
                    "name": f"Mirror of {base_code}" if base_code else None,
                    "status": "proposed",
                    "source": "autopilot",
                    "match": {
                        "iou_min": round(iou, 3),
                        "members": len(g),
                        "area_m2": round(rep.area, 1),
                        "mirror_of": base_code,
                    },
                },
                ctx.actor,
            )
            for i in g:
                await _link(db, shapes[i].unit_id, lay.id)
            created.append((code, len(g), iou, base_code, [shapes[i].unit_id for i in g]))
    for code, n, iou, base, members in created:
        ctx.decide(
            STEP,
            "accepted",
            f"Plan type {code}: {n} units",
            (f"Mirror image of {base}; " if base else "")
            + f"outlines coincide (IoU ≥ {iou:.2f}). Proposed: confirm it on Layouts & renders "
            "before it shares renders",
            confidence=iou,
            needs_you=True,
            entity_ids=members,
        )
    for code, n, members in joined:
        ctx.decide(
            STEP,
            "accepted",
            f"Plan type {code}: {n} more unit(s)",
            "New outlines match the proposed layout",
            confidence=rules.LAYOUT_MIN_IOU,
            needs_you=True,
            entity_ids=members,
        )


def _next_code(taken: set[str], base: str | None) -> str:
    if base:
        code = f"{base}m"
        k = 2
        while code.lower() in taken:
            code = f"{base}m{k}"
            k += 1
        return code
    k = 1
    while f"l{k}" in taken:
        k += 1
    return f"L{k}"


async def _link(db: Any, unit_id: uuid.UUID, layout_id: uuid.UUID) -> None:
    u = (await db.execute(select(Unit).where(Unit.id == unit_id))).scalar_one()
    if u.layout_id is not None:
        return
    u.layout_id = layout_id  # no attribute mirror: a proposed code must not reach older readers
    u.version += 1
