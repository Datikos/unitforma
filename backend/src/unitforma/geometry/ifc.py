"""IFC ingestion (ADR-0006 Decision 4): storeys, spaces with footprints and quantities, and one
GLB per building with a node per ``IfcSpace`` and a merged node per element class.

Pure functions over bytes; IfcOpenShell (LGPL-3.0) is imported unmodified and only here, so the
api and light-worker images stay without it (the ``ifc`` extra lives in the heavy worker image).

Coordinates: IFC is Z-up in metres (after unit conversion); glTF is Y-up, so a point (x, y, z)
becomes (x, z, -y): north (+y) points away from the viewer like "down the sheet" in the massing
frame. Each GLB is in the IFC model's own coordinates shifted so its minimum corner sits at the
origin; placement on the site is the reviewer's step and is out of scope here.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any

from unitforma.geometry.massing import _GltfBuilder, parse_glb

MAX_GLB_BYTES = 15 * 1024 * 1024  # plan §7.3 budget for a detailed building model
DISCLAIMER = "Model from the architect's IFC export"
GENERATOR = "unitforma-ifc"

# element classes → draw order and colour (0–1 RGBA); classes not listed are drawn as "other"
CLASS_STYLE: dict[str, list[float]] = {
    "IfcSlab": [0.80, 0.80, 0.82, 1.0],
    "IfcWall": [0.93, 0.93, 0.90, 1.0],
    "IfcWallStandardCase": [0.93, 0.93, 0.90, 1.0],
    "IfcColumn": [0.75, 0.75, 0.78, 1.0],
    "IfcBeam": [0.75, 0.75, 0.78, 1.0],
    "IfcRoof": [0.70, 0.55, 0.50, 1.0],
    "IfcStair": [0.78, 0.76, 0.72, 1.0],
    "IfcStairFlight": [0.78, 0.76, 0.72, 1.0],
    "IfcRailing": [0.55, 0.57, 0.60, 1.0],
    "IfcWindow": [0.55, 0.75, 0.95, 0.45],
    "IfcCurtainWall": [0.55, 0.75, 0.95, 0.45],
    "IfcPlate": [0.55, 0.75, 0.95, 0.45],
    "IfcDoor": [0.60, 0.45, 0.30, 1.0],
    "IfcCovering": [0.90, 0.90, 0.88, 1.0],
    "IfcFooting": [0.65, 0.65, 0.65, 1.0],
    "IfcMember": [0.72, 0.72, 0.74, 1.0],
    "other": [0.82, 0.82, 0.84, 1.0],
}
SPACE_COLOUR = [0.86, 0.88, 0.92, 0.9]
# never drawn: openings cut the walls already; furniture and fittings do not describe the building
SKIP_CLASSES = frozenset(
    {
        "IfcOpeningElement",
        "IfcFurnishingElement",
        "IfcFurniture",
        "IfcSystemFurnitureElement",
        "IfcAnnotation",
        "IfcGrid",
        "IfcSpace",
        "IfcSite",
        "IfcBuilding",
        "IfcBuildingStorey",
        "IfcProject",
    }
)
# dropped first, in this order, when the GLB exceeds the budget
DROP_ORDER = ("IfcCovering", "IfcRailing", "IfcMember", "other", "IfcPlate", "IfcDoor", "IfcWindow")


class IfcError(ValueError):
    """The file is not an IFC this reader can use; the message is shown to the reviewer."""


@dataclass
class Storey:
    global_id: str
    name: str
    elevation_m: float | None
    index: int


@dataclass
class Space:
    global_id: str
    name: str | None
    long_name: str | None
    storey: Storey | None
    footprint_m: list[list[float]] | None  # XY ring in IFC metres
    areas: dict[str, float] = field(default_factory=dict)
    triangles: int = 0


@dataclass
class IfcModel:
    schema: str
    building_name: str | None
    storeys: list[Storey]
    spaces: list[Space]
    glb: bytes
    stats: dict[str, Any]


def _settings(ifcopenshell: Any, deflection: float) -> Any:
    settings = ifcopenshell.geom.settings()
    for key, value in (("use-world-coords", True), ("mesher-linear-deflection", deflection)):
        try:
            settings.set(key, value)
        except Exception:  # noqa: BLE001 - 0.7 API names below
            try:
                attr = {
                    "use-world-coords": "USE_WORLD_COORDS",
                }.get(key)
                if attr:
                    settings.set(getattr(settings, attr), value)
                elif key == "mesher-linear-deflection":
                    settings.set_deflection_tolerance(value)
            except Exception:  # noqa: BLE001, S110 - best effort; defaults still produce geometry
                pass  # noqa: S110 - defaults still produce geometry
    return settings


def _shape(ifcopenshell: Any, settings: Any, product: Any) -> tuple[list[float], list[int]]:
    shape = ifcopenshell.geom.create_shape(settings, product)
    verts = list(shape.geometry.verts)
    faces = list(shape.geometry.faces)
    return verts, faces


def _to_gltf(verts: list[float], offset: tuple[float, float, float]) -> list[float]:
    """IFC (x, y, z) Z-up → glTF (x, z, -y) Y-up, shifted by the model offset."""
    out: list[float] = []
    ox, oy, oz = offset
    for i in range(0, len(verts), 3):
        x, y, z = verts[i] - ox, verts[i + 1] - oy, verts[i + 2] - oz
        out.extend((round(x, 4), round(z, 4), round(-y, 4)))
    return out


def _footprint(verts: list[float], faces: list[int]) -> list[list[float]] | None:
    """Outline of a space on the XY plane: union of its triangles projected to the ground."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    tris = []
    for i in range(0, len(faces), 3):
        pts = [(verts[3 * faces[i + k]], verts[3 * faces[i + k] + 1]) for k in range(3)]
        try:
            poly = Polygon(pts)
        except (ValueError, TypeError):
            continue
        if poly.area > 1e-6:
            tris.append(poly)
    if not tris:
        return None
    union = unary_union(tris).buffer(0)
    if union.geom_type == "MultiPolygon":
        union = max(union.geoms, key=lambda g: g.area)
    if union.is_empty or union.geom_type != "Polygon":
        return None
    simple = union.simplify(0.02, preserve_topology=True)
    ring = list(simple.exterior.coords)[:-1]
    return [[round(float(x), 3), round(float(y), 3)] for x, y in ring] if len(ring) >= 3 else None


def _quantities(ifcopenshell: Any, space: Any) -> dict[str, float]:
    from ifcopenshell.util import element as ue

    out: dict[str, float] = {}
    try:
        qtos = ue.get_psets(space, qtos_only=True)
    except Exception:  # noqa: BLE001
        return out
    for props in qtos.values():
        for key, target in (
            ("NetFloorArea", "net_floor_area"),
            ("GrossFloorArea", "gross_floor_area"),
            ("NetVolume", "net_volume"),
            ("Height", "height"),
        ):
            v = props.get(key)
            if isinstance(v, (int, float)) and target not in out:
                out[target] = round(float(v), 2)
    return out


def _storey_of(ifcopenshell: Any, product: Any) -> Any:
    from ifcopenshell.util import element as ue

    c = None
    for getter in (ue.get_container, ue.get_aggregate):
        try:
            c = getter(product)
        except Exception:  # noqa: BLE001
            c = None
        if c is not None:
            break
    steps = 0
    while c is not None and not c.is_a("IfcBuildingStorey") and steps < 8:
        steps += 1
        try:
            c = ue.get_aggregate(c) or ue.get_container(c)
        except Exception:  # noqa: BLE001
            return None
    return c if c is not None and c.is_a("IfcBuildingStorey") else None


def read_ifc(data: bytes, *, deflection: float = 0.03, budget: int = MAX_GLB_BYTES) -> IfcModel:
    """Parse, tessellate and pack one IFC file. Raises :class:`IfcError` for unusable input."""
    try:
        import ifcopenshell
        import ifcopenshell.geom
    except ImportError as e:  # pragma: no cover - the api image has no IFC extra
        raise IfcError("IFC processing is not installed in this worker image") from e
    text = data.decode("utf-8", errors="replace")
    if not text.lstrip().upper().startswith("ISO-10303-21"):
        raise IfcError("Not an IFC STEP file")
    try:
        f = ifcopenshell.file.from_string(text)
    except Exception as e:  # noqa: BLE001
        raise IfcError(f"IFC could not be read: {e}"[:300]) from e
    storeys_raw = sorted(
        f.by_type("IfcBuildingStorey"),
        key=lambda s: (s.Elevation is None, float(s.Elevation or 0.0)),
    )
    storeys = [
        Storey(
            global_id=s.GlobalId,
            name=s.Name or f"Storey {i + 1}",
            elevation_m=float(s.Elevation) if s.Elevation is not None else None,
            index=i,
        )
        for i, s in enumerate(storeys_raw)
    ]
    storey_by_gid = {s.global_id: s for s in storeys}
    buildings = f.by_type("IfcBuilding")
    building_name = (buildings[0].Name or buildings[0].LongName) if buildings else None
    settings = _settings(ifcopenshell, deflection)

    # first pass: tessellate everything we draw, remember raw IFC coordinates
    space_geo: list[tuple[Any, list[float], list[int]]] = []
    class_geo: dict[str, list[tuple[list[float], list[int]]]] = {}
    failed = 0
    mins = [float("inf")] * 3
    for product in f.by_type("IfcProduct"):
        if not getattr(product, "Representation", None):
            continue
        cls = product.is_a()
        if cls in SKIP_CLASSES and cls != "IfcSpace":
            continue
        try:
            verts, faces = _shape(ifcopenshell, settings, product)
        except Exception:  # noqa: BLE001 - one bad element must not stop the model
            failed += 1
            continue
        if not verts or not faces:
            continue
        for i in range(3):
            mins[i] = min(mins[i], min(verts[i::3]))
        if cls == "IfcSpace":
            space_geo.append((product, verts, faces))
        else:
            key = cls if cls in CLASS_STYLE else "other"
            class_geo.setdefault(key, []).append((verts, faces))
    if not space_geo and not class_geo:
        raise IfcError("The IFC file holds no geometry to draw")
    offset = tuple(0.0 if m == float("inf") else m for m in mins)

    spaces: list[Space] = []
    for product, verts, faces in space_geo:
        st = _storey_of(ifcopenshell, product)
        spaces.append(
            Space(
                global_id=product.GlobalId,
                name=product.Name,
                long_name=getattr(product, "LongName", None),
                storey=storey_by_gid.get(st.GlobalId) if st is not None else None,
                footprint_m=_footprint(verts, faces),
                areas=_quantities(ifcopenshell, product),
                triangles=len(faces) // 3,
            )
        )

    dropped: list[str] = []
    while True:
        glb, build_stats = _pack(space_geo, spaces, class_geo, offset, building_name, dropped)
        if len(glb) <= budget:
            break
        candidate = next((c for c in DROP_ORDER if c in class_geo and c not in dropped), None)
        if candidate is None:
            raise IfcError(
                f"Model is {len(glb) // (1024 * 1024)} MB after dropping finishes; the budget is "
                f"{budget // (1024 * 1024)} MB. Export without furniture or with less detail."
            )
        dropped.append(candidate)
    stats = {
        **build_stats,
        "schema": f.schema,
        "storeys": len(storeys),
        "spaces": len(spaces),
        "elements_failed": failed,
        "classes_dropped": dropped,
        "offset_m": [round(o, 3) for o in offset],
        "compression": "none",
    }
    return IfcModel(
        schema=f.schema,
        building_name=building_name,
        storeys=storeys,
        spaces=spaces,
        glb=glb,
        stats=stats,
    )


def _pack(
    space_geo: list[tuple[Any, list[float], list[int]]],
    spaces: list[Space],
    class_geo: dict[str, list[tuple[list[float], list[int]]]],
    offset: tuple[float, float, float],
    building_name: str | None,
    dropped: list[str],
) -> tuple[bytes, dict[str, Any]]:
    b = _GltfBuilder()

    def material(name: str, rgba: list[float]) -> int:
        if name not in b._material_index:  # noqa: SLF001 - same module family
            b._material_index[name] = len(b.materials)  # noqa: SLF001
            mat: dict[str, Any] = {
                "name": name,
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": rgba,
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.85,
                },
            }
            if rgba[3] < 1.0:
                mat["alphaMode"] = "BLEND"
            b.materials.append(mat)
        return b._material_index[name]  # noqa: SLF001

    children: list[int] = []
    for (_product, verts, faces), sp in zip(space_geo, spaces, strict=True):
        extras = {
            "ifc_global_id": sp.global_id,
            "code": sp.name or sp.global_id,
            "unit_id": f"space:{sp.global_id}",
            "unit_type": "space",
            "floor_level": sp.storey.index if sp.storey else 0,
            "storey": sp.storey.name if sp.storey else None,
            "lifecycle_status": "space",
        }
        m = b.mesh(
            sp.name or sp.global_id,
            _to_gltf(verts, offset),
            faces,
            material("space", SPACE_COLOUR),
            extras,
        )
        children.append(b.node(sp.name or sp.global_id, m, [], extras))
    for cls, parts in sorted(class_geo.items()):
        if cls in dropped:
            continue
        positions: list[float] = []
        indices: list[int] = []
        for verts, faces in parts:
            base = len(positions) // 3
            positions.extend(_to_gltf(verts, offset))
            indices.extend(i + base for i in faces)
        if not indices:
            continue
        extras = {"ifc_class": cls, "elements": len(parts)}
        m = b.mesh(cls, positions, indices, material(cls, CLASS_STYLE[cls]), extras)
        children.append(b.node(cls, m, [], extras))
    root = b.node(building_name or "Building", None, children, {"building_name": building_name})
    glb = b.glb(
        [root],
        {
            "unitforma": {
                "kind": "ifc",
                "disclaimer": DISCLAIMER,
                "generator": GENERATOR,
                "spaces": len(spaces),
            }
        },
    )
    return glb, {"bytes": len(glb), "triangles": b.triangles, "meshes": len(b.meshes)}


def relink_glb(data: bytes, spaces: dict[str, dict[str, Any] | str | None]) -> bytes:
    """Rewrite the extras of space nodes without touching the geometry.

    ``spaces`` maps an ``IfcSpace`` GlobalId to what the viewer should read: a dict with
    ``unit_id`` (the unit's id once confirmed), ``code`` (the unit's code, what the portal routes
    to) and ``floor_level`` (the matched floor's level, what floor isolation compares); a bare
    string is a unit id; ``None`` removes ``unit_id`` so the space is not pickable (unconfirmed or
    unlisted spaces in the published copy). Spaces not in the map fall back to ``space:<gid>``."""
    gltf, blob = parse_glb(data)
    for coll in (gltf.get("nodes", []), gltf.get("meshes", [])):
        for item in coll:
            ex = item.get("extras") or {}
            gid = ex.get("ifc_global_id")
            if not gid:
                continue
            if gid in spaces:
                target = spaces[gid]
                if target is None:
                    ex.pop("unit_id", None)
                elif isinstance(target, str):
                    ex["unit_id"] = target
                else:
                    if target.get("unit_id") is None:
                        ex["unit_id"] = f"space:{gid}"
                    else:
                        ex["unit_id"] = str(target["unit_id"])
                    for key in ("code", "floor_level"):
                        if target.get(key) is not None:
                            ex[key] = target[key]
            else:
                ex["unit_id"] = f"space:{gid}"
            item["extras"] = ex
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode()
    while len(json_chunk) % 4:
        json_chunk += b" "
    bin_chunk = bytes(blob)
    while len(bin_chunk) % 4:
        bin_chunk += b"\x00"
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
