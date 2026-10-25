# Backlog

State on 2026-10-26: 31 open items across ADR-0006, 0007, 0008, 0010, 0011, 0012, 0013, 0014, 0015, plan Phases 5 to 7 and
the plan's open questions. The ADRs own the items; this file owns the order. A row is deleted when its item
is ticked in its ADR; a new item goes into its ADR first, then here. Rows that share one code area or one
outside input are one row with every reference. Sizes: S up to a day, M a few days, L a week or more.
*Needs* names the outside input, or "—".

## P0 — fix now

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 1 | Dev-stack verification run: `STORAGE_BACKEND=s3` against Garage (upload, process, publish, delete a document and a project, watch `storage.delete_prefix` empty the bucket prefix; closes the unverified S3 branch and PoC V6) and a browser pass with screenshots over the ADR-0014 screens (facade floor picker, site plan by construction status, Terms, entrance filter, table view, building "Shown to buyers" row) after publishing a project and opening the Preview link. | ADR-0012 #A1, ADR-0005 (pending PoC V6), plan PoC V6, ADR-0014 Revisit | dev stack up, a published project | S |
| 2 | Acceptance of DXF intake on a real ArchiCAD export: zones as fills, labels decoded, `from_file` calibration within 1 % of the printed scale. | ADR-0006 #B8 | owner's DXF file | S |
| 3 | Pick the DWG converter: `libredwg` (GPL, separate container), ODA File Converter (free binary, licence terms), or none. | ADR-0006 #D2 | owner's decision | — |

## P1 — before go-live

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 4 | DWG conversion: accept `.dwg`, converter container, `cad.convert_dwg` task, docs; then acceptance on 10 real DWG files reviewed by the owner. | ADR-0006 #D1 #D3 #D4 #D5 #D6 | item 3, owner's files | M |
| 5 | Retention sweep (`housekeeping.retention` is a stub): drafts, attempts, soft-deleted media, orphaned storage prefixes including `pub/` of retired publications. | ADR-0012 Consequences (known gap), plan §10.3, §12.3 | — | M |
| 6 | Phase 5: buyer email-code auth through the BFF, app sessions, inquiries, leads, assignment, notifications via outbox, consent, rate limits. PoC V1 first. | plan Phase 5, ADR-0002 (pending PoC V1) | O5, O6 decisions | L |
| 7 | Phase 6: domain lifecycle (add, DNS instructions, `domains.verify` job, activation, removal with certificate purge) and its admin screen; only the `ask` decision and host routing exist. | plan Phase 6, ADR-0003 | PoC V2 on a team-owned domain | M |
| 8 | Worker health: Procrastinate heartbeat check so `worker-light` and `worker-heavy` stop running with `healthcheck: disable`. | plan §17, `compose.yaml` comment | — | S |
| 9 | Phase 7: restore drill from a real dump written into `restore.md`, load test of the portal endpoints, ASVS L2 review of auth, session and tenancy. | plan Phase 7, runbooks | production host (item 10) | M |
| 10 | Hosting target and region: single EU VPS with containers, or managed Postgres and S3. Decides backup design. | plan O1 | owner's decision | — |
| 11 | Transactional enqueue: `defer_async` is not part of the request transaction (worked around with the row guard in `storage.delete_prefix`); decide whether to keep the pattern or enqueue through the request connection. | ADR-0004 (pending PoC V5), ADR-0012 Decision 5 | — | S |
| 12 | `ng lint` is listed in AGENTS.md but no ESLint config exists: add `angular-eslint` or drop the line. | AGENTS.md rule 7 | — | S |
| 13 | Document kind set by hand on a project-level file: queue the floor re-suggestion so the sheets are usable without a new revision. | ADR-0008 #7 | — | S |
| 14 | IFC exports without a declared length unit: refuse or warn; show the unit in the model stats. | ADR-0006 #E7 | — | S |
| 15 | Request-path hygiene: the IFC link confirmation rewrites the GLB inside the request, and permit preview and import hold a database connection across the registry call; move both into jobs. | ADR-0006 #E3, ADR-0007 #8 | — | S |

## P2 — after

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 16 | Level-marker reading on real sheets: unsigned basement markers ("0.55" printed without "-"), split-level blocks stacked vertically on one sheet with block names from the text near the markers, and a legend column of markers that reads as a block (require labels or line work in the column's region). | ADR-0010 Revisit, ADR-0013 Revisit, ADR-0013 #6 | the pilot building, a real sheet | M |
| 17 | Review after the first three real projects: the document classification keyword table and per-page split, and the permit import fieldset → kind table and label map. | ADR-0008 Revisit, ADR-0007 #9 | three real drawing sets and permit imports | S |
| 18 | Massing rebuilds: a minimum interval per project if a project with thousands of units makes builds slow. | ADR-0011 Revisit | a measurement | S |
| 19 | IFC performance on a real export: tessellation through the iterator with threads, and Draco in the browser measured on a ≈ 10 MB model on desktop Chrome, iOS Safari and a mid-range Android (PoC V7) with the `<model-viewer>` fallback. | ADR-0006 #E5, ADR-0006 C2a, plan PoC V7 | a real IFC, devices | M |
| 20 | Remaining open questions: O2 countries and currencies, O3 reservations, O4 email provider, O7 marketing site, O8 pilot developer. | plan §1 O2–O8 | owner's decisions | — |
| 21 | Unitless DXF with a printed scale: derive the sheet size from the scale before manual calibration. | ADR-0006 #E1 | a real DXF | S |
| 22 | Georgian glyphs on the DXF preview raster: ship a Georgian font in the worker image. | ADR-0006 #E2 | — | S |
| 23 | IFC view: cut or fade the envelope above the isolated floor (interior view). | ADR-0006 #E4 | — | M |
| 24 | Place the IFC model on the site so the project page can show it in the site frame. | ADR-0006 #E6 | placement of the building | M |
| 25 | Massing page refresh after outline changes (poll or push). | ADR-0011 #5 | — | S |
| 26 | Warn before deleting the document that holds a building's elevation sheet: ADR-0012 refuses only mapped documents, the FK clears `elevation_sheet_id` and the floor picker disappears at the next publication. | ADR-0014 Revisit | — | S |
| 27 | Entrance proposed from the drawing: the stair-core labels next to the units on the plan, confirmed like the unit labels. | ADR-0014 Revisit | a real sheet with entrance labels | M |
| 28 | Drawn footprints for planned buildings, so a house without drawings shows grey on the site plan as on lisihouse.ge. | ADR-0014 Revisit, plan §7.1 | — | M |
| 29 | Second portal language (Georgian and English on one host): per-field translations of the editable texts, language switch. | ADR-0014 Revisit, plan §2.3 R3 | — | L |
| 30 | OAuth 2.1 for the MCP server: Ory Hydra as the authorization server next to Kratos, login and consent in the admin app, the SDK's `AuthSettings` and RFC 9728 metadata, client registration; tokens stay for scripts. Decided on 2026-10-26 to follow the tokens, not replace them. | ADR-0015 Option C (Revisit) | an OAuth-only client; owner's go | L |
| 31 | MCP beyond projects and buildings: tools for documents, mapping and sales, a `delete_*` family with an explicit confirmation argument, the buyer-side read-only server. | ADR-0015 Revisit (Option A) | owner's pick | M |
