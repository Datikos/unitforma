"""IFC ingestion (ADR-0006 Decision 4): storeys, spaces with footprints and quantities, and one
GLB per building with a node per ``IfcSpace`` and a merged node per element group and colour
(the architect's surface colours, ADR-0032).

Pure functions over bytes; IfcOpenShell (LGPL-3.0) is imported unmodified and only here, so the
api and light-worker images stay without it (the ``ifc`` extra lives in the heavy worker image).

Coordinates: IFC is Z-up in metres (after unit conversion); glTF is Y-up, so a point (x, y, z)
becomes (x, z, -y): north (+y) points away from the viewer like "down the sheet" in the massing
frame. Each GLB is in the IFC model's own coordinates shifted so its minimum corner sits at the
origin; placement on the site is the reviewer's step and is out of scope here.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from unitforma.geometry.massing import _GltfBuilder, parse_glb

log = structlog.get_logger()

MAX_GLB_BYTES = 15 * 1024 * 1024  # plan §7.3 budget for a detailed building model
DISCLAIMER = "Model from the architect's IFC export"
GENERATOR = "unitforma-ifc"

# element groups → colour (0–1 RGBA) for faces the file gives no colour; a class not listed is
# drawn as "other", building services and proxies as their own groups (see ``_group``)
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
    # the skins and pieces of exploded composites: cladding, railings (Archicad "Explode all")
    "IfcBuildingElementPart": [0.80, 0.80, 0.80, 1.0],
    "services": [0.71, 0.71, 0.76, 1.0],  # pipes, ducts, fittings, sanitary and electrical items
    "proxies": [0.82, 0.82, 0.84, 1.0],  # IfcBuildingElementProxy: furniture, cars, anything
    "other": [0.82, 0.82, 0.84, 1.0],
}
# at most this many of the file's own colours become materials (the most-drawn ones); faces in
# the others take their group's colour, so a file with a colour per element stays a small GLB
MAX_IFC_COLOURS = 48
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
# dropped first, in this order, when the GLB exceeds the budget: what a buyer never sees outside
# first, the envelope and its openings last (ADR-0032 Decision 3)
DROP_ORDER = (
    "services",
    "proxies",
    "IfcCovering",
    "other",
    "IfcMember",
    "IfcBuildingElementPart",
    "IfcRailing",
    "IfcPlate",
    "IfcDoor",
    "IfcWindow",
)


# translator options the reviewer needs to know about (ADR-0030 Decision 1); the names are the
# strings Archicad 29 writes into FILE_DESCRIPTION as "Option [Name: Value]"
EXPORT_OPTION_KEYS = {
    "elements to export": "elements_to_export",
    "ifc base quantities": "base_quantities",
    "material preservation": "material_preservation",
    "space containment": "space_containment",
}
_OPTION_RE = re.compile(r"Option \[([^:\]]+):\s*([^\]]*)\]")


def header_options(descriptions: list[str] | tuple[str, ...]) -> dict[str, str]:
    """``FILE_DESCRIPTION`` strings → the whitelisted translator options, values as written."""
    out: dict[str, str] = {}
    for text in descriptions:
        for name, value in _OPTION_RE.findall(str(text or "")):
            key = EXPORT_OPTION_KEYS.get(name.strip().lower())
            if key and key not in out:
                out[key] = value.strip()
    return out


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
    source: str = "ifc"  # ifc (an IfcSpace of the file) | plan (ADR-0030 Decision 4)
    floor_level: int | None = None  # the project's floor level when known (plan spaces)
    unit_id: Any | None = None  # plan spaces: the unit whose outline this is
    floor_id: Any | None = None


Geometry = tuple[list[float], list[int]]  # raw IFC coordinates (metres, Z up), triangle indices
Colour = tuple[float, float, float, float]  # RGBA 0–1 from the file's surface style


@dataclass
class ParsedIfc:
    """What :func:`parse_ifc` reads before packing: the caller may add plan spaces in between."""

    schema: str
    building_name: str | None
    application: str | None
    export_options: dict[str, str]
    storeys: list[Storey]
    spaces: list[Space]
    space_geo: list[Geometry]  # parallel to ``spaces``
    # element group → the file's colour (None: none given) → geometry drawn in it
    class_geo: dict[str, dict[Colour | None, list[Geometry]]]
    offset: tuple[float, float, float]
    elements_failed: int
    storey_slabs: dict[str, list[list[list[float]]]]  # storey GlobalId → slab footprint rings
    bounds: tuple[float, float, float, float]  # minx, miny, maxx, maxy of everything drawn
    unit_scale: float = 1.0  # file length unit → metres (attributes such as Elevation are raw)

    def bounds_ring(self) -> list[tuple[float, float]]:
        x0, y0, x1, y1 = self.bounds
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


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


def _shape(
    ifcopenshell: Any, settings: Any, product: Any
) -> tuple[list[float], list[int], list[Colour | None]]:
    """Vertices, triangle indices and each triangle's surface colour (None when unstyled)."""
    shape = ifcopenshell.geom.create_shape(settings, product)
    verts = list(shape.geometry.verts)
    faces = list(shape.geometry.faces)
    styles = [_rgba(m) for m in getattr(shape.geometry, "materials", None) or []]
    ids = list(getattr(shape.geometry, "material_ids", None) or [])
    colours = [
        styles[ids[t]] if t < len(ids) and 0 <= ids[t] < len(styles) else None
        for t in range(len(faces) // 3)
    ]
    return verts, faces, colours


def _rgba(style: Any) -> Colour | None:
    """The surface colour of a tessellator style: ``IfcSurfaceStyleRendering.SurfaceColour`` and
    1 − its transparency. The style's ``diffuse`` is that colour times the file's diffuse factor
    (Archicad writes 0.4: the orange 0.93/0.31/0.07 becomes 0.38/0.13/0.03), so it is not used.
    An unstyled element gets the tessellator's default style, named after its class with instance
    id 0: that is no colour of the file's (None)."""
    iid = getattr(style, "instance_id", None)
    try:
        iid = iid() if callable(iid) else iid
    except Exception:  # noqa: BLE001 - an older binding without the accessor: trust the colour
        iid = 1
    if not iid:
        return None
    c = getattr(style, "surface", None)
    if c is None:
        return None
    try:
        rgb = [float(c.r()), float(c.g()), float(c.b())]
    except (AttributeError, TypeError, ValueError):
        try:
            rgb = [float(v) for v in c][:3]
        except (TypeError, ValueError):
            return None
    if len(rgb) != 3 or any(v != v for v in rgb):  # NaN: a style without a colour
        return None
    t = getattr(style, "transparency", 0.0)
    t = float(t) if isinstance(t, (int, float)) and t == t else 0.0
    return (*(round(min(max(v, 0.0), 1.0), 2) for v in rgb), round(1.0 - min(max(t, 0.0), 1.0), 2))


def _group(product: Any) -> str:
    """The draw group of an element: its class when styled in ``CLASS_STYLE``, building services
    (``IfcDistributionElement`` and below, IFC2X3 and IFC4) and proxies apart, else "other"."""
    cls = product.is_a()
    if cls in CLASS_STYLE:
        return cls
    if product.is_a("IfcDistributionElement"):
        return "services"
    if product.is_a("IfcBuildingElementProxy"):
        return "proxies"
    return "other"


def _by_colour(
    verts: list[float], faces: list[int], colours: list[Colour | None]
) -> list[tuple[Colour | None, Geometry]]:
    """One element's triangles split by colour, each part with only the vertices it uses."""
    if len(set(colours)) <= 1:
        return [(colours[0] if colours else None, (verts, faces))]
    parts: dict[Colour | None, tuple[list[float], list[int], dict[int, int]]] = {}
    for t, colour in enumerate(colours):
        pv, pf, index = parts.setdefault(colour, ([], [], {}))
        for v in faces[3 * t : 3 * t + 3]:
            if v not in index:
                index[v] = len(pv) // 3
                pv.extend(verts[3 * v : 3 * v + 3])
            pf.append(index[v])
    return [(colour, (pv, pf)) for colour, (pv, pf, _i) in parts.items()]


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


def parse_ifc(data: bytes, *, deflection: float = 0.03) -> ParsedIfc:
    """Parse and tessellate one IFC file. Raises :class:`IfcError` for unusable input."""
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
    # geometry comes back in metres from the tessellator; attributes such as Elevation are in
    # the file's own length unit (an Archicad export says millimetres: -3000, 3200, ...)
    try:
        from ifcopenshell.util import unit as ifc_unit

        unit_scale = float(ifc_unit.calculate_unit_scale(f)) or 1.0
    except Exception:  # noqa: BLE001 - no unit assignment: assume metres (ADR-0006 E7)
        unit_scale = 1.0
    storeys_raw = sorted(
        f.by_type("IfcBuildingStorey"),
        key=lambda s: (s.Elevation is None, float(s.Elevation or 0.0)),
    )
    storeys = [
        Storey(
            global_id=s.GlobalId,
            name=s.Name or f"Storey {i + 1}",
            elevation_m=(
                round(float(s.Elevation) * unit_scale, 3) if s.Elevation is not None else None
            ),
            index=i,
        )
        for i, s in enumerate(storeys_raw)
    ]
    storey_by_gid = {s.global_id: s for s in storeys}
    buildings = f.by_type("IfcBuilding")
    building_name = (buildings[0].Name or buildings[0].LongName) if buildings else None
    apps = f.by_type("IfcApplication")
    # the authoring tool, so the reviewer can tell the architect which export setting to change
    application = (getattr(apps[0], "ApplicationFullName", None) or None) if apps else None
    export_options: dict[str, str] = {}
    try:
        header = f.header
        export_options = header_options(list(header.file_description.description))
        if not application:
            application = str(header.file_name.originating_system or "") or None
    except Exception:  # noqa: BLE001 - a header is optional information
        export_options = {}
    settings = _settings(ifcopenshell, deflection)

    # first pass: tessellate everything we draw, remember raw IFC coordinates
    space_products: list[tuple[Any, list[float], list[int]]] = []
    class_geo: dict[str, dict[Colour | None, list[Geometry]]] = {}
    storey_slabs: dict[str, list[list[list[float]]]] = {}
    failed = 0
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for product in f.by_type("IfcProduct"):
        if not getattr(product, "Representation", None):
            continue
        cls = product.is_a()
        if cls in SKIP_CLASSES and cls != "IfcSpace":
            continue
        try:
            verts, faces, colours = _shape(ifcopenshell, settings, product)
        except Exception:  # noqa: BLE001 - one bad element must not stop the model
            failed += 1
            continue
        if not verts or not faces:
            continue
        for i in range(3):
            mins[i] = min(mins[i], min(verts[i::3]))
            maxs[i] = max(maxs[i], max(verts[i::3]))
        if cls == "IfcSpace":
            space_products.append((product, verts, faces))
        else:
            by_colour = class_geo.setdefault(_group(product), {})
            for colour, part in _by_colour(verts, faces, colours):
                by_colour.setdefault(colour, []).append(part)
            if cls == "IfcSlab":
                # the storey's footprint for the plan fit (ADR-0030 Decision 4)
                st = _storey_of(ifcopenshell, product)
                ring = _footprint(verts, faces) if st is not None else None
                if st is not None and ring:
                    storey_slabs.setdefault(st.GlobalId, []).append(ring)
    if not space_products and not class_geo:
        raise IfcError("The IFC file holds no geometry to draw")
    offset = tuple(0.0 if m == float("inf") else m for m in mins)
    bounds = (
        offset[0],
        offset[1],
        maxs[0] if maxs[0] != float("-inf") else offset[0],
        maxs[1] if maxs[1] != float("-inf") else offset[1],
    )

    spaces: list[Space] = []
    space_geo: list[Geometry] = []
    for product, verts, faces in space_products:
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
        space_geo.append((verts, faces))
    return ParsedIfc(
        schema=f.schema,
        building_name=building_name,
        application=application,
        export_options=export_options,
        storeys=storeys,
        spaces=spaces,
        space_geo=space_geo,
        class_geo=class_geo,
        offset=offset,  # type: ignore[arg-type]
        elements_failed=failed,
        storey_slabs=storey_slabs,
        bounds=bounds,
        unit_scale=unit_scale,
    )


def prism(ring: list[tuple[float, float]], z0: float, z1: float) -> Geometry:
    """A flat extrusion of an XY ring between two heights, raw IFC coordinates."""
    from unitforma.geometry.massing import ear_clip, signed_area

    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if signed_area(pts) < 0:
        pts.reverse()
    n = len(pts)
    verts: list[float] = []
    for x, y in pts:
        verts += [x, y, z0]
    for x, y in pts:
        verts += [x, y, z1]
    faces: list[int] = []
    for i in range(n):
        j = (i + 1) % n
        faces += [i, j, n + i, j, n + j, n + i]
    for a, b, c in ear_clip(pts):
        faces += [n + a, n + b, n + c, a, c, b]
    return verts, faces


def pack_ifc(
    parsed: ParsedIfc,
    *,
    budget: int = MAX_GLB_BYTES,
    extra_spaces: list[tuple[Space, list[float], list[int]]] = (),  # type: ignore[assignment]
) -> IfcModel:
    """Pack a parsed file (plus spaces the caller derived, ADR-0030) into a GLB within ``budget``,
    dropping element classes in ``DROP_ORDER`` until it fits; spaces are never dropped."""
    spaces = list(parsed.spaces) + [sp for sp, _v, _f in extra_spaces]
    space_geo = list(parsed.space_geo) + [(v, fc) for _sp, v, fc in extra_spaces]
    dropped: list[str] = []
    while True:
        glb, build_stats = _pack(
            space_geo, spaces, parsed.class_geo, parsed.offset, parsed.building_name, dropped
        )
        if len(glb) <= budget:
            break
        candidate = next(
            (c for c in DROP_ORDER if c in parsed.class_geo and c not in dropped), None
        )
        if candidate is None:
            raise IfcError(
                f"Model is {len(glb) // (1024 * 1024)} MB after dropping finishes; the budget is "
                f"{budget // (1024 * 1024)} MB. Export without furniture or with less detail."
            )
        dropped.append(candidate)
    stats = {
        **build_stats,
        "schema": parsed.schema,
        "application": parsed.application,
        "export_options": parsed.export_options,
        "storeys": len(parsed.storeys),
        "spaces": len(spaces),
        "spaces_plan": sum(1 for sp in spaces if sp.source == "plan"),
        "elements_failed": parsed.elements_failed,
        "classes_dropped": dropped,
        "offset_m": [round(o, 3) for o in parsed.offset],
        "compression": "none",
    }
    return IfcModel(
        schema=parsed.schema,
        building_name=parsed.building_name,
        storeys=parsed.storeys,
        spaces=spaces,
        glb=glb,
        stats=stats,
    )


def read_ifc(data: bytes, *, deflection: float = 0.03, budget: int = MAX_GLB_BYTES) -> IfcModel:
    """Parse, tessellate and pack one IFC file. Raises :class:`IfcError` for unusable input."""
    return pack_ifc(parse_ifc(data, deflection=deflection), budget=budget)


def _pack(
    space_geo: list[Geometry],
    spaces: list[Space],
    class_geo: dict[str, dict[Colour | None, list[Geometry]]],
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
    for (verts, faces), sp in zip(space_geo, spaces, strict=True):
        extras = {
            "ifc_global_id": sp.global_id,
            "code": sp.name or sp.global_id,
            "unit_id": f"space:{sp.global_id}",
            "unit_type": "space",
            # the project's floor level when known; the relink fixes the storey index otherwise
            "floor_level": (
                sp.floor_level
                if sp.floor_level is not None
                else (sp.storey.index if sp.storey else 0)
            ),
            "storey": sp.storey.name if sp.storey else None,
            "lifecycle_status": "space",
            "source": sp.source,
        }
        m = b.mesh(
            sp.name or sp.global_id,
            _to_gltf(verts, offset),
            faces,
            material("space", SPACE_COLOUR),
            extras,
        )
        children.append(b.node(sp.name or sp.global_id, m, [], extras))
    kept = _kept_colours(class_geo, dropped)
    for cls, by_colour in sorted(class_geo.items()):
        if cls in dropped:
            continue
        groups: dict[Colour | None, list[Geometry]] = {}
        for colour, parts in by_colour.items():
            groups.setdefault(colour if colour in kept else None, []).extend(parts)
        order = sorted(groups.items(), key=lambda kv: (kv[0] is not None, kv[0] or ()))
        for colour, parts in order:
            positions: list[float] = []
            indices: list[int] = []
            for verts, faces in parts:
                base = len(positions) // 3
                positions.extend(_to_gltf(verts, offset))
                indices.extend(i + base for i in faces)
            if not indices:
                continue
            if colour is None:
                name, mat = cls, material(cls, CLASS_STYLE[cls])
            else:
                hexa = _hex(colour)
                name, mat = f"{cls} {hexa}", material(hexa, list(colour))
            extras: dict[str, Any] = {"ifc_class": cls, "elements": len(parts)}
            if colour is not None:
                extras["colour"] = _hex(colour)
            m = b.mesh(name, positions, indices, mat, extras)
            children.append(b.node(name, m, [], extras))
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
    return glb, {
        "bytes": len(glb),
        "triangles": b.triangles,
        "meshes": len(b.meshes),
        "ifc_colours": len(kept),
    }


def _kept_colours(
    class_geo: dict[str, dict[Colour | None, list[Geometry]]], dropped: list[str]
) -> set[Colour]:
    """The file's colours drawn as their own materials: the ``MAX_IFC_COLOURS`` most-drawn."""
    triangles: dict[Colour, int] = {}
    for cls, by_colour in class_geo.items():
        if cls in dropped:
            continue
        for colour, parts in by_colour.items():
            if colour is not None:
                triangles[colour] = triangles.get(colour, 0) + sum(len(f) for _v, f in parts)
    ranked = sorted(triangles, key=lambda c: -triangles[c])
    return set(ranked[:MAX_IFC_COLOURS])


def _hex(colour: Colour) -> str:
    """#RRGGBB, with the opacity appended for glass (#F0F7F2@0.31)."""
    r, g, b, a = colour
    text = "#" + "".join(f"{round(v * 255):02X}" for v in (r, g, b))
    return text if a >= 1.0 else f"{text}@{a:.2f}"


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


def compress_glb(data: bytes, timeout_s: int = 300) -> tuple[bytes, str]:
    """Draco-compress a GLB with the ``gltf-transform`` CLI when it is on the PATH (ADR-0006 C2a).

    Returns ``(glb, "draco")``, or the input unchanged with ``"none"`` when the CLI is absent
    (api, light worker, tests outside the heavy image), fails, times out, or does not shrink the
    file. Node and mesh ``extras`` survive: the CLI rewrites accessors and buffer views only, so
    :func:`relink_glb` keeps working on the result.
    """
    exe = shutil.which("gltf-transform")
    if exe is None:
        return data, "none"
    with tempfile.TemporaryDirectory(prefix="uf-draco-") as d:
        src, dst = Path(d) / "in.glb", Path(d) / "out.glb"
        src.write_bytes(data)
        try:
            subprocess.run(  # noqa: S603 - fixed executable, temp-file arguments
                [exe, "draco", str(src), str(dst), "--method", "edgebreaker"],
                check=True,
                capture_output=True,
                timeout=timeout_s,
            )
            out = dst.read_bytes()
        except (subprocess.SubprocessError, OSError) as e:
            detail = getattr(e, "stderr", b"") or b""
            log.warning(
                "ifc.draco_failed",
                error=str(e)[:200],
                stderr=detail[-300:].decode(errors="replace"),
            )
            return data, "none"
    if len(out) >= len(data):
        return data, "none"
    return out, "draco"
