# Backlog

State on 2026-10-26: 36 open items across ADR-0006, 0007, 0008, 0010, 0011, 0012, 0013, 0014, plan Phases 5 to 7 and
the plan's open questions. The ADRs own the items; this file owns the order. A row is deleted when its item
is ticked in its ADR; a new item goes into its ADR first, then here. Sizes: S up to a day, M a few days,
L a week or more. *Needs* names the outside input, or "—".

## P0 — fix now

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 1 | Run the dev stack once with `STORAGE_BACKEND=s3` against Garage: upload, process, publish, delete a document and a project, and watch `storage.delete_prefix` empty the bucket prefix. Closes the unverified S3 branch and PoC V6. | ADR-0012 #A1, ADR-0005 (pending PoC V6), plan PoC V6 | dev stack up | S |
| 2 | Acceptance of DXF intake on a real ArchiCAD export: zones as fills, labels decoded, `from_file` calibration within 1 % of the printed scale. | ADR-0006 #B8 | owner's DXF file | S |
| 3 | Pick the DWG converter: `libredwg` (GPL, separate container), ODA File Converter (free binary, licence terms), or none. | ADR-0006 #D2 | owner's decision | — |

## P1 — before go-live

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 4 | DWG conversion: accept `.dwg`, converter container, `cad.convert_dwg` task, docs. | ADR-0006 #D1 #D3 #D4 #D6 | item 3 | M |
| 5 | DWG acceptance on 10 real files reviewed by the owner. | ADR-0006 #D5 | owner's files | S |
| 6 | Retention sweep (`housekeeping.retention` is a stub): drafts, attempts, soft-deleted media, orphaned storage prefixes including `pub/` of retired publications. | ADR-0012 Consequences (known gap), plan §10.3, §12.3 | — | M |
| 7 | Phase 5: buyer email-code auth through the BFF, app sessions, inquiries, leads, assignment, notifications via outbox, consent, rate limits. PoC V1 first. | plan Phase 5, ADR-0002 (pending PoC V1) | O5, O6 decisions | L |
| 8 | Phase 6: domain lifecycle (add, DNS instructions, `domains.verify` job, activation, removal with certificate purge) and its admin screen; only the `ask` decision and host routing exist. | plan Phase 6, ADR-0003 | PoC V2 on a team-owned domain | M |
| 9 | Worker health: Procrastinate heartbeat check so `worker-light` and `worker-heavy` stop running with `healthcheck: disable`. | plan §17, `compose.yaml` comment | — | S |
| 10 | Phase 7: restore drill from a real dump written into `restore.md`, load test of the portal endpoints, ASVS L2 review of auth, session and tenancy. | plan Phase 7, runbooks | production host (O1) | M |
| 11 | Hosting target and region: single EU VPS with containers, or managed Postgres and S3. Decides backup design. | plan O1 | owner's decision | — |
| 12 | Transactional enqueue: `defer_async` is not part of the request transaction (worked around with the row guard in `storage.delete_prefix`); decide whether to keep the pattern or enqueue through the request connection. | ADR-0004 (pending PoC V5), ADR-0012 Decision 5 | — | S |
| 13 | `ng lint` is listed in AGENTS.md but no ESLint config exists: add `angular-eslint` or drop the line. | AGENTS.md rule 7 | — | S |
| 20 | Document kind set by hand on a project-level file: queue the floor re-suggestion so the sheets are usable without a new revision. | ADR-0008 #7 | — | S |
| 21 | IFC exports without a declared length unit: refuse or warn; show the unit in the model stats. | ADR-0006 #E7 | — | S |
| 32 | Browser pass with screenshots over the ADR-0014 screens: facade floor picker, site plan by construction status, Terms, entrance filter, table view, building "Shown to buyers" row; publish a project and open the Preview link. | ADR-0014 Revisit | dev stack up, a published project | S |

## P2 — after

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 14 | Floors from drawings: unsigned basement markers ("0.55" printed without "-"). | ADR-0010 Revisit | the pilot building | S |
| 15 | Document classification: review the keyword table and the per-page split after three real drawing sets. | ADR-0008 Revisit | three real sets | S |
| 16 | Split-level blocks stacked vertically on one sheet; block names from text near the markers. | ADR-0013 Revisit | a real sheet | M |
| 17 | Massing rebuilds: a minimum interval per project if a project with thousands of units makes builds slow. | ADR-0011 Revisit | a measurement | S |
| 18 | Draco in the browser: measure a ≈ 10 MB IFC model on desktop Chrome, iOS Safari and a mid-range Android (PoC V7); `<model-viewer>` fallback. | plan PoC V7, ADR-0006 C2a | devices | S |
| 19 | Remaining open questions: O2 countries and currencies, O3 reservations, O4 email provider, O7 marketing site, O8 pilot developer. | plan §1 O2–O8 | owner's decisions | — |
| 22 | Unitless DXF with a printed scale: derive the sheet size from the scale before manual calibration. | ADR-0006 #E1 | a real DXF | S |
| 23 | Georgian glyphs on the DXF preview raster: ship a Georgian font in the worker image. | ADR-0006 #E2 | — | S |
| 24 | IFC link confirmation rewrites the GLB inside the request: move it to a geometry job. | ADR-0006 #E3 | — | S |
| 25 | IFC view: cut or fade the envelope above the isolated floor (interior view). | ADR-0006 #E4 | — | M |
| 26 | IFC tessellation through the iterator with threads; measure on a real export first. | ADR-0006 #E5 | a real IFC | M |
| 27 | Place the IFC model on the site so the project page can show it in the site frame. | ADR-0006 #E6 | placement of the building | M |
| 28 | Permit preview and import hold a database connection across the registry call: fetch in a job. | ADR-0007 #8 | — | S |
| 29 | Permit import: review the fieldset → kind table and label map after three real imports. | ADR-0007 #9 | three real imports | S |
| 30 | Massing page refresh after outline changes (poll or push). | ADR-0011 #5 | — | S |
| 31 | A legend column of level markers can read as a split-level block: require labels or line work in the column's region. | ADR-0013 #6 | a real sheet | S |
| 33 | Warn before deleting the document that holds a building's elevation sheet: ADR-0012 refuses only mapped documents, the FK clears `elevation_sheet_id` and the floor picker disappears at the next publication. | ADR-0014 Revisit | — | S |
| 34 | Entrance proposed from the drawing: the stair-core labels next to the units on the plan, confirmed like the unit labels. | ADR-0014 Revisit | a real sheet with entrance labels | M |
| 35 | Drawn footprints for planned buildings, so a house without drawings shows grey on the site plan as on lisihouse.ge. | ADR-0014 Revisit, plan §7.1 | — | M |
| 36 | Second portal language (Georgian and English on one host): per-field translations of the editable texts, language switch. | ADR-0014 Revisit, plan §2.3 R3 | — | L |
