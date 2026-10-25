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
class BuildingSolids:
    building_id: str
    code: str
    name: str | None
    placement: Placement
    units: list[UnitSolid]
    extras: dict[str, Any] = field(default_factory=dict)


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
        self.triangles = 0

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

    def mesh(
        self, name: str, positions: list[float], indices: list[int], material: int, extras: dict
    ) -> int:
        count = len(positions) // 3
        pos_bytes = struct.pack(f"<{len(positions)}f", *positions)
        if count < 65536:
            idx_bytes = struct.pack(f"<{len(indices)}H", *indices)
            ctype = 5123
        else:
            idx_bytes = struct.pack(f"<{len(indices)}I", *indices)
            ctype = 5125
        xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
        pv = self._view(pos_bytes, 34962)
        iv = self._view(idx_bytes, 34963)
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
        ia = len(self.accessors) - 1
        self.meshes.append(
            {
                "name": name,
                "primitives": [
                    {"attributes": {"POSITION": pa}, "indices": ia, "material": material, "mode": 4}
                ],
                "extras": extras,
            }
        )
        self.triangles += len(indices) // 3
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
            m = b.mesh(u.code, positions, indices, b.material(u.unit_type), extras)
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
