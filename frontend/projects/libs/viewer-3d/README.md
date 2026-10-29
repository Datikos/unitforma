# viewer-3d

three.js wrapper for Unitforma (plan §11.1 `libs/viewer-3d`): loads the GLB produced by the worker
(the schematic massing of `geometry.build_massing`, or the architect's IFC converted by
`geometry/ifc.py`), orbits around it, isolates floors and lets the user pick units (node
`extras.unit_id`). No framework binding library — a single component owns the renderer and disposes
it on destroy.

## The architectural look (ADR-0033)

`architectural-look.ts` draws what a BIM viewer draws, in the browser, with nothing added to the
model: a thin dark line on every edge of every element and a darkening where surfaces meet. Each
frame runs the chain

1. `GBufferPass`: the scene flat-shaded with a `MeshNormalMaterial` of each mesh's own side (the
   massing and the plan spaces are double-sided) into a half-float normal target with a depth
   texture; meshes flagged `userData.ghost` (units faded by the floor focus, drafts, the glass
   spaces of an IFC model) and line objects are left out; a mesh whose material carries the floor
   cut draws with a normal material carrying the same plane;
2. `RenderPass`: the colours, into a 4× multisampled target;
3. `GTAOPass` (full tier only): ambient occlusion from the same depth and normal textures,
   `AO_RADIUS_M` = 2 m, 16 samples, denoised;
4. `EdgePass`: an edge where a neighbouring pixel is farther by more than `EDGE_DEPTH_RELATIVE`
   (2 %) of the depth, or where the normals differ by more than `EDGE_NORMAL_DEGREES` (20°); the
   nearer pixel owns a silhouette line, so lines stay one pixel wide; the sky draws none;
5. `OutputPass`: sRGB to the canvas, alpha kept so the host's sky gradient shows through.

`renderTier(deviceFacts())` decides once per viewer: `full` on WebGL2 with no data saver, at least
4 GB of `deviceMemory` (or a browser that does not say) and a viewport of at least 768 px; `edges`
on any other WebGL2 device; `plain` (the renderer alone) without WebGL2. The pixel ratio is capped
at 1.5 in every tier (plan §7.3).

The massing model keeps the `EdgesGeometry` lines on its unit meshes: two units on one flat facade
have no depth step between them, and those lines are what separates them. The IFC model (nodes
with `ifc_class`, ADR-0032) gets no line geometry.

**Known gap.** Seams between coplanar faces of one merged mesh are not drawn (two cladding panels
of one colour in one plane read as one): ADR-0032 merges the elements of a group and colour, and a
screen-space pass sees no step there. Per-element seams need an element id per vertex in the GLB,
a converter change (BACKLOG).

**Measured** (2026-10-28, headless Chrome 156 on an Apple M2, N4 building A: 614,805 triangles,
158 meshes, 0.83 MB Draco): 60 fps, vsync-bound, on both tiers, at 1440 × 700 CSS px and a
device pixel ratio of 1.5 (full) and 600 × 700 at 2 (edges); about 100 MB of JS heap with the model
loaded. The massing of A-9/10 (99 units) at the same size: 60 fps on `edges`, 52–55 on `full`
under a load average of about 6. Phones: not measured.

## A picked floor of the IFC model is cut open (ADR-0036)

The IFC model merges each element class and colour across all storeys, so a storey cannot be hidden.
With a floor picked, one horizontal clipping plane (`floor-cut.ts`) removes the model above
`PLAN_CUT_M` = 1.2 m over the floor's lowest space, or half the floor's height when the floor is lower
than 2.4 m. The plane sits on every material of the model from load on (at `NO_CUT_Y` when nothing is
cut, so a floor change recompiles no shader), with `clipShadows`; the ground, the site features and
the trees are never cut. The spaces are glass in an IFC model, never opaque: 40 % on the picked floor
and on every floor when none is picked, 55 % hovered, 75 % selected. They cast no shadow, and a
polygon offset draws the picked floor's base over the slab it lies on (without it the slab flickered
through the tint); it is off on the uncut building, where it pulled the top floor's tint through the
roof finish 0.1 m above it (#D3). The other floors' spaces are not drawn (`colorWrite` off) but stay tappable below the cut and
show at 30 % when hovered; a ray hit above the cut is ignored. Below the cut a hit on the picked
floor wins over a nearer one on another floor (`pickedHit`, #D4): adjacent storeys' spaces share a
face, so a tap on a flat hit its floor and the ceiling of the flat below at the same distance. On a change of floor the camera keeps
its azimuth, aims at the floor's centre from 55° and the floor's diagonal; clearing the floor frames
the model again. A floor without spaces is not cut. The schematic massing keeps the fade.

**Section fill (ADR-0036 #D2).** The IFC materials are double-sided, so a cut wall would show its
own inner faces lit like its outside. Each opaque element that is not a space draws its back faces in
`SECTION_FILL` (#3b4048) between 0.5 m below the picked floor's base and the cut, so cut walls,
columns and doors read solid dark, as on a plan. One `onBeforeCompile` hook and one pair of uniforms
per viewer serve every such material: moving the band is one uniform write, no recompile, no added
draw. Glass and the spaces keep their look; with no floor picked the band is at `NO_CUT_Y` and
nothing changes.

**Known look.** The fill is the element's inside seen through the cut, not a plane at the cut: it is
flat only because it is unlit. An open element in the band (one that is not a closed solid) shows
its back faces dark too; none did on N4.

**Measured** (2026-10-29, headless Chrome on an Apple M2, the portal building page of N4 at
1440 × 1000 CSS px and a device pixel ratio of 1.5, full tier): 60 fps with level 0, 2 or 3 cut;
the same with the section fill (level -2, 0 and 2).

## Tests

`architectural-look.spec.ts` proves the tier rule (desktop, a browser without `deviceMemory`, a
data-saver phone, a 2 GB device, a narrow viewport, no WebGL2) and that the edge shader declares
every uniform it samples. `floor-cut.spec.ts` proves the cut height (a floor with spaces, a low floor,
a floor without spaces), the space opacity per state, that the camera keeps its azimuth over a
cut floor, the section fill's band and which materials take it, and that a tap takes the picked
floor's space on a tie with the floor below. The fill's shader hook is checked
in headless Chrome with the chain. `massing-viewer.spec.ts` proves the component degrades to a status line
without WebGL. The chain itself cannot run in the test browser (no WebGL context); it is checked on
the dev stack in headless Chrome.

The library is consumed from source through the workspace `tsconfig.json` path mapping; the
`ng-packagr` build target is available for publishing it separately.
