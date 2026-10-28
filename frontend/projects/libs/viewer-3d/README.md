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

1. `GBufferPass`: the scene flat-shaded with a `MeshNormalMaterial` into a half-float normal target
   with a depth texture; meshes flagged `userData.ghost` (units faded by the floor focus, drafts)
   and line objects are left out;
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
loaded. Phones: not measured.

## Tests

`architectural-look.spec.ts` proves the tier rule (desktop, a browser without `deviceMemory`, a
data-saver phone, a 2 GB device, a narrow viewport, no WebGL2) and that the edge shader declares
every uniform it samples. `massing-viewer.spec.ts` proves the component degrades to a status line
without WebGL. The chain itself cannot run in the test browser (no WebGL context); it is checked on
the dev stack in headless Chrome.

The library is consumed from source through the workspace `tsconfig.json` path mapping; the
`ng-packagr` build target is available for publishing it separately.
