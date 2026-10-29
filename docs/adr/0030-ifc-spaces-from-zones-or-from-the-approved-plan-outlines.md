# ADR-0030: IFC spaces from the architect's zones or from the approved plan outlines; export diagnostics; duplicate uploads

- **Status:** accepted (2026-10-27, "let start"; implemented 2026-10-27, C2 docs in the same change); Decision 4 amended 2026-10-29 by D1 (a level may refine the shared translation), D2 open
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (building model budget), §13.1 (document → published project), ADR-0006 Phase C (IFC intake, space links), ADR-0008 (document kinds), ADR-0011 (massing from outlines), ADR-0025 Decision 5 (placement by footprint fit)

## Context

The owner's request on 2026-10-27, after the first real IFC: "in different cases there may be zones
sometimes; you should support both". What happened that day, with the numbers:

- The architect's export `P1-M1-V06-2025-10-13 Jan Homeri.ifc` (Archicad 29.0.1, IFC2X3, 63,305,642
  bytes, 9,111 drawable products, 6 storeys) holds **no `IfcSpace` and no `IfcZone`**. The heavy worker
  converted it in 121 s to a 0.3 MB Draco GLB (234,185 triangles, 7 merged class nodes, 79 elements that
  failed to tessellate, class "other" dropped to fit the 15 MB raw budget: 4,701
  `IfcBuildingElementPart` skins plus the MEP classes). The 3D massing page showed "0 spaces" and
  nothing to link; the warning added under ADR-0008 #6 names the authoring tool.
- The file's STEP header says why. `FILE_DESCRIPTION` carries the translator options as strings of
  the form `Option [Name: Value]`; the ones that matter here, as written in that file:
  `Elements to export: Visible elements (on all stories)` (hidden zone layers are not exported),
  `IFC Base Quantities: Off` (no floor areas even with zones), `Material Preservation: Explode all`
  (composite skins as separate parts, the reason for the dropped class),
  `Space containment: Off`, `IFC Domain: All`, `Structural Function: All Elements`. `FILE_NAME`
  carries `originating_system = 'Graphisoft - Archicad - 29.0.1'`. ifcopenshell exposes both through
  `file.header.file_description.description` and `file.header.file_name.originating_system` (checked
  on 0.8.x, 2026-10-27). Graphisoft's help states that zones export as `IfcSpace` when they are inside
  the export scope (visible or selected elements, or the entire project) and that the Model Filter
  picks element types (<https://help.graphisoft.com/AC/24/INT/_AC24_Help/115_IFC/115_IFC-34.htm>);
  the Archicad 29 menu path is unverified.
- The same bytes were uploaded three times under three documents (sha256 `69618fd9…`, 06:38, 07:57
  and 08:37 UTC) and converted five times (two "Re-run conversion" clicks). Nothing told the uploader
  that revision 3 was revision 1 again; `document_revisions.sha256` is written by the worker and read
  by nobody.
- What the platform already has for the building: the mapping pipeline produces approved unit
  outlines per floor in building-local metres (`unit_boundaries.polygon_m`, sheet frame: x right, y
  down), floors with elevations and heights (`floors.elevation_m`, `height_m`,
  `geometry_service.floor_elevations`), and the massing extrudes exactly those outlines
  (`massing.UnitSolid`, `massing.extrude`: sheet y → glTF +Z). The IFC reader maps IFC (x, y, z) to
  glTF (x, z, −y) (`ifc._to_gltf`), so a plan ring enters the IFC frame as (x, −y) and the two frames
  differ by a rotation and a translation only (a placement never mirrors, `massing.building_rectangle`).
  `autopilot/passes/placement.py` already fits a footprint polygon to a candidate face by rotation
  search (3° coarse, 0.5° fine) and centroid translation with IoU as the score, with
  `rules.PLACEMENT_AREA_TOLERANCE = 0.25` and confirm/draft thresholds 0.9/0.8.
- The viewer contract is the node `extras` (`unit_id`, `code`, `floor_level`, `unit_type`,
  `ifc_global_id`), read by `viewer-3d/massing-viewer.ts`; `ifc.relink_glb` rewrites them by
  `ifc_global_id`, and `ifc_service.public_glb` hides unconfirmed or unlisted spaces in the published
  copy. `ifc_space_links.ifc_global_id` is `String(22)`, the IFC GUID width;
  `ifcopenshell.guid.compress(uuid.hex)` returns 22 characters and `guid.expand` reverses it (checked
  2026-10-27), so a unit id has a valid, deterministic GlobalId.
- Found on the way: `ifc._pack` writes `floor_level` as the storey index and relies on the relink
  to replace it with the project's floor level; `ifc.read_ifc` parses, tessellates and packs in one
  call, so nothing can be added between parsing and packing.

## Decision

1. **The IFC reader reports the export settings that decide whether the file can serve.**
   `ifc.read_ifc` parses `FILE_DESCRIPTION` strings of the form `Option [Name: Value]` into
   `stats.export_options`, keeping only `elements_to_export`, `base_quantities`,
   `material_preservation`, `space_containment` (names normalised to snake case, values as written);
   `stats.application` falls back to `FILE_NAME.originating_system` when no `IfcApplication` exists.
   The 3D massing page turns flagged values into one advice line each: visible-elements export when
   the model has no spaces ("zones on a hidden layer are not exported; ask for Entire project"),
   base quantities off ("no floor areas will be copied on confirm"), explode all ("skins as separate
   parts; the model is larger than it needs to be"). These lines replace the generic Archicad paragraph
   of ADR-0008 #6 when options are present. Option names are evidence from one Archicad 29 file; other
   tools write other strings and simply produce no lines.
2. **A revision that repeats a file already processed in the project says so and, for an IFC that
   already is the building's model, is not converted again.** In `documents.jobs.process_revision`,
   after `inspect`, a `done` revision of any document of the same project with the same `sha256`
   sets `document_revisions.processing_note` (new, `String(300)`, migration 0021, expand only):
   "Same file as <document title> rev <n>". Sheets, proposals and `supersedes_revision_id` hang off
   revisions, so every other kind is processed as usual. For `application/x-step`, when the building's
   current `ifc` model is `ready` and its revision carries that checksum, the revision ends `done`
   with the note and `geometry.ingest_ifc` is not queued; "Re-run conversion" stays an explicit re-run
   (`POST /buildings/{id}/model/rebuild` queues the task directly). The document card shows the note
   as a neutral line, not the red error alert.
3. **A building's spaces come from `IfcSpace` when the file has any, otherwise from the approved
   outlines of its floors.** Both sources produce the same thing: space nodes in the building's GLB
   and `ifc_space_links` rows, so the reviewer's table, the confirm flow, the relink and the published
   copy do not change. `ifc_space_links.source` (new, `ifc | plan`, default `ifc`, migration 0021)
   tells them apart. Mixing per storey (a partial export) is Revisit, not this decision.
4. **A plan space is the unit's outline placed in the IFC frame between its storey's elevations.**
   `ifc.read_ifc` is split into `parse_ifc` (storeys, spaces, class geometry, offset, raw IFC
   coordinates, header stats) and `pack_ifc` (the budget loop of ADR-0006 C3); `read_ifc` stays as
   the wrapper. When `parse_ifc` returns no spaces, `ifc_service.ingest_ifc` loads the building's
   floors, non-removed units and their current calibrated boundaries, and:
   - matches storeys to floors with `ifc_match.match_floors` (elevation within 0.3 m, else order when
     counts agree); a floor without a storey takes base and height from `floor_elevations`;
   - takes the lowest floor that has outlines and a matched storey as the **fit floor**; its plan
     footprint is the union of that floor's rings mapped to (x, −y); the **IFC footprint** is the XY
     convex hull of the `IfcSlab` elements contained in the matched storey (`_storey_of`), else of
     every drawn element of that storey, else the whole model;
   - fits the plan footprint onto the IFC footprint with the placement search (rotation 0–360° at
     3°, refined at 0.5°, centroid translation, IoU score) without the area pre-check (an IFC slab
     includes corridors, cores and balconies that the apartment union excludes); the result is
     `stats.plan_fit = {rotation_deg, tx, ty, iou, floor_level, storey}`;
   - when the IoU is below `rules.IFC_PLAN_FIT_MIN_IOU = 0.30`, or there is no slab, floor or
     calibrated outline, writes `stats.plan_fit = {"reason": …}` and produces no spaces; the page
     says which;
   - otherwise applies the same transform to every outline of every floor that has a storey or an
     elevation, extrudes it from the storey elevation (or the floor's base) to the next storey's
     elevation (or the floor's height), and hands the solids to `pack_ifc` as spaces with
     `GlobalId = ifcopenshell.guid.compress(unit_id.hex)`, `name = unit code`, `floor_level` = the
     floor's level (fixed for IFC spaces too), material `SPACE_COLOUR`, the same extras as an
     `IfcSpace` node plus `source: "plan"`.
   Each plan space becomes an `IfcSpaceLink` with `source = plan`, `unit_id` and `floor_id` set,
   `footprint_m` the placed ring, `areas = {}`, `status = suggested` and `confidence = iou` (the unit
   is certain by construction; the alignment is what the reviewer confirms). Confirming writes no
   areas, because a plan space has no IFC quantities; the page says so. `stats.spaces` counts both
   sources, `stats.spaces_plan` the plan ones.
   **Amended 2026-10-27, after the first real file** (the Archicad export of a three-block
   complex; blocks B, C and D are separate buildings in the platform, 88 outlines on levels −1 to
   3; composite slabs exploded into parts):
   - storey elevations are multiplied by the file's length unit scale
     (`ifcopenshell.util.unit.calculate_unit_scale`); the export said millimetres and no storey
     had matched a floor;
   - the storey target is the union of its slab footprints, or their convex hull when the union is
     under half of the hull's area (exploded composites leave balconies and landings as `IfcSlab`:
     203 m² of slab union under a 1,937 m² hull on the ground storey; the basement slab was whole,
     1,466 m² under 1,866 m²); the model's bounds remain the last resort;
   - the fit runs in two scopes, the filed building's outlines alone and the outlines of every
     building of the project on the same floor levels (blocks mapped on one sheet share the
     frame), and the scope with the higher mean IoU wins; spaces are built for the filed building
     only. One block alone fitted at IoU 0.07–0.12 (a 300 m² row inside a 1,937 m² envelope has
     no anchor); the project union fitted at 0.30–0.32 with 0.85–1.0 of every level inside;
   - one transform is scored jointly over every level with outlines and a storey
     (`plan_fit.joint_fit`: candidates from the fit level, winner by the summed IoU), which broke
     the 180° ambiguity of the long rectangular complex (355° and 176° scored alike on one level);
   - for the XY target a storey within 1.6 m of the floor's elevation also serves when none is
     within 0.3 m (blocks C and D sit at +1.0 m and +2.0 m against the complex's storeys);
     the heights of the spaces still come from the strict match or the floor;
   - acceptance: mean IoU ≥ 0.30, or ≥ 0.20 with every level at least 85 % inside a slab or hull
     target (never the bounds, inside which anything covers fully).
   `stats.plan_fit` carries `scope`, `per_level` (IoU and coverage), `min_coverage`, `face`
   (`slabs | hull | bounds`) and the fit level's storey.
5. **Thresholds and budget.** `IFC_PLAN_FIT_MIN_IOU = 0.30` is a start; the first real building with
   outlines and a zoneless IFC sets it (Revisit). Plan spaces are flat extrusions (two caps and the
   walls, `massing.extrude`), a few hundred triangles each; the 15 MB raw budget applies to the whole
   GLB as before, and plan spaces are never dropped (they are the point of the model).

## Options considered

### Option A (chosen): derive the spaces from the approved outlines, in the IFC frame
Pros: works with today's file, the reviewer's flow and the viewer contract stay the same, the IoU
fit is the placement code already in the repository, and the resulting transform is most of
BACKLOG 24 (IFC on the site). Cons: one more frame transform to hold in the head; the fit can be
wrong on an L-shaped building whose apartments cover one wing only (the IoU and the review step
catch it).

### Option B: require the re-export (do nothing)
Pros: no code, the architect's zones carry the names and areas the matcher wants. Cons: the owner
saw that the first real export had no zones, and many offices never draw them; a project then has
an IFC model buyers cannot click, with no fallback.

### Option C: show the massing instead of the IFC when the file has no spaces
Pros: trivial. Cons: throws away the architect's geometry for exactly the case the owner brought;
the massing is what the IFC was meant to replace.

### Option D: detect rooms from the walls and slabs geometrically
Pros: no dependency on the plans. Cons: a research task (wall graph closure on exploded skins,
79 failed elements in the first file), with no unit identity at the end; rejected.

## Trade-off analysis

| | A: plan outlines | B: re-export | C: massing | D: room detection |
|---|---|---|---|---|
| Works on the 2026-10-27 file | yes, after the fit | no | no (loses the model) | unknown |
| Unit identity of a space | certain | from names, matched | n/a | none |
| Reviewer step | confirm the alignment | confirm names | none | n/a |
| Areas on confirm | none (plan has none) | yes, if quantities on | n/a | none |
| Code | fit + pack split, migration 0021 | none | small | large |

## Consequences

**Easier.** A zoneless IFC still gives a clickable 3D building. The uploader learns at once that a
file is the same one, and the page tells the architect which export switch to flip, in their own
tool's words. `stats.plan_fit` composed with `site_transform` is the IFC-on-site placement of
BACKLOG 24.

**Harder.** Three frames on every review of the 3D code: sheet (y down), IFC (y up, metres, offset),
glTF (Y up, Z = −IFC y). Two sources of space links with different meanings of "confirm" (names
versus alignment). `read_ifc` callers must know whether they want the parse or the pack step.

**Operations.** Migration 0021 is expand only (two nullable or defaulted columns), compatible with
the previous release; the heavy worker image is unchanged. No new container, queue or job.

**Revisit.** After the first real building with outlines and a zoneless IFC: `IFC_PLAN_FIT_MIN_IOU`
(the real file passed at 0.30–0.32, a thin margin; the candidates 349° and 355° differed by 6° and
8 m, so the reviewer's 3D check is part of the flow), mixing per storey (a partial export with zones
on some floors), a project-level IFC (one file covering several blocks is filed once per block
today, three conversions of the same 63 MB), and whether a confirmed plan space should feed back a
`site_transform` for the IFC (BACKLOG 24).

**Out of scope here:** rooms inside a unit, IFC on the site (BACKLOG 24), unit areas from plan
spaces (the documented areas of the drawing already exist, ADR-0006 Phase A), DWG/DXF-derived IFC.

## Action items

### Phase A: diagnostics and duplicates
- [x] A1 `geometry/ifc.py`: `export_options` from the header, `application` fallback; unit test on the
      pasted `FILE_DESCRIPTION` of 2026-10-27
      (`test_ifc_ingest.py::test_header_options_reads_the_archicad_translator_settings`).
- [x] A2 Migration `0021_ifc_plan_spaces`: `document_revisions.processing_note String(300)`,
      `ifc_space_links.source String(10) NOT NULL DEFAULT 'ifc'`; models; `RevisionOut.processing_note`,
      `IfcSpaceLinkOut.source`; OpenAPI regenerated.
- [x] A3 `documents/jobs.py`: same-checksum note; IFC not re-queued when the building's current ready
      model came from that checksum; test `test_duplicate_ifc_upload_is_noted_and_not_converted_again`.
- [x] A4 Admin: the note on the document card (neutral line), the advice lines on the 3D massing page.

### Phase B: spaces from the plan outlines
- [x] B1 `geometry/ifc.py`: `parse_ifc` / `pack_ifc` split, `PlanSpace` input, storey slab hulls,
      `floor_level` from the floor; `read_ifc` unchanged for callers.
      *Found while implementing:* only plan spaces carry the project's floor level from the start;
      an `IfcSpace` node still gets the storey index at packing and the floor level from the relink
      afterwards, because the storey-to-floor match needs the database and runs after packing.
      Decision 4's "fixed for IFC spaces too" is therefore true after the relink, not in the packed
      file.
- [x] B2 `geometry/plan_fit.py`: the fit (shared rotation search with `autopilot/passes/placement.py`,
      moved there from the pass), the (x, −y) mapping; test with a known rotation and translation
      recovered within 1° and 0.1 m.
- [x] B3 `geometry/ifc_service.py`: load floors, units and boundaries; decide the source; plan
      spaces → links with `source = plan`; `stats.plan_fit`, `stats.spaces_plan`;
      `plan_fit.IFC_PLAN_FIT_MIN_IOU` (in `geometry`, not `autopilot.rules`: geometry must not
      import the solver). *Found while implementing:* the pure part lives in
      `geometry/plan_spaces.py`; `confirm_plan_links` and
      `POST /buildings/{id}/ifc-links/confirm-plan` confirm every suggested plan space with one
      relink, since one `decide` per space rewrites the GLB each time (ADR-0006 E3).
- [x] B5 (amendment, 2026-10-27) `parse_ifc` unit scale and slab footprint rings per storey;
      `plan_spaces.storey_target`, two scopes, loose storey for the target, acceptance rule;
      `plan_fit.joint_fit`; `_plan_inputs` loads the project's outlines with building and level.
      Tests: `test_parse_ifc_scales_storey_elevations_by_the_file_unit` (millimetre fixture),
      `test_plan_spaces_fit_the_project_when_the_block_alone_does_not`,
      `test_plan_spaces_use_the_hull_when_the_slabs_are_exploded`. Measured on the real file in the
      heavy worker (2026-10-27): B 31 spaces, C 36, D 21, scope project, rotation 349–352°, mean IoU
      0.30–0.31, every level 85–100 % inside.
- [x] B4 Tests: `make_ifc(spaces=False)`; end to end: IFC without spaces plus two calibrated outlines →
      two `plan` links suggested with the IoU, two space nodes carrying the units' ids, `public_glb`
      keeps them pickable only when listed; the reason path when no outline is calibrated.

### Phase C: screen and docs
- [x] C1 Admin 3D massing page: source chip per row ("from plan"), the fit line (rotation, IoU, fit
      floor, slab or bounds) or the reason, "Confirm all plan spaces" button, the areas caveat in the
      section text.
- [x] C2 README status sentence; BACKLOG rows (#36 updated, new Revisit rows); ADR-0006 Phase C and
      ADR-0008 #6 pointers; this ADR's status line.

### Phase D: floors drawn on different sheet origins (amendment, 2026-10-29)

*Evidence.* N4 building A (IFC v12, the owner's level 0 screenshot under ADR-0036) showed the flats
of levels 1 to 3 reaching past the facade. The fit was made on level -2 (the only `slabs` target,
rotation 2.5°) and carried to every level; each floor plan sheet has its own origin. Measured in the
heavy worker against each storey's own target:

| Level | Target | Coverage, shared fit | Coverage at the best shift | Best shift |
|---|---|---|---|---|
| -2 | slabs | 0.978 | 0.987 | 0.7 m |
| 0 | hull | 0.984 | 0.993 | 1.3 m |
| 1 | hull | 0.878 | 1.000 | 3.4 m |
| 2 | hull | 0.854 | 1.000 | 3.9 m |
| 3 | hull | 0.901 | 1.000 | 3.1 m |

On the hull targets the coverage is flat (0.997–0.999) for shifts from 3 m to 5 m on level 1 to 3,
so the best IoU or coverage alone does not pin a level.

- [x] D1 `plan_fit.level_shift`: after the shared fit, every level other than the fit level searches
      its own translation onto its storey's target on a 0.25 m grid within `LEVEL_SHIFT_MAX_M` = 5 m,
      and takes the **smallest** shift whose coverage is within 0.005 of the best; it moves only when
      the coverage gains `LEVEL_SHIFT_MIN_GAIN` = 0.05 or more, and a shift that would reach the cap
      is refused (the real offset may be larger). The rotation stays shared. `plan_spaces.build`
      applies the shift per level and writes `per_level[k].shift_m`, `coverage_shifted` or
      `shift_refused` into `stats.plan_fit`; the admin fit line names the moved and the refused
      levels (`pages/ifc-plan-fit.ts`). Tests: `test_a_level_drawn_on_another_sheet_origin_moves_onto_its_slab`,
      `test_a_level_already_on_its_slab_or_too_far_off_keeps_the_shared_fit`, `ifc-plan-fit.spec.ts`.
      *Measured 2026-10-29* as a dry run on N4's file and outlines in the heavy worker (nothing
      written): levels 1, 2 and 3 move 2.8, 3.3 and 2.5 m to 0.995–0.996 inside, levels -2 and 0 stay;
      `build` takes 3.69 s instead of 0.86 s, on a conversion that runs in the background.
      *Consequence:* on the next conversion of a building whose levels move, ADR-0035's carry rule
      (footprint IoU 0.98 or more) sends those levels' confirmed plan spaces back to suggested, since
      they did move; "Confirm all plan spaces" confirms them again in one click. N4 is not re-run here:
      that is the owner's "Re-run conversion".
- [ ] D2 The schematic massing (`geometry/service.py`) and the site outline stack each unit's
      `polygon_m` from its own sheet with no registration between the floor sheets, so N4's massing
      has the same 3 m stagger between level -2 and levels 1 to 3. Register each floor sheet to the
      building (from the outer walls, the grid axes or a confirmed IFC fit) once, where `polygon_m`
      is made, so every consumer reads aligned floors. BACKLOG 59.
