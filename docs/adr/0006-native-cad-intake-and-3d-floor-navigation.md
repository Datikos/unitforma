# ADR-0006: Native CAD intake (DXF, DWG, IFC) beside PDF, and floor-first 3D navigation in the portal

- **Status:** accepted (2026-10-25; Phase A implemented 2026-10-25; Phase B implemented 2026-10-25 except the real-file acceptance B8; Phases C and D open; DWG backend B1 `none` until the owner picks otherwise)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner); the DWG conversion option needs his licence decision
- **Plan reference:** §1.1, §2.1, §2.2, §4.2, §7.3, §13.2, Phase 8

## Context

The product concept, restated by the owner on 2026-10-25: a developer uploads AutoCAD or ArchiCAD
documents (and PDFs), the platform builds the building in 3D, a buyer opens the portal, picks a floor on
the 3D building, then picks the exact apartment on that floor's plan.

What `main` does today (commit 84d6289):

- `documents/service.py` `ALLOWED_MIME` accepts PDF, PNG, JPEG, WEBP, GLB, IFC and `octet-stream`. DXF
  and DWG are refused with 415. IFC and GLB are stored as document revisions and nothing processes them:
  `pyproject.toml` has no IFC library and `jobs/tasks.py` has three tasks (`documents.ingest_revision`,
  `mapping.propose_revision_diff`, `geometry.build_massing`), none of them for models.
- The PDF path (`documents/processing.py` `extract_page`) writes one `extract.json` per page with
  `words` (text with normalised `x0,y0,x1,y1`), `segments`, `rects`, `fills` (normalised rings with
  colour), `page_pt` and `hints`. `mapping/suggest.py` reads only those keys to propose unit outlines
  (filled zones first, then closed loops grown to the printed area). `documents/levels.py` reads
  `words` for level markers. Nothing downstream knows the extract came from a PDF.
- The pilot drawing set is ArchiCAD exported to PDF; its zones arrive as fills and matched printed areas
  to 0.1 m² (plan §13.2 notes). **Unverified:** that the same zones arrive in ArchiCAD's DXF export as
  closed `LWPOLYLINE` or `HATCH` entities on zone layers, and in its IFC export as `IfcSpace`; this is the
  documented behaviour of both exporters, not yet observed on a pilot file (checked by item B8).
- The 3D model is `geometry/massing.py`: every approved unit polygon is extruded between its floor
  elevation and height into one glTF node per unit, grouped per building, labelled "Schematic model
  generated from floor plans — not an architectural model". The GLB `extras` carry `unit_id`, `code`,
  `unit_type`, `floor_level`. `geometry_models.kind` already allows `massing_generated | glb_source | ifc`.
- The portal (`projects/portal`) shows the massing on the project page; a click on a unit solid
  navigates straight to the unit page (`project.page.ts:51`, `:158`). The building page
  (`building.page.ts`) has the floor stack and the 2D plan with unit polygons, driven by `?floor=`.
  `libs/viewer-3d` `MassingViewerComponent` already has `floorLevel` and `selectedUnitId` inputs and a
  `unitPicked` output, so floor isolation and unit highlight are plumbed but not used for navigation.
- Worker image: `backend/Dockerfile` on `python:3.14-slim`, `requires-python >= 3.13`. Compose runs
  `worker-light` (queues `default,docs,mail,periodic`) and `worker-heavy` (`docs-heavy,geometry,geometry-heavy`).

Third-party facts checked on 2026-10-25:

| Component | Licence | Fit with the image | Source |
|---|---|---|---|
| ezdxf 1.4.5 | MIT | `cp314` wheels plus a pure-Python `py3` wheel on PyPI; reads DXF R12 to R2018; does not read DWG | pypi.org/pypi/ezdxf/json; ezdxf docs |
| IfcOpenShell 0.9.0.post1 | LGPL-3.0-or-later | `py314` `manylinux_2_31` wheels on PyPI (`requires_python >=3.10,<3.16`) | pypi.org/pypi/ifcopenshell/json |
| ODA File Converter | proprietary, free download; ODA FAQ: non-members may use it for non-commercial applications only; ODA does not distribute it for embedding | would run as a separate container; commercial SaaS use is **not** covered by the free terms as far as the FAQ states | opendesign.com FAQ "What are ODA Viewer and ODA File Converter?" (**unverified** beyond the FAQ text; the full EULA was not read) |
| LibreDWG 0.13.x (`dwg2dxf`) | GPL-3.0-or-later | reads DWG r1.2 to r2018 ("99 %" per its manual); DXF output "mostly implemented", AutoCAD fails to import some of it | gnu.org/software/libredwg manual |

AGENTS.md rule 9: no AGPL in application images; GPL is acceptable only as an unmodified standalone
service. LibreDWG as a separate container invoked over a queue is such a service; linking it into the
worker is not.

## Decision

1. **Three intake routes, one review path.** The platform accepts PDF and images (unchanged), DXF, DWG
   and IFC. Every 2D route produces the same per-sheet `extract.json` (`words`, `segments`, `rects`,
   `fills`, `page_pt`, `hints`) plus a raster PNG, so `mapping/suggest.py`, `documents/levels.py`,
   the sheet editor, approval, lineage and the revision diff stay unchanged. No second review flow.
2. **DXF is read in-process with ezdxf (MIT).** New `documents/cad_dxf.py`: one sheet per layout
   (model space counts as page 1; paper-space layouts follow), entities `LINE`, `LWPOLYLINE`,
   `POLYLINE`, `ARC` and `CIRCLE` (flattened to segments), `HATCH` and closed `LWPOLYLINE` as `fills`,
   `TEXT`/`MTEXT` as `words` (legacy Georgian font decoding from `documents/labels.py` applied by
   font/style name), blocks exploded one level. Layer names are kept in each entity (`"layer"` key)
   and summarised in `hints.layers`. Drawing units from `$INSUNITS` and the entity extent set
   `page_pt` and a `calibration` of status `from_file`, so the two-point calibration step is
   pre-filled and may be skipped. The raster is drawn with Pillow from the same segments at
   `rasterize_page`'s long edge. Size cap: 50 MB per DXF, 200 000 entities per layout; above that the
   revision fails with a problem detail naming the limit.
3. **DWG is accepted and converted to DXF asynchronously in a separate container, never in the
   worker image.** The conversion backend is chosen by the owner (Options B1 to B3 below); until a
   backend is configured (`CAD_DWG_CONVERTER=none`) a DWG upload is accepted, stored, and its
   revision ends `processing_status = failed` with the problem detail "DWG conversion is not
   configured on this installation; export DXF from AutoCAD (SAVEAS → AutoCAD 2018 DXF) or
   ArchiCAD (File → Save as → DXF)". The converter container is reached over the job queue
   (`cad-convert` queue) by a `cad.convert_dwg` task, writes the DXF next to the DWG in object
   storage (`.../source.dxf`) and re-enqueues `documents.ingest_revision`. The converter image holds
   the unmodified converter binary plus a thin Python queue consumer (`tools/cad-converter/`) that
   calls the binary as a subprocess (mere aggregation, so the GPL reasoning above holds); it is
   resource-limited (1 CPU, 1 GB) and on the `internal` network only.
4. **IFC is Phase 8 pulled forward, as designed in plan §2.2 and J8.** New `geometry/ifc.py` using
   IfcOpenShell 0.9 (LGPL, unmodified, imported as a library in the `worker-heavy` image only):
   `IfcBuildingStorey` → floor candidates (name, elevation), `IfcSpace` → unit candidates (GlobalId,
   long name, storey, footprint polygon from the space's representation, net/gross area quantities
   when present), the whole building tessellated to one GLB per building with one node per
   `IfcSpace` and one node per non-space element group (walls, slabs, windows, roof), `extras`
   carrying GlobalId. Output `geometry_models.kind = ifc`, Draco-compressed by `gltf-transform`
   (planned in §4.2 but not installed today: `backend/Dockerfile` has no Node; added by item C2a),
   budget 15 MB per building, enforced by the job (a larger GLB fails with the size in `error`). A new `ifc_space_links` table (tenant_id,
   geometry_model_id, ifc_global_id, unit_id nullable, status `suggested | confirmed | rejected`,
   confidence) holds the reviewed matching of spaces to existing unit ids, suggested by storey +
   label + footprint overlap with the current `unit_boundaries` (reusing `mapping/diff.py` overlap
   logic). Unit ids, prices, leads and favourites are never touched by IFC import.
5. **Which 3D the buyer sees.** The portal shows the IFC-derived GLB for a building when a model of
   kind `ifc` is `ready` and `is_current`, else the massing GLB. The disclaimer badge changes with the
   kind: massing keeps "Schematic model generated from floor plans — not an architectural model"; IFC
   shows "Model from the architect's IFC export" and the revision date. Floor plans in 2D stay the
   source for unit outlines until the reviewer confirms a space link; a confirmed link adds the IFC
   footprint as a `unit_areas` entry with `source = ifc_quantity` and lets the unit's 3D node be
   highlighted.
6. **Floor-first navigation, no backend change.** A click on a unit solid in the project page 3D
   navigates to `/projects/{slug}/buildings/{code}?floor={level}&unit={code}`. The building page
   shows the 3D building (massing or IFC) beside the floor stack with the other floors faded
   (`floorLevel` input), the picked floor's units coloured by availability; a click on a floor in the
   stack or on a floor slab in 3D selects that floor; the 2D plan below shows that floor with the
   picked unit preselected (`selectedUnitId`); clicking a polygon or a solid selects the unit and
   shows its card with "Open". The unit page keeps the direct link. Phones and 2D fallback keep the
   stack-and-plan behaviour that exists today.
7. **Honesty rule.** A 2D source (PDF, DXF, converted DWG) can only ever yield the schematic model.
   Exact facades, windows and interior walls come only from IFC. The upload screen says this next
   to the file picker, and the plan §7.3 wording stays.
8. **Order of work.** 6 first (small, fulfils the buyer flow with what exists), then 2, then 4, then 3
   once the converter backend is chosen. Phase 5 (inquiries) follows unless the owner reorders.

## Options considered

### A. 2D CAD intake

- **A1 (chosen): DXF via ezdxf in the worker, DWG via a separate converter container.** Pros: MIT
  library, pure Python, same extract shape, the mapping engine already proved on the pilot zones.
  Cons: DWG still depends on a converter; one more file format to keep tests for.
- **A2: PDF only (status quo), tell developers to print to PDF.** Pros: nothing to build. Cons: the
  owner rejected it on 2026-10-25; CAD text in PDF loses font names on some exporters, and the
  scale must be calibrated by hand on every sheet.
- **A3: Convert DXF/DWG to PDF with a CAD tool and run the PDF path.** Pros: one extraction path.
  Cons: needs a renderer with a licence issue of its own, loses layers, drawing units and entity
  identity, which are exactly what DXF gives for free.

### B. DWG conversion backend (owner's decision, needed before Decision 3 is implemented)

- **B1: `CAD_DWG_CONVERTER=none`, DWG refused with export instructions.** Pros: zero cost, zero
  licence risk. Cons: an AutoCAD-only office has one more manual step per upload.
- **B2: ODA File Converter in a separate container.** Pros: the reference converter, every DWG
  version, DXF output AutoCAD accepts. Cons: the free terms cover non-commercial use only per ODA's
  FAQ; commercial SaaS use needs an ODA membership (price unverified, published by ODA to members).
  Not redistributable: the image must download it at build time from ODA.
- **B3: LibreDWG `dwg2dxf` in a separate container (GPL-3.0, unmodified standalone).** Pros: free,
  reads up to r2018, allowed by AGENTS.md rule 9 as a standalone service. Cons: DXF output quality
  is "mostly implemented" per its own manual; entity coverage on ArchiCAD-produced DWG unverified.
  Needs a 10-file acceptance set before it is trusted.
- **B4: Paid conversion API (CloudConvert, Autodesk Platform Services).** Pros: no container to
  operate. Cons: drawings leave the installation, against the self-hosted promise; per-file cost.

Recommendation: start with **B1** (it is the behaviour of Decision 3 with no backend) and run the
**B3** acceptance set on the pilot office's DWG files; adopt B3 if 9 of 10 convert with all zone
polylines intact, otherwise buy B2.

### C. IFC and exact 3D

- **C1 (chosen): IfcOpenShell as a Python library in `worker-heavy`, GLB per building, reviewed
  space matching.** Pros: LGPL unmodified, py314 wheel exists, planned since v0.1 (§2.2, J8).
  Cons: 6 to 8 weeks per the plan; large models need the heavy worker's memory (set 4 GB limit).
- **C2: `IfcConvert` static binary as a subprocess.** Pros: no Python binding. Cons: no access to
  properties and quantities without a second parse; the wheel removes the reason to prefer it.
- **C3: Keep massing only, exact 3D later (status quo).** Pros: nothing to build. Cons: the owner
  asked for the building in 3D "exact"; massing is schematic by construction.
- **C4: xeokit or another BIM viewer loading IFC in the browser.** Pros: no server conversion.
  Cons: AGPL or commercial licence for the frontend (plan §4.2), 50 MB+ IFC files on phones.

### D. Floor-first navigation

- **D1 (chosen): 3D pick goes to the building page with floor and unit preselected; building page
  gets the 3D view with floor isolation.** Pros: uses the existing inputs, no API change, one
  screen holds floor, plan and 3D together. Cons: the building page becomes heavier on desktop;
  three.js is already lazy-loaded.
- **D2: Keep the unit page as the 3D click target.** Pros: nothing to change. Cons: skips the floor
  step the owner asked for.
- **D3: Full 3D-only flow (floor slabs explode, apartments picked in 3D).** Pros: impressive.
  Cons: the 2D plan is the verified source of outlines; on massing models the 3D unit solid is
  the plan polygon anyway; worse on phones.

## Trade-off analysis

| Axis | A1 DXF+converter | A2 PDF only | B2 ODA | B3 LibreDWG | C1 IfcOpenShell | C3 massing only |
|---|---|---|---|---|---|---|
| Licence in app image | MIT | — | none (separate container, commercial terms needed) | GPL, separate container only | LGPL, unmodified import | — |
| New container | 0 (DXF), 1 (DWG) | 0 | 1 | 1 | 0 (heavy worker grows) | 0 |
| Image size growth | ~10 MB | 0 | ~150 MB (own image) | ~30 MB (own image) | ~120 MB in worker-heavy | 0 |
| Scale calibration | from file | manual | from file | from file | from file | — |
| Exact 3D | no | no | no | no | yes | no |
| Owner cost | 0 | 0 | ODA membership, unverified | 0 | 0 | 0 |
| Work size | M | — | S after B3 harness | M | L (6 to 8 weeks) | — |

## Consequences

**Easier.** Developers upload what the CAD tool exports without printing; scale comes from the file;
ArchiCAD offices get exact geometry from IFC; the buyer flow is floor → plan → unit on every device.

**Harder.** Three parsers to keep green with fixtures (one small DXF, one small IFC under `tests/`
built from synthetic geometry, never a client's file); a `worker-heavy` image with IfcOpenShell to
rebuild on each release; one more container if B2 or B3 is chosen; reviewers must hold the rule that
IFC never creates or deletes units by itself, only links to them.

**Operations.** `worker-heavy` memory limit rises to 4 GB for IFC tessellation; the converter
container has no inbound port and only the queue; a failed conversion is visible as the revision's
`processing_status = failed` with the reason in the documents screen.

**Revisit.** After the B3 acceptance set (10 real DWG files) decide B2 vs B3; after the first IFC
pilot measure GLB size per building against the 15 MB budget; when IfcOpenShell publishes 0.9.x
with `requires_python` covering 3.16 bump the image.

**Out of scope here:** buyer inquiries (Phase 5, unchanged), apartment interior walk-through,
self-redesign editor (plan §2.3), finishing catalogue (Phase 11), ArchiCAD `.pln` or AutoCAD
project files (proprietary; only exports are read), Revit `.rvt` (export IFC).

## Action items

Phase A: floor-first navigation (S, no backend)
- [x] A1 `project.page.ts`: `openUnit` navigates to the building page with `floor` and `unit` query
      params; keep the "Browse units" path.
- [x] A2 `building.page.ts`: add `uf-massing-viewer` with `floorLevel` and `selectedUnitId` bound to
      the page state; `unitPicked` selects the unit; read `unit` query param on load; hide 3D when
      `caps.prefer3d` is false.
- [x] A3 `massing-viewer.ts`: fade non-selected floors (opacity 0.15) when `floorLevel` is set;
      emit `floorPicked` when a solid on another floor is clicked.
- [x] A4 Portal spec tests for the navigation and the floor fade; `ng build portal` bundle check
      (3D chunk stays deferred).
- [x] A5 Docs: plan §7.1 navigation model, README status line.
      *Found while implementing (2026-10-25):* faded floors stay pickable so a buyer can move floors
      from the model, so the `floorPicked` output is informational and the building page acts on
      `unitPicked` alone. The massing GLB is one file per project; the building page loads the same
      file as the project page (browser-cached) and frames the focused building client-side, so a
      per-building GLB is not needed before IFC models (Phase C). `ng lint` has no target in this
      workspace and the committed portal files are not Prettier-formatted, so neither is a gate;
      `ng test portal` and `ng build portal` are.

Phase B: DXF intake (M)
- [x] B1 `pyproject.toml`: add `ezdxf>=1.4.5`; `uv lock`.
- [x] B2 `documents/service.py`: accept `application/dxf`, `image/vnd.dxf`, `.dxf` by extension when
      declared `octet-stream`; `processing.sniff_mime` detects the DXF header (`0\nSECTION`).
- [x] B3 `documents/cad_dxf.py`: `inspect_dxf` (layouts as pages), `extract_layout` producing the
      extract shape of Decision 2, `rasterize_layout` with Pillow; legacy font decoding by style name.
- [x] B4 `documents/jobs.py` `process_revision`: dispatch on mime; write `calibration` with status
      `from_file` when `$INSUNITS` is metres, centimetres or millimetres.
- [x] B5 Tests `test_dxf_intake.py`: a synthetic DXF with two zones as closed `LWPOLYLINE` and one
      `HATCH`, labels in `TEXT`, `$INSUNITS = 6`; asserts two fill candidates at confidence 0.95
      with the printed areas, calibration `from_file`, raster dimensions.
- [x] B6 Admin documents page: accepted-format list and the Decision 7 note next to the picker.
- [x] B7 Docs: plan §13.2 table gets a "DXF" row per step; README status.
      *Found while implementing (2026-10-25):* the file-derived calibration is stored with
      `calibration_status = calibrated` and `calibration.source = dxf_insunits` instead of a new
      `from_file` status, so the three consumers of the status (`mapping/service.py`,
      `inventory/service.py`, the revision diff inheritance) stay unchanged; the editor labels it
      "from the drawing units". Segments keep the flat `[x0, y0, x1, y1]` shape of the PDF extract;
      layer names live in `hints.layers` (counts) and on each fill, not on each segment. The DXF is
      parsed once per revision in `documents/jobs.py` and reused for every layout. Text boxes are
      estimated from the style height and ignore rotation. Binary DXF is refused with a message.
      Two gaps left open: a unitless drawing (`$INSUNITS = 0`) that prints "1:100" keeps its
      `page_pt` in raw drawing units, so areas compare wrongly until the reviewer calibrates by hand
      (calibrate before trusting suggestions); and the preview raster draws text with Pillow's default
      font, which has no Georgian glyphs, so decoded labels show as boxes on the PNG while the extract,
      the word list and the suggestions carry the right text.
- [ ] B8 Acceptance on a real ArchiCAD DXF export from the pilot office (owner provides the file, it
      stays outside git): zones arrive as fills, labels decode, calibration `from_file` within 1 % of
      the printed scale; result recorded here as "*Found while implementing*". Decision 2 is not done
      before this passes.

Phase C: IFC ingestion (L, plan Phase 8 pulled forward)
- [ ] C1 Migration `0009_ifc_space_links`: table of Decision 4 with RLS from `migrations/rls.py`;
      `unit_areas.source` gains `ifc_quantity`.
- [ ] C2 `pyproject.toml`: `ifcopenshell>=0.9.0` as an optional extra `ifc`; `backend/Dockerfile`
      target `worker-heavy` installs the extra; compose `worker-heavy` uses that target, memory 4 GB.
- [ ] C2a `backend/Dockerfile` target `worker-heavy`: Node 22 LTS runtime and `@gltf-transform/cli`
      (MIT) pinned, used as a subprocess; alternative if the image grows past 600 MB: a Python Draco
      encoder (`DracoPy`, Apache-2.0) and skip the CLI.
- [ ] C3 `geometry/ifc.py`: storeys, spaces with footprints and quantities, tessellation to GLB with
      per-space nodes; `gltf-transform` Draco step; stats (`spaces`, `storeys`, `glb_bytes`); fail the
      job when the GLB exceeds 15 MB.
- [ ] C4 `jobs/tasks.py` `geometry.ingest_ifc` on queue `geometry-heavy`; enqueued by
      `process_revision` for mime `application/x-step`; writes `geometry_models` kind `ifc`.
- [ ] C5 `geometry/service.py`: space → unit suggestions (storey match, label match, footprint IoU ≥
      0.5 via `mapping/diff.py` overlap), endpoints `GET/PUT /projects/{id}/ifc-links`.
- [ ] C6 Admin page `ifc-links.page.ts`: list of spaces with suggested unit, confirm/reject, 3D
      preview with the space highlighted.
- [ ] C7 `publishing/snapshot.py`: pick the current `ifc` model per building when `ready`, else
      massing; carry `model_kind` and disclaimer text; portal badge from `model_kind`.
- [ ] C8 Tests `test_ifc_ingest.py` with a synthetic IFC4 file (two storeys, three spaces) built by
      IfcOpenShell in the test; asserts storeys, spaces, GLB node names, suggestion to an existing
      unit by label; unit ids unchanged after confirm.
- [ ] C9 Docs: plan §2.2 and Phase 8 marked as pulled forward with this ADR's number; §7.3 R2 line;
      README status; runbook note on `worker-heavy` memory.

Phase D: DWG conversion (M, after the owner picks B1, B2 or B3)
- [ ] D1 `documents/service.py`: accept `application/acad`, `image/vnd.dwg`, `.dwg`; sniff `AC10`
      header; revision waits in `processing_status = converting`.
- [ ] D2 Setting `CAD_DWG_CONVERTER = none | libredwg | oda` in `core/settings.py`; `.env.example`
      line with the Decision 3 message when `none`.
- [ ] D3 `deploy/cad-converter/Dockerfile` (one per backend chosen) and compose service
      `cad-converter` on queue `cad-convert`, `internal` network, 1 CPU, 1 GB.
- [ ] D4 Task `cad.convert_dwg`: fetch DWG, run converter, store `source.dxf`, enqueue ingest;
      failure → `failed` with the converter's stderr first line.
- [ ] D5 Acceptance set: 10 real DWG files from the pilot office converted and reviewed by the owner;
      result recorded under this ADR as "*Found while implementing*".
- [ ] D6 Docs: plan §13.2 "DWG" row; `deploy.md` for the converter container; README status.
