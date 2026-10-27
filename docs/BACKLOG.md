# Backlog

State on 2026-10-27: 41 open items across ADR-0006, 0007, 0008, 0010, 0011, 0012, 0013, 0014, 0015, 0016, 0017, 0019, 0020, 0022, 0025, plan Phases 5 to 7 and
the plan's open questions. The ADRs own the items; this file owns the order. A row is deleted when its item
is ticked in its ADR; a new item goes into its ADR first, then here. Rows that share one code area or one
outside input are one row with every reference. Sizes: S up to a day, M a few days, L a week or more.
*Needs* names the outside input, or "—".

Decided out on 2026-10-26 by the owner: a Signify integration and a block level between building and floor
(blocks stay buildings). Automating the setup checklist from a permit import (ADR-0017 proposal 1b) was
decided out the same day and reopened, widened to manual intake, on 2026-10-27 (ADR-0025).

## P0 — fix now

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 2 | Acceptance of DXF intake on a real ArchiCAD export: zones as fills, labels decoded, `from_file` calibration within 1 % of the printed scale. | ADR-0006 #B8 | owner's DXF file | S |
| 3 | Pick the DWG converter: `libredwg` (GPL, separate container), ODA File Converter (free binary, licence terms), or none. | ADR-0006 #D2 | owner's decision | — |

## P1 — before go-live

| # | Task | Ref | Needs | Size |
|---|---|---|---|---|
| 4 | DWG conversion: accept `.dwg`, converter container, `cad.convert_dwg` task, docs; then acceptance on 10 real DWG files reviewed by the owner. | ADR-0006 #D1 #D3 #D4 #D5 #D6 | item 3, owner's files | M |
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
| 32 | Sample project `permit-1127975`: the owner sets the ADR-0014 data on building A (construction status, completion text, terms, the elevation drawing for the floor picker, entrances) so the portal shows them; checks the map position (OSM cluster of the street's `19/x` buildings, ±100 m), refines the 11 site features and the four facade regions drawn by eye from the general plan, and closes apartments №3 and №15 (no closed outline). | ADR-0016 #E1 (done, approximate) | owner's review | S |
| 33 | First real generated 3D plan render on the sample project once a Gemini API key is in `secrets/ai_image_api_key` and `UF_AI_IMAGE_PROVIDER=gemini`: verify the response parser against the live answer, judge the image against the reference, approve or reject. | ADR-0017 #E1 | owner's API key | S |
| 34 | Contract steps for the release after migrations 0015 and 0017: stop mirroring facade choices into `projects.site_frame.facades`, migrate leftovers, drop the key and the fallback in `geometry.facade_assignments` (ADR-0016 E5); stop mirroring the layout code into `units.attributes.layout`, read only `units.layout_id`, drop the key and `layout` from `rules.ATTRIBUTE_FIELDS` (ADR-0022 E1). | ADR-0016 #E5, ADR-0022 #E1 | the 0015 and 0017 releases deployed | S |
| 35 | Tile provider or self-hosted tiles for the portal map once traffic justifies it or OSM withdraws access (the `UF_PORTAL_MAP_EMBED` switch covers the gap; runbook written). | ADR-0016 Revisit (E4 done) | traffic figures, provider pick | M |
| 36 | The architect's IFC export for `permit-1127975` (ArchiCAD: File → Save as → IFC, zones as IfcSpace) uploaded under building A, spaces linked; the portal then shows the real building. | ADR-0017 #E2 | the architect's file | S |
| 37 | Second image provider (OpenAI GPT Image) for a quality and price comparison; batch pricing when volumes grow. | ADR-0017 #E3 | owner's wish | S |
| 38 | UX pass on the pages the owner names (he sends the page or a screenshot with one sentence each). Done 2026-10-26: Projects (compact fields, top-aligned form rows, even cards); unit page (price and terms in one card, packed rows, two-column buyer toggles, 25 % shorter); unit page richer (plan card with availability colours, same-floor and same-layout links, live price per m², header facts, toned card icons). | ADR-0009 (patterns) | owner's pages | S per page |
| 39 | ADR-0019 (several developers on one general area): the owner picks Option A (one tenant, project-restricted members, per-project contacts) or Option B (platform area aggregating tenants); then its action items. | ADR-0019 Decision | owner's pick | S (A) / L (B) |
| 40 | "Process again" on the document card for a revision queued, processing or failed, with its guide line; the manual escape hatch next to the 10-minute sweep. | ADR-0016 #F5 | — | S |
| 41 | Long Georgian file names on the `local` storage backend: URL-quoting makes 9 bytes per letter and exceeds the 255-byte path component ("File name too long" on 2 of 16 permit files, 2026-10-26); cap or hash in `storage.object_key`. S3 is unaffected. | ADR-0016 #F6 | — | S |
| 42 | ADR-0020 (renovation playground): the owner picks how the drawn furniture is cleared (generated blank plan, DXF layers, fade), whether tenants manage the catalogue, whether layouts wait for buyer accounts and whether buyers may spend AI images; the sharing code length (4 symbols or 6 digits) and who opens a live board; then Phase B (blank plan, M), C (catalogue, M), D (after Phase 5, M), E2 to E8 (live board over SSE, M). Phase A and E1 (editor, code catalogue, fade, browser save, share link) done 2026-10-26. | ADR-0020 Decision | owner's picks | S to M per phase |
| 43 | ADR-0025 open items: the first live geocoding of the sample project's address with `UF_GEOCODER=nominatim` (judge the pin; cadastral route if Georgian addresses resolve poorly); the first live classification call against `UF_AI_CLASSIFY=true` (verify the text-answer parser); run the solver on a fresh import of `permit-1127975` in the dev stack and record per pass what it decided and left, tuning the thresholds in `autopilot/rules.py` only with a fixture that reproduces the case; facade sides from axis labels. | ADR-0025 #D1 #D2 #D3 | owner's dev stack, a Nominatim run, an API key | S to M |
