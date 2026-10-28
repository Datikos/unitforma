# ADR-0033: An architectural look for the IFC model: edges and ambient occlusion drawn by the viewer

- **Status:** proposed (2026-10-28); built the same day for the owner's look
- **Date:** 2026-10-28
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (fallback ladder, mobile budget), §13.2 (3D engine row), ADR-0006 (IFC to GLB, floor-first navigation), ADR-0016 (ground and site features), ADR-0017 (massing palette), ADR-0032 (the file's colours)

## Context

The owner's question on 2026-10-28, with a screenshot of N4's IFC in the Autodesk Viewer
(viewer.autodesk.com): "could you get full specification from the autodesk and make better renderer for
this kind of file?". What the screenshot shows and what our viewer does today:

- **The Autodesk picture** is flat-shaded faces in the file's colours (ochre panels, grey concrete, dark
  railings, glass), a thin dark line on every edge of every element, soft darkening where surfaces meet
  (under the balconies, in the stair core), no cast shadow, a light grey background. Nothing in it is
  more geometry than we have: ADR-0032 ships the same colours (21 of the file's colours on N4) and the
  same elements (614,805 triangles, 36 element meshes, 122 plan spaces, 8.79 MB raw, 0.83 MB Draco).
- **There is no Autodesk specification to fetch.** The viewer's renderable format (SVF, SVF2) is made in
  Autodesk's cloud by the Model Derivative service and is not published; the viewer is a bundled fork of
  three.js. The public surface is its JavaScript API. Autodesk's own type definitions
  (`@types/forge-viewer`, owner "Autodesk Forge Partner Development",
  https://raw.githubusercontent.com/DefinitelyTyped/DefinitelyTyped/master/types/forge-viewer/index.d.ts,
  read 2026-10-28) list what the look is made of: `setQualityLevel(useSAO: boolean, useFXAA: boolean)`
  (screen-space ambient occlusion and anti-aliasing), `setDisplayEdges(show)`, `setLightPreset(index)`,
  `setGroundShadow`, `setGroundReflection`, `setEnvMapBackground`, `setProgressiveRendering`. The same
  file types edges and faces as `THREE.Geometry`, a class three.js removed in r125 (January 2021), so
  the fork is older than that: inferred, not stated by Autodesk. The IFC format itself is public
  (ISO 16739-1:2018, buildingSMART) and ifcopenshell already reads all of it that we use. So the
  question becomes: which of those four things (edges, occlusion, light preset, anti-aliasing) do we
  draw, and where.
- **Our viewer** (`libs/viewer-3d/massing-viewer.ts`, three.js r186): one `WebGLRenderer` with
  `antialias: true` at a pixel ratio capped at 1.5, a hemisphere light at 1.1 and a sun at 1.6 with a
  2048 px PCF shadow map, `MeshStandardMaterial` with `flatShading`, the ground disc, site features and
  trees of ADR-0016, and dark lines (`EdgesGeometry` at 25°, opacity 0.35) on **unit meshes only**. On
  the IFC model the units are the plan spaces inside the walls, so the building's elements have no
  lines at all, and nothing darkens the balconies: the model reads flat.
- **Lines as geometry do not fit the budget.** Measured 2026-10-28 on the owner's Mac (Node 24,
  three r186) on a merged geometry the size of N4 (614,808 triangles in 25,617 shells of panels and
  railing bars): `EdgesGeometry(geo, 25)` took 1,518 ms, produced 512,340 segments, 12.3 MB of
  positions, and 420 MB of heap while running. A phone would take several times that and may run out
  of memory; the same lines computed at conversion time and stored in the GLB would add about 12 MB raw
  to a model that already uses 8.79 of the 15 MB raw budget (`KHR_draco_mesh_compression` compresses
  triangles, not lines).
- **Transparency matters to any screen-space method.** Glass arrives at alpha 0.31 (ADR-0032); the
  floor-first navigation fades other floors to 0.18 and other buildings to 0.08 (ADR-0006 Decision 6);
  drafts draw at 0.55 (ADR-0011). All of them set `depthWrite = false`, so a depth or normal buffer of
  the scene as drawn does not contain them.
- **Merged elements have no seams.** ADR-0032 Decision 2 merges every element of a group and colour
  into one mesh, so two ochre panels in one plane share no depth or normal step. Autodesk draws that
  seam from topology; a screen-space pass cannot.
- The portal already decides 3D versus plan per device (`portal/core/capabilities.ts`: WebGL2, data
  saver, `deviceMemory < 2`, width under 768 px); the plan's gate V7 asks ≥ 30 fps on a desktop and
  ≥ 20 fps on a mid-range phone under 300 MB.

## Decision

1. **The viewer draws the look; the GLB does not change.** `massing-viewer.ts` renders through a pass
   chain (`three/examples/jsm/postprocessing`): a G-buffer prepass of the scene with a flat-shaded
   `MeshNormalMaterial` into a half-float target with a `DepthTexture`; the beauty pass into a
   4-sample multisampled target; `GTAOPass` fed with that depth and normal texture (`setGBuffer`, so
   the scene is drawn twice per frame, not three times); an edge pass; `OutputPass`. Nothing in
   `geometry/ifc.py` changes.
2. **An edge is a depth or normal discontinuity between neighbouring pixels.** The edge pass
   (`architectural-look.ts`, `EDGE_SHADER`) compares each pixel with its four neighbours in the
   G-buffer: an edge where the view-space depth differs by more than `EDGE_DEPTH_RELATIVE = 0.02` of the
   pixel's own depth, or where the normals differ by more than `EDGE_NORMAL_DEGREES = 20`. An edge pixel
   is the beauty colour mixed with `EDGE_COLOUR = #334155` at `EDGE_STRENGTH = 0.6`. Thresholds are
   constants of the library, not settings.
3. **What is in the G-buffer.** Every mesh drawn at its own opacity, glass included (the GLB's alpha is
   the file's; a window gets its frame lines), the ground disc, the site features and the trees. A unit
   mesh faded by the focus (another floor or building) or drawn as a draft is left out, so faded parts
   get neither lines nor occlusion and stay a ghost behind the focused floor.
4. **Three tiers, decided once per viewer from the device** (`renderTier(...)`, a pure function):
   `full` (occlusion and edges) on WebGL2 with no data saver, `deviceMemory` of at least 4 GB or
   unknown, and a viewport of at least 768 px; `edges` (edges only, no GTAO) on any other WebGL2
   device; `plain` (the renderer alone, today's picture) without WebGL2. The pixel ratio stays capped
   at 1.5 (plan §7.3); GTAO runs at the full target size with 16 samples and the denoise pass.
5. **Lights for the look.** Hemisphere light to 1.5 (sky white, ground `#b7c4a8` as before), the sun to
   1.0 with the PCF shadow map as before (r186 has removed `PCFSoftShadowMap`); the sky gradient of the
   host stays behind the transparent canvas.
   The massing model (ADR-0017) goes through the same chain; its unit meshes keep their
   `EdgesGeometry` lines, because adjoining units on one flat facade have no depth step between them
   and the lines are what separates them (a massing unit is a few dozen triangles). The IFC model gets
   no line geometry.
6. **A known gap is written where a reader would assume the opposite** (`viewer-3d/README.md`,
   plan §13.2): seams between coplanar faces of one merged mesh are not drawn; per-element seams need
   an element id per vertex in the GLB and a converter change (BACKLOG, Revisit below).

## Options considered

### Option A (chosen): edges and occlusion as screen-space passes in our viewer
Pros: no data added to any model; cost per pixel, not per triangle (N4's 614,805 triangles cost the
same as a massing box); one pipeline for the massing and the IFC model; the tiers reuse the portal's
device rules. Cons: no seam between coplanar faces of one mesh; two scene draws per frame; a dozen
constants to tune by eye on the owner's model.

### Option B: `EdgesGeometry` on every mesh in the browser
Pros: real edges, including coplanar seams where the mesh has them; 30 lines of code. Cons: measured
1.5 s and 420 MB of heap on a Mac for N4, unknown and worse on a phone; 12.3 MB of line positions
alive next to the model; done again on every load.

### Option C: edges computed at conversion and stored in the GLB as line primitives
Pros: computed once, on the worker; exact. Cons: about 12 MB raw per N4-sized model on top of 8.79 MB
against the 15 MB raw budget that bounds what a phone decodes; Draco does not compress lines; a second
mesh kind in `_pack` and the Draco CLI step; ADR-0032's colour split would need the edges split the
same way.

### Option D: embed the Autodesk Viewer (APS)
Pros: the picture in the screenshot as is. Cons: every IFC uploaded to Autodesk's cloud for
translation (a paid Model Derivative call per model; the architect's file leaves our storage,
ADR-0007's reason for keeping files on the host); a proprietary format we cannot read or re-colour;
the unit picking, floor focus and availability tints rebuilt on a second engine.

### Option E: xeokit
Rejected in plan §13.2: AGPL for a frontend library we modify, or a licence fee.

### Option F: web-ifc in the browser
Parse the IFC on the client. Cons: N4's file takes 103 s to tessellate on a Mac in ifcopenshell and
the browser would download the source file; the GLB pipeline exists for exactly this reason.

## Trade-off analysis

| | A: screen-space passes | B: EdgesGeometry | C: edges in the GLB | D: Autodesk Viewer |
|---|---|---|---|---|
| Data added per N4 | 0 | 12.3 MB in memory | about 12 MB raw | the file leaves the host |
| Cost scales with | pixels | triangles (1.5 s on a Mac) | triangles, once | Autodesk's price list |
| Coplanar seams | no | yes | yes | yes |
| Occlusion | yes (GTAO) | no | no | yes (SAO) |
| Works on the massing model | yes | already | needs the massing packer too | no |
| Size | M | S | M | L |

## Consequences

**Easier.** The IFC model reads as the architect's: every balcony, railing and window frame has its
line, the recesses are darker; an uploaded IFC needs no setting to look right; a phone without the
memory for occlusion still gets the lines.

**Harder.** The viewer has a pass chain to keep working on three tiers; a shader of our own
(the edge pass) lives in the frontend; thresholds tuned on one model may need another look on the next
(a white building on a white sky gradient; a model in centimetres); seen on N4 at close range:
faint dotted verticals on the cladding panels where the tessellation's near-coplanar faces cross the
20° normal threshold (`EDGE_NORMAL_DEGREES` and `EDGE_DEPTH_RELATIVE` are the knobs for C2); the sky gradient of the host must
survive the chain (the output target keeps alpha; checked on the dev stack, see Phase C).

**Operations.** No migration, setting, container or model re-run. The admin bundle is lazy for the
3D page, so the passes join the massing chunk, not the initial bundle (its warning budget had 0.23 kB
left on 2026-10-28).

**Measured** (2026-10-28, headless Chrome 156.0.8078.48 with the Metal backend on an Apple M2, the admin 3D
page through `ng serve`, N4 building A: 614,805 triangles, 158 meshes, 0.83 MB Draco): `full` tier
at 1440 × 700 CSS px and a device pixel ratio of 1.5, 60 fps over 4 s (vsync-bound), 96–106 MB of
JS heap; `edges` tier at 600 × 700 and a ratio of 2, 60 fps, 118 MB. The chain adds no visible
cost at that size on that GPU; a frame-time budget below the vsync needs a slower device. Phone
numbers stay "not measured" until a device is in hand (plan rule: facts with a source). The picture:
a line on every panel, railing and step, darker under the balconies and in the stair core, the
file's colours; the sky gradient of the host shows through. The massing path of the chain (Decision 5)
was not looked at: the dev stack had no project with a ready massing model on 2026-10-28 (C2).
N4's conversion dropped only `services`, so the closed grey panels in front of the openings are the
file's `IfcBuildingElementPart` skins as converted (ADR-0032), not the look.

**Revisit.** Seams between coplanar elements (an element id per vertex in the GLB, a converter change
with ADR-0032's colour split); ground reflection and an environment map (the two remaining Autodesk
switches) once the look is judged on more than one model; a user switch for the look on the portal if
a phone tier disappoints.

**Out of scope here:** any change to the GLB or the converter; textures; the massing palette
(ADR-0017); picking of non-unit elements.

## Action items

### Phase A: viewer
- [x] A1 `libs/viewer-3d/src/lib/architectural-look.ts`: `renderTier(device)` and `DeviceFacts`,
      `EDGE_*` constants, the edge shader, `buildLookChain(renderer, scene, camera, tier)` returning
      the composer, the G-buffer target and a `setSize`; `GBufferPass` renders the scene with the
      override material, skipping meshes flagged `userData.ghost`.
- [x] A2 `massing-viewer.ts`: render through the chain; `applyFocus` flags ghosts; `addEdges` only
      when the model carries no `ifc_class` node; lights per Decision 5; `resize` and `ngOnDestroy`
      size and dispose the targets.
- [x] A3 Tests `architectural-look.spec.ts`: `renderTier` on a desktop, a data-saver phone, a 2 GB
      device, no WebGL2; the edge shader compiles against the uniforms it declares (string check).

### Phase B: docs
- [x] B1 `viewer-3d/README.md` (the chain, the tiers, the known gap), `frontend/README.md` entry,
      plan §13.2 3D engine row, README status sentence, BACKLOG rows.

### Phase C: the owner's model
- [x] C1 N4 building A on the dev stack in headless Chrome (2026-10-28): see Consequences,
      Measured; the captures are in the session's scratchpad, not in git.
      *Found while implementing:* r186's `GTAOPass` crashes when built with an external depth and
      normal texture (`setGBuffer` reads its own target for the debug output), so the chain builds
      the pass with its own buffers, hands it ours and disposes its own; `PCFSoftShadowMap` is gone
      in r186 (a console warning), the PCF map stays. The dev server does not pick up a type error
      in the library as a rebuild: it exits, and the page answers "connection refused".
- [ ] C2 The owner looks at the model on the 3D massing page and on the portal and keeps or tunes
      the constants of Decision 2 and 5.
