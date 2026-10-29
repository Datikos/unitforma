# ADR-0036: A picked floor of the IFC model is cut open

- **Status:** accepted (2026-10-29, the owner's pick of option 2 after his screenshot of N4 level 0); implemented 2026-10-29 on branch `adr-0036`, verified on N4 the same day; D1 (the admin tint by link status) added and done 2026-10-29; D2 (the section fill of cut elements) added and done 2026-10-29; D3 (the building page opens on the whole building) and D4 (a tap takes the picked floor on a tie) added 2026-10-30 after the owner's screenshot of N4 level 2; D5 (the plan starts on the lowest floor with flats) added and done 2026-10-30; Decision 4 amended 2026-10-30 by D6 (on the cut model only the picked floor is tappable)
- **Date:** 2026-10-29
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (floor isolation, interior view), §11.3 (MVP 3D); ADR-0006 Decision 6 and #E4, ADR-0030 (plan spaces), ADR-0033 (the architectural look)

## Context

The owner picked level 0 of N4 building A on the admin 3D page (2026-10-29, IFC model v12) and got
a flat green band across the facade: the walls, windows, balconies and orange frames of that floor
were gone. The upper floors showed a green haze, and at the west end boxes stood out of the building.

- **The spaces are prisms.** N4's IFC file holds no `IfcSpace`, so ADR-0030 builds each unit's
  space from its approved plan outline, extruded from the storey's elevation to the next storey's
  (`geometry/plan_spaces.py`, `ifc.prism`). The outlines include the balconies, so the prisms reach
  the railing line, in front of the facade.
- **The viewer draws the picked floor opaque.** `massing-viewer.applyFocus` gives the picked floor's
  unit meshes `opacity 1, transparent false`, which overrides the GLB's `SPACE_COLOUR` alpha of 0.9.
  For the schematic massing that is right: the unit boxes are the building. For an IFC model it
  paints a box over every wall of the floor. With no floor picked the same rule covers the whole
  building.
- **The other floors' spaces stay at `FADE_OTHER_FLOOR` = 18 %**, the haze, and the plan fit's error
  shows as boxes outside the walls.
- **The IFC elements cannot be hidden per storey.** ADR-0032 merges the elements of one class and
  one colour into one mesh across all storeys (158 meshes for 614,805 triangles on N4), so there is
  no storey object to switch off.

ADR-0006 #E4 asked for this view ("cut or fade the envelope above the chosen floor so interior
spaces are visible") and BACKLOG 23 carried it.

## Decision

1. **Only the IFC model is cut.** When the loaded GLB is an IFC conversion (a node with
   `ifc_class`) and a floor is picked, one horizontal clipping plane removes everything of the
   model above the cut. The schematic massing keeps today's fade: its units are separate meshes and
   already are the building. The plane is the only way to remove a storey from meshes merged across
   storeys.
2. **The cut height is `PLAN_CUT_M` = 1.2 m above the picked floor's base**, the lowest point of that
   floor's space meshes. For a floor lower than 2.4 m it is half the floor's height instead.
   Cutting at the next storey's elevation would leave a sliced slab ring over the floor. Floor plans
   are commonly drawn cut at about 1 to 1.5 m above the floor (a drafting convention, not checked
   against a standard). A floor with no space meshes is not cut; the other floors' spaces are hidden
   as in Decision 4.
3. **In an IFC model the spaces are tinted glass, never opaque.** `SPACE_GLASS_OPACITY` = 0.4 on the
   picked floor and on every floor when none is picked. The selected unit is at
   `SELECTED_GLASS_OPACITY` = 0.75 and a hovered one at `HOVER_GLASS_OPACITY` = 0.55. Spaces cast no
   shadow and stay out of the edge and occlusion buffers (`userData.ghost`).
4. **The other floors' spaces are not drawn while a floor is picked, but stay tappable below the
   cut.** A tap on one below the cut moves the floor (ADR-0006 Decision 6). A hovered one shows at
   `OTHER_FLOOR_HOVER_OPACITY` = 0.3. A ray hit above the cut does not count. The floors above are
   reached through the floor picker.
5. **The camera looks down into the floor.** On a change of the picked floor, and on load with a
   floor already set (the portal unit page), the camera keeps its azimuth, aims at the floor's
   centre and rises to `CUT_VIEW_ELEVATION_DEG` = 55°. The distance is the floor's diagonal. When
   the floor is cleared, the camera frames the whole model again. The buyer can orbit freely after
   that.
6. **The cut reaches every pass.** The plane is set on the model's materials with
   `clipShadows`, so removed floors cast no shadow. `GBufferPass` draws a clipped mesh with a
   normal material carrying the same plane, so edges and occlusion match the cut. The ground, the
   site features and the trees are never clipped. The plane exists from load on and sits far
   above the model when nothing is cut, so a floor change does not recompile shaders.

## Options considered

### Option A: see-through boxes
The picked floor's spaces as glass, the other floors' spaces hidden. Pro: the outside view stays,
small. Con: from outside a buyer still sees a facade with a tint, not the floor's flats; the plan
stays hidden behind walls.

### Option B: cut-away at the picked floor (chosen)
Option A's glass plus one clipping plane over the picked floor and a camera over it. Pro: shows the
real walls of the picked floor from the architect's model, which is what picking a floor is for.
Con: the floors above the picked one are not visible while it is picked; cut walls show as hollow
shells.

### Option C: both, behind a toggle
Outside glass view and the cut-away, switched by the buyer. Pro: both views. Con: one more control
on a phone screen and two looks to keep working; the floor picker already lets the buyer leave the
cut.

### Option D: split the IFC meshes per storey in the converter
Hide whole storeys instead of clipping. Pro: no shader change. Con: multiplies the mesh count by the
storey count (158 × 6 on N4) and needs a re-run of every IFC; a storey still hides its own interior,
so a cut is needed anyway.

## Trade-off analysis

| | A glass | B cut (chosen) | C toggle | D per storey |
|---|---|---|---|---|
| Shows the floor's walls | no | yes | yes | no |
| Floors above visible | yes | no | by toggle | no |
| Converter change | no | no | no | yes, re-run all |
| Cost per frame | none | one plane test per fragment | as B | more draw calls |
| UI controls added | none | none | one | none |

## Consequences

- **Easier:** a picked floor of an IFC model reads as a plan: walls cut at sill height, the flats
  as coloured glass, the selected one in amber. The whole building with no floor picked shows the
  architecture through the glass instead of covered boxes.
- **Harder:** while a floor is picked a buyer does not see the floors above it, so "where is this
  floor in the building" comes from the floor picker, not from the model. Cut walls have no cap:
  their inner faces show (double-sided materials, ADR-0032); D2 fills them. Two focus rules now live in the viewer,
  one per model kind.
- **Revisit:** caps on the cut walls (a stencil pass; done as a section fill by D2) if the hollow shells read badly on the owner's
  look; a cut for the schematic massing if a buyer asks for one; a glass opacity per device if a
  phone shows the glass too strong.

**Out of scope here:** the plan fit's offset that puts boxes outside the walls (ADR-0030 Revisit,
BACKLOG 49), and per-element seams (ADR-0033 Revisit).

## Action items

Phase A: viewer
- [x] A1 `libs/viewer-3d/src/lib/floor-cut.ts`: the constants of Decisions 2 to 5 and the pure rules
      `cutHeight`, `ifcSpaceOpacity` and `aimOverFloor`; `floor-cut.spec.ts` with a floor with
      spaces, a low floor, a floor without spaces, the opacity of each state, and the camera keeping
      its azimuth.
- [x] A2 `massing-viewer.ts`: the plane on the IFC model's materials with `clipShadows`, local
      clipping on the renderer, the IFC branch of the focus, the opacity per state, no shadow from
      spaces, the pick rule below the cut, the camera on a floor change; the massing model unchanged.
      The hover line drops the leading dot when the space has no building code.
      *Found while implementing:* a space's base lies on the slab, and the two flickered against
      each other, so the tint showed as streaks; the spaces get a polygon offset
      (`polygonOffsetFactor` −1, units −4) and the flats now read as tinted floors.
- [x] A3 `architectural-look.ts`: `GBufferPass` draws clipped meshes with clipped normal materials.

Phase B: texts
- [x] B1 The portal unit page's caption, the admin 3D page hint and its guide entry, the viewer-3d
      README, plan §7.3 and the portal paragraph, the root README's decision list; ADR-0006 #E4 ticked
      and BACKLOG 23 removed.
      *Found while implementing:* the unit page never passed the badge, so it said "Schematic model
      generated from floor plans" over the architect's model; it now passes the building model's
      disclaimer like the building page.

Phase C: verify
- [x] C1 N4 on the dev stack in headless Chrome: level 0, a middle level and no floor on the admin
      3D page, and the portal unit page; no slab ring at the cut, no edges above it, no shadow from
      removed floors, the frame rate against ADR-0033's 60 fps.
      *Done 2026-10-29* on the portal built from this branch against the dev API (v12): level 0,
      2 and 3 cut, walls readable, the flats tinted, no slab ring, no edges above the cut, 60 fps
      on each. Hover works on the picked floor and below the cut. A build with the other floors'
      spaces switched off entirely rendered the same frame, so the green on the lower facade is the
      picked floor's own balconies. The west end of the
      L shows A-x-03 reaching past the end wall: the plan fit's offset or a terrace in the outline
      (ADR-0030 Revisit, BACKLOG 49), visible before this change as the boxes outside the building.
      *2026-10-29:* the cause is neither: each floor plan sheet has its own origin, and levels 1 to
      3 sat 3.1–3.9 m off their slabs under the shared fit (ADR-0030 #D1).

Phase D: follow-up
- [x] D1 The admin 3D page tints each IFC space by its link status, in the hues of the status chips
      (confirmed `#34d399`, suggested `#fbbf24`, unmatched `#f87171`, not a unit `#9ca3af`), passed
      as `unitColors` keyed by the id the space carries in the GLB (the unit once confirmed, else
      `space:<GlobalId>`). C1 showed the GLB's own near-grey space colour at 40 % glass is barely
      visible on a cut floor. The portal keeps the availability colours. `admin/.../massing.page.ts`,
      its hint and the guide's "Show IFC model" entry.
      *Done 2026-10-29* on N4 level 0 and all floors (58 and 60 fps): the flats read green, the
      hovered one blue, corridors and cores grey. All 854 of N4's links are confirmed, so the other
      three hues are proven by `massing.page.spec.ts` only. The status chips split "unmatched"
      (red) from "not units" (grey) to match.
- [x] D2 Cut elements get a section fill instead of hollow shells (the Revisit's caps). The IFC
      materials are double-sided, so a cut wall showed its own inner faces lit like its outside.
      Options weighed on 2026-10-29:
      | | Back-face section fill (chosen) | Stencil caps | Keep the known look |
      |---|---|---|---|
      | Draws per frame | none added | 2 extra passes of the model (614,805 triangles each) and a cap plane | none |
      | Render chain | one `onBeforeCompile` on the opaque IFC materials | `stencil: true` on the renderer, a stencil buffer on the multisampled target, the helper meshes kept out of the G-buffer | unchanged |
      | Needs closed meshes | no: an open element shows its back faces dark, inside the band only | yes: an open mesh anywhere under the ray leaks a cap | no |
      | Result | the cut element's inside is one flat dark colour, outlined by the edge pass | a flat cap exactly at the cut | the walls read as hollow |
      Chosen: the fill. It adds no draw and leaves the chain as ADR-0033 built it. Rule: an opaque
      IFC element that is not a space draws its back faces in `SECTION_FILL` (#3b4048, the poché of
      a plan) when they lie between 0.5 m below the picked floor's base and the cut. Outside that
      band and with no floor picked, nothing changes. Glass (`alphaMode BLEND`) and the spaces keep
      their look. One shared shader hook and one shared uniform per viewer, so the program count
      does not grow with the meshes. `floor-cut.ts` (`SECTION_FILL`, `sectionBand`,
      `takesSectionFill`), `massing-viewer.ts` (`prepareCut`, `applyCut`), the viewer-3d README's
      known look, the guides.
      *Done 2026-10-29* on the portal building page of N4 built from this branch against the dev
      API (v12): levels -2, 0 and 2 show the cut walls, columns and door leaves dark, no dark patch
      off the band, 60 fps on each (60 before). Viewer-3d 19 tests; admin and portal initial bundles
      unchanged (498.05 and 390.89 kB).
- [x] D3 The portal building page opens on the whole building. Until now `level()` fell back to the
      first floor (N4: the parking level -2), so the architect's model always arrived cut open and
      a buyer never saw the building or its roof (owner, 2026-10-30: "a missing rooftop and the
      full building visual is uncommon"). Options weighed on 2026-10-30:
      | | Whole until a floor is chosen (chosen) | A whole/cut switch, cut by default | Keep |
      |---|---|---|---|
      | First view | the building with its roof | the lowest floor cut open | the lowest floor cut open |
      | Where the state lives | the link: no `?floor=` and no `?unit=` means whole | a page signal, lost on a shared link | — |
      | Back to whole | "Whole building" drops both from the link | the switch | not possible |
      Chosen: whole until chosen. A floor on the left, a band on the facade, a unit tapped on the
      model or a link with `?floor=`/`?unit=` cuts it (Decision 5 aims the camera as before); the
      plan below shows a default floor meanwhile (D5). The schematic massing follows the same rule
      (no fade until a floor is chosen). The spaces' polygon offset (A2) is on for the cut floor
      only: on the uncut building it pulled level 3's tint through the roof finish, whose top lies
      about 0.1 m over the spaces' 18.00 m top. `portal/.../building.model.ts` (`floorChosen`,
      `tapOnModel`), `building.page.ts`, `massing-viewer.ts` (`applyFocus`), the portal guide.
      *Done 2026-10-30* on N4 with the portal built from branch `adr-0036-whole` against the dev
      API: `/buildings/A?view=3d` opens on the whole building with a grey roof (the deployed
      portal opened on level -2 cut), `?floor=2` cuts as before, "Whole building" returns to
      `?view=3d`.
- [x] D4 A tap on a flat of the picked floor selects it instead of moving to the floor below.
      Adjacent storeys' spaces share a face: on N4 (the 2026-10-29 re-run) level 1 ends at 11.60 m where level 2
      begins (every level likewise, measured in the GLB on 2026-10-30). With the hit on the clipped
      top face ignored (Decision 4), the picked flat's floor face and the lower flat's ceiling tie
      at the same distance and either came first. Rule: below the cut the nearest hit on the picked
      floor wins; another floor's space counts only when the ray meets none of the picked floor.
      `floor-cut.ts` (`pickedHit`), `massing-viewer.ts` (`pick`), the viewer-3d README.
      *Done 2026-10-30*: 200 taps on a grid over N4 level 2 in headless Chrome.
      | Taps landing on | level 2 | level 1 | level 0 | level -2 |
      |---|---|---|---|---|
      | Deployed portal (before) | 163 | 27 | 8 | 2 |
      | This branch | 187 | 3 | 8 | 2 |
      The 13 left are taps where the ray meets no level 2 space (walls, the corridor, stairs) and
      reaches a space of a lower floor, which Decision 4 still allows.
- [x] D5 Before a floor is chosen the plan shows the lowest floor with an apartment, else with a
      commercial unit, else with any unit, else the lowest floor. Until now it was the first floor
      of the list, on N4 the parking level -2, under the whole building of D3 (owner's pick of
      the follow-up, 2026-10-30). The 3D view stays whole; the floor list marks the floor shown.
      `portal/.../building.model.ts` (`defaultFloor`), `building.page.ts` (`level`).
      *Done 2026-10-30*: `building.model.spec.ts` proves N4's order (parking -2, empty -1, flats
      from 0) and the fallbacks.
- [x] D6 On the cut IFC model a tap counts only the picked floor's spaces below the cut; the other
      floors' spaces are neither drawn nor tappable, and no longer show at 30 % on hover
      (`OTHER_FLOOR_HOVER_OPACITY` removed). Amends Decision 4. D4's 200-tap grid on N4 level 2
      left 13 taps that met no level 2 space (walls, the corridor, stairs) and moved to a flat of
      a floor below the buyer could not see; on a phone nothing warned first (owner's pick of the
      follow-up, 2026-10-30). Such a tap now does nothing; the other floors are reached from the
      floor list, the facade or "Whole building". The schematic massing keeps ADR-0006 Decision
      6: a tap on a faded floor moves there. `floor-cut.ts` (`pickedHit`, `ifcSpaceOpacity`),
      `massing-viewer.ts`, the viewer-3d README.
      *Done 2026-10-30*: `floor-cut.spec.ts` proves a miss of the picked floor (a lower flat
      under the ray, the tie face of the flat below) selects nothing.
