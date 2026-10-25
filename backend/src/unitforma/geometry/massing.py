"""Schematic massing: extrude unit polygons into a glTF 2.0 binary (GLB) — plan §11.3.

Pure functions, no database or storage. The output is deliberately simple so the portal's
three.js viewer can pick units by node name: one node + one mesh per unit, grouped under a
node per building, with ``extras`` carrying ids and codes. Coordinates: site frame metres,
X east/right, Z south/down-the-sheet, Y up (glTF is Y-up, right-handed).

The model is labelled "Schematic model generated from floor plans — not an architectural model".
Compression (Draco/meshopt via gltf-transform) is a worker-image post-processing step and is
not needed for massing models, which stay far below the 2 MB budget per building.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]
Ring = list[Point]

DISCLAIMER = "Schematic model generated from floor plans — not an architectural model"
GENERATOR = "unitforma-massing"

TYPE_COLOURS = {
    "apartment": [0.86, 0.88, 0.92, 1.0],
    "commercial": [0.96, 0.80, 0.55, 1.0],
    "parking": [0.70, 0.72, 0.76, 1.0],
    "storage": [0.78, 0.84, 0.72, 1.0],
}


@dataclass
class Placement:
    """Building local frame → site frame (plan §3.5 ``site_transform``)."""

    tx: float = 0.0
    ty: float = 0.0
    rotation_deg: float = 0.0
    scale: float = 1.0
    elevation: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Placement:
        d = d or {}
        return cls(
            tx=float(d.get("tx", 0) or 0),
            ty=float(d.get("ty", 0) or 0),
            rotation_deg=float(d.get("rotation_deg", 0) or 0),
            scale=float(d.get("scale", 1) or 1),
            elevation=float(d.get("elevation", 0) or 0),
        )

    def apply(self, p: Point) -> Point:
        a = math.radians(self.rotation_deg)
        c, s = math.cos(a), math.sin(a)
        x, y = p
        return (
            self.tx + self.scale * (c * x - s * y),
            self.ty + self.scale * (s * x + c * y),
        )


@dataclass
class UnitSolid:
    unit_id: str
    code: str
    unit_type: str
    building_code: str
    floor_level: int
    ring_m: Ring  # building-local metres (sheet frame: x right, y down)
    base_m: float
    height_m: float
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class FacadeImage:
    """An elevation drawing cropped to one side of the building (ADR-0016 Decision 2).

    ``side`` indexes the sides of the building's bounding rectangle as ``building_rectangle``
    orders them (clockwise on the sheet, side k runs from corner k to corner k+1).
    """

    side: int
    image: bytes
    mime: str = "image/jpeg"
    flip: bool = False


@dataclass
class BuildingSolids:
    building_id: str
    code: str
    name: str | None
    placement: Placement
    units: list[UnitSolid]
    extras: dict[str, Any] = field(default_factory=dict)
    facades: list[FacadeImage] = field(default_factory=list)
    # the facade rectangle fixed by the service from every unit of the building, so a GLB built
    # from a subset (the portal keeps listed units only) maps the drawings exactly as the admin
    # page's ``sides`` describe them
    facade_rect: list[Point] | None = None


# --- building rectangle: the four sides a facade drawing can be mapped to ---------------------
def _convex_hull(points: list[Point]) -> list[Point]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def building_rectangle(rings: list[Ring]) -> list[Point] | None:
    """Minimum-area bounding rectangle of all rings, corners clockwise on the sheet (y down).

    Side k is the edge from corner k to corner k+1; the first corner is the one with the
    smallest (x, y), so the numbering is stable between calls and across frames that only
    rotate, scale or translate (a placement never mirrors).
    """
    pts = [(float(x), float(y)) for r in rings for x, y in r]
    hull = _convex_hull(pts)
    if len(hull) < 3:
        return None
    best: tuple[float, list[Point]] | None = None
    for i in range(len(hull)):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % len(hull)]
        length = math.hypot(bx - ax, by - ay)
        if length < 1e-9:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length  # along the edge
        vx, vy = -uy, ux  # perpendicular
        us = [(p[0] - ax) * ux + (p[1] - ay) * uy for p in hull]
        vs = [(p[0] - ax) * vx + (p[1] - ay) * vy for p in hull]
        u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
        area = (u1 - u0) * (v1 - v0)
        if best is None or area < best[0] - 1e-9:
            corners = [
                (ax + u * ux + v * vx, ay + u * uy + v * vy)
                for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            ]
            best = (area, corners)
    if best is None:
        return None
    rect = best[1]
    # clockwise as seen on the sheet (y down): shoelace area positive in these coordinates
    if signed_area(rect) < 0:
        rect.reverse()
    start = min(range(4), key=lambda k: (round(rect[k][0], 3), round(rect[k][1], 3)))
    rect = rect[start:] + rect[:start]
    return [(round(x, 4), round(y, 4)) for x, y in rect]


@dataclass
class Side:
    index: int
    a: Point
    b: Point
    length: float
    normal: Point  # outward, in the sheet frame (x right, y down)


def rectangle_sides(rect: list[Point]) -> list[Side]:
    out: list[Side] = []
    for k in range(4):
        a, b = rect[k], rect[(k + 1) % 4]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        dx, dy = ((b[0] - a[0]) / length, (b[1] - a[1]) / length) if length else (1.0, 0.0)
        # clockwise on a y-down sheet keeps the interior on the right, so outward is the left
        out.append(Side(k, a, b, round(length, 3), (dy, -dx)))
    return out


# A wall is textured when it faces a side of the building rectangle and lies within this many
# metres of it, inside (recesses, set-back floors) or outside (balconies): the elevation drawing
# is an orthographic projection, so every wall facing it shows the drawing at its own position.
FACADE_DEPTH_M = 6.0
# units that never define the building rectangle (stalls on the ground floor around the house)
FACADE_EXCLUDED_TYPES = ("parking",)


def facade_rings(units: list[UnitSolid]) -> list[Ring]:
    """The rings that define the building rectangle: the lowest floor that has units other than
    parking stalls, the same choice as the footprint endpoint's ``sides``."""
    kept = [u for u in units if u.unit_type not in FACADE_EXCLUDED_TYPES and len(u.ring_m) >= 3]
    if not kept:
        return []
    lowest = min(u.floor_level for u in kept)
    return [u.ring_m for u in kept if u.floor_level == lowest]


def _along_side(p: Point, side: Side) -> tuple[float, float]:
    """``t`` along the side (0 at ``a``, 1 at ``b``) and the signed distance from it, positive
    outside the rectangle."""
    dx, dy = side.b[0] - side.a[0], side.b[1] - side.a[1]
    t = ((p[0] - side.a[0]) * dx + (p[1] - side.a[1]) * dy) / (side.length * side.length)
    d = (p[0] - side.a[0]) * side.normal[0] + (p[1] - side.a[1]) * side.normal[1]
    return t, d


def _faces_side(
    p0: Point, p1: Point, orientation: float, side: Side, depth: float
) -> tuple[float, float] | None:
    """``(t0, t1)`` along the side for a wall ``p0``→``p1`` of a ring with the given shoelace
    sign when the wall faces the side and lies within ``depth`` metres of it, else None."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-6 or side.length < 1e-9:
        return None
    nx, ny = (dy / length, -dx / length) if orientation >= 0 else (-dy / length, dx / length)
    if nx * side.normal[0] + ny * side.normal[1] < 0.9:
        return None
    t0, d0 = _along_side(p0, side)
    t1, d1 = _along_side(p1, side)
    if not (-depth <= d0 <= depth and -depth <= d1 <= depth):
        return None
    if max(t0, t1) < -0.02 or min(t0, t1) > 1.02:
        return None
    return min(1.0, max(0.0, t0)), min(1.0, max(0.0, t1))


# --- triangulation -------------------------------------------------------------------------
def signed_area(ring: Ring) -> float:
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2


def _point_in_triangle(p: Point, a: Point, b: Point, c: Point) -> bool:
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])

    d1, d2, d3 = cross(a, b, p), cross(b, c, p), cross(c, a, p)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def ear_clip(ring: Ring) -> list[tuple[int, int, int]]:
    """Triangulate a simple polygon (no holes). Returns index triples into ``ring``.

    Classic O(n²) ear clipping; unit outlines have tens of vertices, never thousands.
    Degenerate input (collinear leftovers) falls back to a fan so a GLB is always produced.
    """
    n = len(ring)
    if n < 3:
        return []
    idx = list(range(n))
    ccw = signed_area(ring) > 0
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        found = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = ring[i0], ring[i1], ring[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if (cross <= 1e-12) if ccw else (cross >= -1e-12):
                continue  # reflex or collinear vertex
            if any(_point_in_triangle(ring[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            del idx[k]
            found = True
            break
        if not found:
            break
    if len(idx) >= 3:
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
    if not ccw:
        tris = [(a, c, b) for a, b, c in tris]
    return tris


def extrude(ring_site: Ring, base: float, height: float) -> tuple[list[float], list[int]]:
    """Walls + caps for a polygon in the X/Z plane between ``base`` and ``base+height`` (Y up).

    Sheet y (down) maps to glTF +Z; polygon orientation is normalised so caps face outwards.
    """
    ring = list(ring_site)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    # in the X/Z plane with Y up, a ring that is CCW on the sheet (y down) is CW seen from above
    if signed_area(ring) > 0:
        ring.reverse()
    n = len(ring)
    top = base + height
    positions: list[float] = []
    for x, z in ring:
        positions += [x, base, z]
    for x, z in ring:
        positions += [x, top, z]
    indices: list[int] = []
    # walls: quad per edge, two triangles, outward facing for the (now) clockwise-on-sheet ring
    for i in range(n):
        j = (i + 1) % n
        b0, b1, t0, t1 = i, j, n + i, n + j
        indices += [b0, t0, b1, b1, t0, t1]
    cap = ear_clip(ring)  # ring is CW on sheet → triangles come back CW-on-sheet as well
    for a, b, c in cap:
        indices += [n + a, n + b, n + c]  # top cap faces +Y
        indices += [a, c, b]  # bottom cap faces −Y
    return positions, indices


# --- GLB assembly --------------------------------------------------------------------------
def _pad4(b: bytes, fill: bytes) -> bytes:
    return b + fill * ((4 - len(b) % 4) % 4)


class _GltfBuilder:
    def __init__(self) -> None:
        self.bin = bytearray()
        self.buffer_views: list[dict] = []
        self.accessors: list[dict] = []
        self.meshes: list[dict] = []
        self.nodes: list[dict] = []
        self.materials: list[dict] = []
        self._material_index: dict[str, int] = {}
        self.images: list[dict] = []
        self.textures: list[dict] = []
        self.triangles = 0

    def texture(self, data: bytes, mime: str) -> int:
        """Embed an image (JPEG or PNG: core glTF, no extension) and return its texture index."""
        view = self._view(data, 0)
        self.buffer_views[view].pop("target", None)
        self.images.append({"bufferView": view, "mimeType": mime})
        self.textures.append({"source": len(self.images) - 1, "sampler": 0})
        return len(self.textures) - 1

    def material_textured(self, unit_type: str, texture: int) -> int:
        key = f"{unit_type}#tex{texture}"
        if key not in self._material_index:
            colour = TYPE_COLOURS.get(unit_type, TYPE_COLOURS["apartment"])
            self._material_index[key] = len(self.materials)
            self.materials.append(
                {
                    "name": key,
                    "doubleSided": True,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [min(1.0, c * 1.1) for c in colour[:3]] + [1.0],
                        "baseColorTexture": {"index": texture, "texCoord": 0},
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.9,
                    },
                }
            )
        return self._material_index[key]

    def material(self, unit_type: str) -> int:
        if unit_type not in self._material_index:
            colour = TYPE_COLOURS.get(unit_type, TYPE_COLOURS["apartment"])
            self._material_index[unit_type] = len(self.materials)
            self.materials.append(
                {
                    "name": unit_type,
                    "doubleSided": True,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": colour,
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.9,
                    },
                }
            )
        return self._material_index[unit_type]

    def _view(self, data: bytes, target: int) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.buffer_views.append(
            {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data), "target": target}
        )
        self.bin += data
        return len(self.buffer_views) - 1

    def _indices(self, indices: list[int], count: int) -> int:
        if count < 65536:
            idx_bytes = struct.pack(f"<{len(indices)}H", *indices)
            ctype = 5123
        else:
            idx_bytes = struct.pack(f"<{len(indices)}I", *indices)
            ctype = 5125
        iv = self._view(idx_bytes, 34963)
        self.accessors.append(
            {
                "bufferView": iv,
                "componentType": ctype,
                "count": len(indices),
                "type": "SCALAR",
                "min": [min(indices)],
                "max": [max(indices)],
            }
        )
        self.triangles += len(indices) // 3
        return len(self.accessors) - 1

    def mesh(
        self,
        name: str,
        positions: list[float],
        indices: list[int],
        material: int,
        extras: dict,
        textured: list[tuple[list[int], int, list[float]]] | None = None,
    ) -> int:
        """One mesh per unit. ``textured`` adds primitives for the outer walls that carry a
        facade drawing: (indices, material, uv per vertex); each becomes its own primitive
        sharing the position accessor (three.js makes one child Mesh per primitive)."""
        count = len(positions) // 3
        pos_bytes = struct.pack(f"<{len(positions)}f", *positions)
        xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
        pv = self._view(pos_bytes, 34962)
        self.accessors.append(
            {
                "bufferView": pv,
                "componentType": 5126,
                "count": count,
                "type": "VEC3",
                "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
            }
        )
        pa = len(self.accessors) - 1
        primitives: list[dict] = []
        if indices:
            ia = self._indices(indices, count)
            primitives.append(
                {"attributes": {"POSITION": pa}, "indices": ia, "material": material, "mode": 4}
            )
        for t_indices, t_material, uvs in textured or []:
            if not t_indices:
                continue
            uv_view = self._view(struct.pack(f"<{len(uvs)}f", *uvs), 34962)
            self.accessors.append(
                {"bufferView": uv_view, "componentType": 5126, "count": count, "type": "VEC2"}
            )
            ta = len(self.accessors) - 1
            ia = self._indices(t_indices, count)
            primitives.append(
                {
                    "attributes": {"POSITION": pa, "TEXCOORD_0": ta},
                    "indices": ia,
                    "material": t_material,
                    "mode": 4,
                }
            )
        self.meshes.append({"name": name, "primitives": primitives, "extras": extras})
        return len(self.meshes) - 1

    def node(self, name: str, mesh: int | None, children: list[int], extras: dict) -> int:
        node: dict[str, Any] = {"name": name, "extras": extras}
        if mesh is not None:
            node["mesh"] = mesh
        if children:
            node["children"] = children
        self.nodes.append(node)
        return len(self.nodes) - 1

    def glb(self, root_nodes: list[int], root_extras: dict) -> bytes:
        gltf = {
            "asset": {"version": "2.0", "generator": GENERATOR},
            "scene": 0,
            "scenes": [{"nodes": root_nodes}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin)}],
            "extras": root_extras,
        }
        if self.images:
            gltf["images"] = self.images
            gltf["textures"] = self.textures
            # linear filtering, clamp: one drawing spans exactly one side
            gltf["samplers"] = [
                {"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}
            ]
        json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
        bin_chunk = _pad4(bytes(self.bin), b"\x00")
        total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
        return b"".join(
            [
                struct.pack("<4sII", b"glTF", 2, total),
                struct.pack("<II", len(json_chunk), 0x4E4F534A),
                json_chunk,
                struct.pack("<II", len(bin_chunk), 0x004E4942),
                bin_chunk,
            ]
        )


def build_glb(
    buildings: list[BuildingSolids], project_extras: dict[str, Any] | None = None
) -> tuple[bytes, dict[str, Any]]:
    """Assemble the project massing. Returns (glb bytes, stats)."""
    b = _GltfBuilder()
    roots: list[int] = []
    units = 0
    bbox_min = [math.inf] * 3
    bbox_max = [-math.inf] * 3
    for bld in buildings:
        children: list[int] = []
        facade_tex = _facade_textures(b, bld)
        for u in bld.units:
            ring_site = [bld.placement.apply(p) for p in u.ring_m]
            if len(ring_site) < 3:
                continue
            base = bld.placement.elevation + u.base_m
            positions, indices = extrude(ring_site, base, u.height_m)
            if not indices:
                continue
            extras = {
                "unit_id": u.unit_id,
                "code": u.code,
                "unit_type": u.unit_type,
                "building_code": u.building_code,
                "floor_level": u.floor_level,
                **u.extras,
            }
            textured: list[tuple[list[int], int, list[float]]] = []
            if facade_tex:
                indices, textured = _split_facade_walls(
                    b, u.unit_type, positions, indices, len(ring_site), facade_tex
                )
            m = b.mesh(u.code, positions, indices, b.material(u.unit_type), extras, textured)
            children.append(b.node(u.code, m, [], extras))
            units += 1
            for k in range(3):
                bbox_min[k] = min(bbox_min[k], min(positions[k::3]))
                bbox_max[k] = max(bbox_max[k], max(positions[k::3]))
        roots.append(
            b.node(
                bld.code,
                None,
                children,
                {"building_id": bld.building_id, "code": bld.code, "name": bld.name, **bld.extras},
            )
        )
    stats = {
        "buildings": len(buildings),
        "units": units,
        "triangles": b.triangles,
        "bbox": None if units == 0 else {"min": bbox_min, "max": bbox_max},
    }
    data = b.glb(
        roots,
        {
            "unitforma": {
                "kind": "massing_generated",
                "disclaimer": DISCLAIMER,
                **(project_extras or {}),
                **stats,
            }
        },
    )
    stats["bytes"] = len(data)
    return data, stats


def parse_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    """Minimal GLB reader (tests and the health check of generated models)."""
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("not a GLB 2.0 container")
    off = 12
    gltf: dict[str, Any] | None = None
    blob = b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8 : off + 8 + clen]
        if ctype == 0x4E4F534A:
            gltf = json.loads(chunk.decode())
        elif ctype == 0x004E4942:
            blob = chunk
        off += 8 + clen
    if gltf is None:
        raise ValueError("GLB without JSON chunk")
    return gltf, blob


# --- facades ---------------------------------------------------------------------------------
@dataclass
class _FacadeTextures:
    sides: list[Side]
    by_side: dict[int, tuple[int, bool]]  # side index → (texture index, flip)
    base: float
    top: float


def _facade_textures(b: _GltfBuilder, bld: BuildingSolids) -> _FacadeTextures | None:
    """Embed the building's facade drawings and describe the sides they belong to."""
    if not bld.facades:
        return None
    rect_local = bld.facade_rect or building_rectangle(facade_rings(bld.units))
    if rect_local is None:
        return None
    rect = [bld.placement.apply(p) for p in rect_local]  # order survives: no mirroring
    sides = rectangle_sides(rect)
    by_side: dict[int, tuple[int, bool]] = {}
    for f in bld.facades:
        if 0 <= f.side < 4 and f.image:
            by_side[f.side] = (b.texture(f.image, f.mime), f.flip)
    if not by_side:
        return None
    bases = [bld.placement.elevation + u.base_m for u in bld.units]
    tops = [bld.placement.elevation + u.base_m + u.height_m for u in bld.units]
    return _FacadeTextures(sides, by_side, min(bases), max(tops))


def _split_facade_walls(
    b: _GltfBuilder,
    unit_type: str,
    positions: list[float],
    indices: list[int],
    n: int,
    tex: _FacadeTextures,
    depth: float = FACADE_DEPTH_M,
) -> tuple[list[int], list[tuple[list[int], int, list[float]]]]:
    """Move the walls that face a textured side of the building rectangle (within ``depth``
    metres of it) into their own primitives with UVs: u is the wall's projection onto the side
    as a viewer outside sees it, v runs from the roof (0) to the ground (1) of the whole
    building, so one drawing spans the facade, balconies and recesses included."""
    wall_tris = indices[: 6 * n]  # extrude() emits the walls first, two triangles per edge
    rest = indices[6 * n :]
    plain: list[int] = []
    per_side: dict[int, list[int]] = {}
    uvs_by_side: dict[int, list[float]] = {}
    height = max(tex.top - tex.base, 1e-6)
    orientation = signed_area([(positions[3 * k], positions[3 * k + 2]) for k in range(n)])
    for i in range(n):
        j = (i + 1) % n
        p0 = (positions[3 * i], positions[3 * i + 2])
        p1 = (positions[3 * j], positions[3 * j + 2])
        hit: tuple[int, float, float] | None = None
        for side in tex.sides:
            if side.index not in tex.by_side:
                continue
            ts = _faces_side(p0, p1, orientation, side, depth)
            if ts is not None:
                hit = (side.index, ts[0], ts[1])
                break
        tris = wall_tris[6 * i : 6 * i + 6]
        if hit is None:
            plain += tris
            continue
        k, t0, t1 = hit
        flip = tex.by_side[k][1]
        uv = uvs_by_side.setdefault(k, [0.0] * (2 * (len(positions) // 3)))
        for vi, t in ((i, t0), (j, t1), (n + i, t0), (n + j, t1)):
            y = positions[3 * vi + 1]
            uv[2 * vi] = t if flip else 1.0 - t
            uv[2 * vi + 1] = (tex.top - y) / height
        per_side.setdefault(k, []).extend(tris)
    textured = [
        (tris, b.material_textured(unit_type, tex.by_side[k][0]), uvs_by_side[k])
        for k, tris in per_side.items()
    ]
    return plain + rest, textured
