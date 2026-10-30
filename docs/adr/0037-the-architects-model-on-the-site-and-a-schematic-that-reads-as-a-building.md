# ADR-0037: The architect's model on the site, and a schematic model that reads as a building

- **Status:** accepted (2026-10-30, the owner's "ok do it" on options 4 then 1 after his screenshot of N4's schematic model); Phases A and B implemented 2026-10-30 on branch `adr-0037-site`, verified on N4 with the dev data in a dry run
- **Date:** 2026-10-30
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (3D), §11.3 (MVP 3D), §3.5 (placement); ADR-0006 Decision 5 and 6, ADR-0011, ADR-0017 Decision 2, ADR-0030 (plan fit, #D2 registration), ADR-0033 (the look), ADR-0035 (drawn outline), ADR-0036 (the cut)

## Context

The owner's screenshot of N4 (2026-10-30): "the second way to build 3D is very poor". The
schematic model (`geometry/massing.py`) is every apartment outline extruded as its own prism
(`UnitSolid`); everything that is not a unit is absent:

- the corridor is a slot splitting the bar in two rows, the stair cores and walls are notches and
  slits between the prisms (the gaps between neighbouring outlines);
- level -2's parking stalls stand as loose boxes under the building, because the ground is drawn
  at the model's lowest point (`massing-viewer.ts`: `groundY = min(box.min.y, 0)`);
- no slab, roof edge or window reads; an edge line on every unit boundary stripes the facade.

The architect's IFC model is drawn well (ADR-0032, ADR-0033, ADR-0036) but only on the building
page, alone, in its own frame: `geometry_models.model_transform` is `{"frame": "ifc", "offset_m"}`
(the model's minimum corner at the origin), so the site features drawn around it on the building
page are not where the building is, and the project page's site view shows only the schematic.
Placing the IFC on the site is BACKLOG 24 / ADR-0030 Revisit ("feeding a confirmed plan fit back as
the IFC's site_transform").

*Evidence that the placement can be composed, measured 2026-10-30 on N4 (nothing written).* The
plan fit maps building metres (the reference floor's sheet frame, ADR-0030 #D2) into the IFC plan:
`q = R(θ)·(x, −y) + t` (`plan_fit.sheet_to_ifc`, never mirrored). The site placement maps
building metres onto the site: `s = T + R(φ)·p` (`massing.Placement`). The IFC GLB is
`(q.x − ox, z − oz, −(q.y − oy))` (`ifc._to_gltf`), the schematic GLB `(s.x, h, s.y)`. Composing
`placement ∘ fit⁻¹` (the two y flips cancel: a rigid transform) and applying it to the bounds of
the IFC GLB's plan spaces of N4 building A (θ 0.0°, t (−20.498, 30.5), offset (−14.078, −26.889,
−5.2), placement (40.926, 29.089), 0°):

| Level | IFC plan spaces on the site, m | Schematic model, m |
|---|---|---|
| -2 | x 56.5–115.5, y 49.4–82.5 | x 56.5–115.5, z 49.4–82.5 |
| 0 | x 53.6–115.6, y 49.3–83.2 | x 53.6–115.6, z 49.3–83.2 |
| 1, 2, 3 | x 54.7–121.3, y 49.4–82.5 | x 54.7–121.3, z 49.4–82.5 |

Vertically N4's floors carry explicit elevations equal to the IFC storeys (level -2 at −3.0 m,
level 0 at 0.0 m; the GLB's level 0 spaces start at y 5.20 = 0.0 − oz). The stats keep only the
number of storeys, so the fit storey's elevation must be stored to align heights.

## Decision

1. **A placed building with a fitted IFC model is drawn with that model on the site.** The model's
   site matrix is `placement ∘ fit⁻¹` in glTF coordinates, with the vertical offset
   `base(fit floor) − (storey elevation − oz)`; it is computed when the snapshot is built
   (`geometry.site_matrix`), never stored, so a later placement or re-run is followed at once.
   It exists when the model's plan fit was accepted (`stats.plan_fit` without `reason`, with
   `storey_elevation_m`), the building is placed (`placement_status` not `unplaced`) and the model
   is ready; otherwise the building keeps the schematic model. ADR-0030 #D1's per-level shifts are
   the IFC's own and do not enter the matrix (after #D2 they are zero on N4).
2. **The conversion stores the fit storey's elevation** as `stats.plan_fit.storey_elevation_m`. A
   model converted before has none and keeps the schematic on the site until its next
   "Re-run conversion" (the spaces do not move, so ADR-0035's carry rule keeps the confirmations).
3. **The portal project page shows one scene**: the schematic model without the buildings that
   have a site matrix, plus each such building's public IFC GLB under its matrix. The snapshot
   carries `building.model.site_matrix` (16 numbers, column-major, glTF metres). The building page
   draws its IFC model under the same matrix, so the roads and gardens around it are where the
   site plan puts them. The admin 3D page keeps its massing / IFC switch. The change reaches the
   portal with the next published version (snapshots are immutable, ADR-0018).
4. **The viewer loads more than one GLB**: `models` (`{src, matrix, buildingCode}`) next to `src`,
   each under its own group; "is an IFC model" becomes a property of a mesh, so the glass spaces,
   the cut and the section fill apply to the IFC meshes only; the schematic units of a building
   drawn by its IFC model are hidden and not pickable; the camera, the look's scene box and the
   ground span every group.
5. **The schematic model is drawn as floors, not boxes.** Per building and floor, a *plate* is
   the morphological closing of all its current outlines (`buffer(+c).buffer(−c)`,
   `PLATE_CLOSE_M` = 2.0 m: gaps up to 4 m, N4's corridor and cores); *infill* = plate − units is
   one neutral mesh per floor (no `unit_id`, not pickable, faded with its floor); a *slab band*
   `SLAB_BAND_M` = 0.3 m thick, `SLAB_OVERHANG_M` = 0.15 m proud of the plate, at every floor's base;
   the top floor's plate gets a parapet `PARAPET_M` = 1.0 m high and 0.25 m thick. Units keep their
   availability colours and picking (the colour is how a buyer picks, ADR-0017 Decision 2). Plates
   are built from all current outlines before the public filter, so unlisted units still close
   the building.
6. **The ground lies at level 0's base**; floors below ground are under it and appear only when a
   floor below ground is picked, which lowers the ground to that floor's base.

## Options considered

### Option A: the IFC model placed at read time from the plan fit and the placement (chosen for 1 to 4)
- Pros: no new stored transform to keep in step; follows a new placement or re-run at once;
  verified on N4 to 0.1 m.
- Cons: only for models with an accepted plan fit; an IFC with its own zones and no plan fit
  stays off the site (a later fit of its spaces would add it).

### Option B: write the IFC's `site_transform` once at conversion (BACKLOG 24's wording)
- Pros: one stored matrix.
- Cons: stale after every new placement; one more value to keep in step on review.

### Option C: floor plates with infill, slabs and parapet (chosen for 5 and 6)
- Pros: reads as a building; units keep colours and picking; no new input.
- Cons: the closing width is a guess (a courtyard notch under 4 m fills in); facades stay flat.

### Option D: a shell from the drawings' outer walls
- Pros: the exact envelope with cores and corridors.
- Cons: depends on clean vector line work; scanned sets have none; L size. A later refinement of C.

### Option E: cosmetic only (merge units per floor, slab lines)
- Pros: small.
- Cons: the gaps stay; the complaint stays.

## Trade-off analysis

| | A + C (chosen) | B + C | D | E |
|---|---|---|---|---|
| N4 on the site | the architect's model | the architect's model, stale on a new placement | schematic | schematic |
| A building without IFC | floors with infill and slabs | same | exact shell where drawn | gappy boxes |
| New stored state | `storey_elevation_m` in stats | a matrix per model | wall contours | none |
| Size | M + M | M + M | L | S |

## Consequences

- *Easier:* the portal shows N4 as the architect drew it on the site plan; the building page's
  site features finally sit around the IFC; the schematic reads as floors for every other building.
- *Harder:* the viewer holds several models; "IFC" is a per-mesh rule reviewers must keep; the
  snapshot carries a matrix that depends on two other tables (plan fit, placement).
- *Revisit:* the closing width on the first courtyard building; window bands on the schematic
  facades; Option D where the line work is clean; placing an IFC with its own zones.
- **Out of scope here:** writing a `site_transform` for IFC models (BACKLOG 24 stays open for the
  IFC-without-plan-fit case); the admin 3D page's composed site view.

## Action items

Phase A: the architect's model on the site
- [x] A1 `plan_spaces.build` stores `storey_elevation_m`; `ifc_service.site_matrix(db, model,
      building)` over the pure `geometry/site_matrix.site_matrix_of`. Tests: `test_site_matrix.py`
      (a point of an outline lands where the schematic draws it, for four fits and placements with
      rotation and scale; N4's level 0 corner), the zoneless conversion test (the stored elevation,
      no matrix until placed, a rotation about the vertical only).
- [x] A2 Snapshot: `building.model.site_matrix` (`publishing/snapshot._building_model`); portal
      `BuildingDoc.model.site_matrix` (optional: older snapshots lack it).
- [x] A3 Viewer: `models` (`PlacedModel`), `srcMatrix`, `userData.ifc` per mesh (`paint`, the
      massing branch of `applyFocus`, `addEdges`), a building's schematic meshes hidden when its
      model loaded (a failed load keeps them), one root group for the camera, look and ground;
      a load token drops a slower earlier load.
- [x] A4 Portal: the project page passes `placedModels` and a disclaimer naming which buildings
      are the architect's (`site-view.model.ts`, 3 specs); the building and unit pages pass
      `srcMatrix`; the portal guide, the viewer-3d README, the README.
- [x] A5 Verified 2026-10-30 on N4: the branch's portal against the dev API with building A's
      matrix added to the API response in the test server (N4's conversion predates
      `storey_elevation_m`): the project page shows the architect's model on its paved plot between
      the roads with the gardens' trees around it, the building page the same, level 2 cut open in
      place; 60 fps on each. N4 needs one "Re-run conversion" and a new published version to show
      it for real (Decision 2 and 3).

Phase B: the schematic as floors
- [x] B1 `massing.py`: `floor_plates` (built in `service.collect` from every current outline),
      `extrude_polygon` (holes, constrained triangulation), `_floor_nodes` (infill = plate − the
      GLB's units, slab band, the top floor's parapet; extras `structure`, `floor_level`,
      `building_code`, no `unit_id`). Tests: `test_massing_floors.py` (5); the GLB test counts unit
      nodes by `unit_id`; the public contract allows `structure`.
      *Found while implementing:* round joins on the sliver clean-up made N4's infill 107,688
      triangles; mitre joins and a 5 cm simplify bring it to 9,928.
- [x] B2 Viewer: `structure` meshes fade with their floor and building and get no line geometry;
      the ground at y 0 in site metres (`groundAtZero`: the schematic, or an IFC under its
      matrix), lowered to a picked floor's base below ground (`lowerGround`).
- [x] B3 Verified 2026-10-30: N4's schematic built by this branch's code in a one-off worker
      container against the dev data (nothing written), shown by the branch's portal in place of
      the published one: one closed block with slab bands and a parapet, the parking under the
      ground, level 1 picked with the other floors faded, level -2 picked with the ground lowered;
      60 fps on each.
      | N4 schematic | Units | Infill | Slabs | Parapet | Triangles | GLB |
      |---|---|---|---|---|---|---|
      | Before | 122 | — | — | — | 12,676 | 302 KB |
      | After | 122 | 5 floors | 5 bands | 1 | 23,560 | 632 KB |
      Guides and README in the same change. The portal shows it after the next massing build and
      a new published version.
