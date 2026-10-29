# ADR-0032: The architect's colours on the IFC model; building services dropped before the envelope

- **Status:** accepted (2026-10-27, "1"; implemented 2026-10-27)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (building model budget), §13.2 (IFC row), ADR-0006 Decision 4 and Phase C (IFC to one GLB per building), ADR-0030 (plan spaces on a zoneless IFC)

## Context

The owner's question on 2026-10-27, after uploading five renders of N4 (public `render` documents,
1600 × 1200 JPEGs): "how to make like this on the 3D model". The renders show a grey building with
orange vertical panels, dark balcony railings and glazing. The portal's model of N4 (published v2,
the architect's IFC with 122 plan spaces) showed none of that. What the code and the file said:

- `geometry/ifc.py` merges every element of a class into one mesh and paints it with a fixed
  `CLASS_STYLE` colour (walls 0.93/0.93/0.90, windows light blue at 0.45 opacity, anything not
  listed "other" grey). The file's own styles were never read.
- The file carries them. Read with ifcopenshell 0.9.0 on 2026-10-27, `IfcSurfaceStyleRendering`
  colours by class: orange 0.93/0.31/0.07 on 417 `IfcSlab` (the panels are modelled as slabs) and
  20 `IfcWall`; grey 0.66 on 999 walls, 306 columns and 118 beams; dark 0.30/0.31/0.33 on 4,099
  `IfcBuildingElementPart` of material "Iron" (the railings, exploded by the export's
  "Material Preservation: Explode all"); glass 0.94/0.97/0.95 at transparency 0.69 on windows and
  glazed doors. The tessellator returns each style with a `surface` colour (that value) and a
  `diffuse` colour, which is the surface colour times the file's diffuse factor (0.4 in Archicad's
  export: the orange reads 0.38/0.13/0.03). An unstyled element gets a default style named after
  its class with instance id 0.
- Triangles per group at 0.03 m deflection (52 s with the iterator, 103 s in `parse_ifc` on a Mac):
  building services 1,002,792 (504 `IfcDistributionFlowElement`, 94 fittings, 188 segments),
  `IfcBuildingElementPart` 230,604, doors 170,928, 9 `IfcBuildingElementProxy` "FU - 027"
  (furniture) 136,944, walls 31,689, slabs 12,946, windows 7,412. The parts, services and proxies
  were all "other", which `DROP_ORDER` dropped to fit the 15 MB raw budget: the railings went with
  the pipes. The model shipped at 4.38 MB raw, 0.44 MB after Draco, 246,861 triangles.
- The viewer (`viewer-3d/massing-viewer.ts`) keeps each mesh's GLB colour for every node that is not
  a unit; only unit nodes are tinted. The admin 3D page lists `stats.classes_dropped` in a chip and
  its export advice said the skins "are the first class dropped".
- The 15 MB budget applies to the raw GLB on purpose (the comment in `ifc_service`: it bounds what
  the browser decodes), so the fix is to spend it on what a buyer sees, not to raise it.

## Decision

1. **Each face takes the file's surface colour.** `_shape` returns a colour per triangle from the
   tessellator's styles: `IfcSurfaceStyleRendering.SurfaceColour` and alpha = 1 − transparency,
   rounded to 0.01; the diffuse colour is not used; a default style (instance id 0) is no colour,
   and such faces keep their group's `CLASS_STYLE` colour.
2. **One mesh per element group and colour.** `ParsedIfc.class_geo` becomes group → colour →
   geometry, an element split by colour with only the vertices each part uses. A coloured mesh is
   named `<group> #RRGGBB` (`#RRGGBB@0.31` for glass), its node extras carry `ifc_class`, `elements`
   and `colour`, its material is the colour (alpha below 1: `BLEND`). At most
   `MAX_IFC_COLOURS = 48` colours become materials, the most-drawn by triangle count; faces in the
   others take the group colour. `stats.ifc_colours` counts the colours kept.
3. **Building services and proxies are groups of their own and are dropped first.** `_group`:
   a class in `CLASS_STYLE` is its own group (now including `IfcBuildingElementPart`), an
   `IfcDistributionElement` or any subtype (IFC2X3 and IFC4) is `services`, an
   `IfcBuildingElementProxy` is `proxies`, anything else `other`. `DROP_ORDER` = services,
   proxies, `IfcCovering`, other, `IfcMember`, `IfcBuildingElementPart`, `IfcRailing`, `IfcPlate`,
   `IfcDoor`, `IfcWindow`: what a buyer never sees from outside first, the envelope last. The
   15 MB raw budget is unchanged.
4. **The admin 3D page names the groups.** The "dropped to fit 15 MB" chip shows "building services
   (pipes, ducts, fittings)", "generic objects", "other elements", "element skins and parts"; the
   "Explode all" advice says the skins are kept because they carry the facade colours and railings.

## Options considered

### Option A (chosen): the file's colours, services dropped first
Pros: the model looks like the architect's own renders without anyone setting anything; works for
every export with surface styles (Archicad, Revit); the budget goes to the envelope. Cons: more
element meshes (36 on N4 instead of 7, besides the 122 space meshes) and a larger raw GLB (8.5 MB
instead of 4.4).

### Option B: a hand-picked colour per class on the 3D page
Pros: one day, works on files without styles. Cons: wrong on N4: the orange panels are `IfcSlab`,
so "slabs orange" paints every floor orange; a person sets what the file already says.

### Option C: the render photos as facade textures
Pros: photographic look. Cons: perspective shots with trees in front; each side needs
rectification by hand; a week or more and still wrong at the corners.

## Trade-off analysis

| | A: file's colours | B: colour per class | C: photo textures |
|---|---|---|---|
| N4 looks like its renders | yes (orange panels, dark railings, glass) | no (orange floors) | partly |
| Person's work per project | none | a palette | hours per side |
| Raw GLB on N4 | 8.53 MB of 15 | 4.38 MB | + textures |
| Size | M | S | L |

## Consequences

**Easier.** An architect's colour scheme reaches the buyer as drawn; railings and cladding survive
the budget; dropped groups read as words on the admin page.

**Harder.** Two levels in `class_geo` (group, colour) on every change to the converter; a file with
a colour per element produces up to 48 materials plus one per group.

**Operations.** No migration, setting or container. A building's model takes the colours when its
IFC is converted again ("Re-run conversion"); the published copy changes with the next publication.
Measured on N4's file (2026-10-27, local, ifcopenshell 0.9.0): 602,129 triangles, 36 meshes, 21 of
the file's colours, 8.53 MB raw, services dropped; parsing 103 s, packing 1 s.

**Revisit.** Material properties (metal railings, glass reflections) from the file's specular and
reflectance values; furniture proxies kept while they fit (N4: 136,944 triangles nobody sees from
outside); placing the IFC on the site so the grass, trees and roads of the site features surround it
(BACKLOG 24).

**Out of scope here:** textures (`IfcSurfaceStyleWithTextures`), per-element picking of non-unit
elements, the massing model's colours (ADR-0017 keeps its own palette).

## Action items

### Phase A: converter
- [x] A1 `geometry/ifc.py`: `_shape` colours per triangle, `_rgba` (surface colour, default styles
      ignored), `_group`, `_by_colour`, `class_geo` group → colour, `_pack` one mesh per group and
      colour with `_kept_colours` and `_hex`, `CLASS_STYLE` gains `IfcBuildingElementPart`,
      `services`, `proxies`; `DROP_ORDER`; `stats.ifc_colours`.
- [x] A2 Tests: `make_ifc(styled=True)` (an orange slab with Archicad's 0.4 diffuse factor, a glass
      window, a pipe segment, a proxy);
      `test_the_architects_colours_are_kept_and_services_are_dropped_first`,
      `test_only_the_most_drawn_colours_become_materials`.

### Phase B: admin and docs
- [x] B1 `admin/pages/massing.page.ts`: dropped-group labels, the "Explode all" advice.
- [x] B2 Plan §13.2 IFC row, README status, BACKLOG.

### Phase C: N4
- [x] C1 Re-run the conversion of building A on the dev stack (2026-10-27): 8,794,520 bytes raw,
      834,456 after Draco (0.44 MB before this ADR), 614,805 triangles, 21 of the file's colours,
      services dropped, 122 plan spaces.
      *Found while implementing:* a re-run conversion suggests every plan space again, so the 122
      confirmations of the previous model are lost and "Confirm all plan spaces" is needed before
      the next publication; carrying a confirmation over when the space's GlobalId and the plan fit
      are unchanged is BACKLOG 55.
- [x] C2 The owner looks at the model on the 3D massing page, confirms the plan spaces and publishes
      again (the renders join the gallery with the same publication). Published 2026-10-28 at the
      owner's word ("publish"): 122 plan spaces confirmed, N4 version 8 live with 122 units; its
      building GLB is 836,408 bytes (Draco) with 36 coloured meshes and 122 unit nodes; the gallery
      holds the five renders.
