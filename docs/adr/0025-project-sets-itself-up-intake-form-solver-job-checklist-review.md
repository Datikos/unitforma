# ADR-0025: A project sets itself up: one intake form, a solver job that applies the confident proposals, and the setup checklist as the review surface

- **Status:** accepted (2026-10-27, the owner's "start implementing until finish" on the options of 2026-10-26; implemented 2026-10-27 on branch `adr-0025`, merged to `main` the same day; Phase D done 2026-10-27 (D1–D3 on the dev stack, D4–D5 the same day); no open items; this reverses the 2026-10-26 decision that put "automating the setup checklist from a permit import (ADR-0017 proposal 1b)" out of scope: the owner asked for it again, widened to manual intake)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner). Six picks were asked on 2026-10-26 and not answered before "start"; the defaults taken are named in Decision 9 and are his to change.
- **Plan reference:** §12.3 (jobs), §13.1 (document → published project), §13.2 (automation classification), §11.2 (admin screens), §21 (sources), ADR-0007 (permit import), ADR-0008 (classification), ADR-0010 (floors proposed), ADR-0011 (massing follows mapping), ADR-0013 (blocks), ADR-0016 Decision 2 (facades), ADR-0017 Decision 5 (checklist) and Option E (no wizard), ADR-0022 (layout registry)

## Context

The owner's request of 2026-10-26: "project creation simplification: the form asks the input data, after
that all checklist will be solved by AI, of course the similar layout matching". What the code does today
(read on 2026-10-27):

- **Two create paths, both stop early.** `projects.page.ts` creates a project from a slug and a name, or
  imports a tas.ge permit (ADR-0007) into a project with its address, one building and the current
  drawings. Neither collects a currency, a building code for a manual project, or drawings; the permit
  hint says "Floors are added by you".
- **Every step after processing waits for a click.** `publishing/setup.py` lists twelve steps. The data
  for most of them is already proposed: `documents/floor_proposal.py` reads storeys from the level
  markers but "floors are never created without a click" (ADR-0010); `documents/jobs._suggest_floors`
  writes `sheet_floors` rows with `status = suggested` and a region per floor; `mapping.suggest_for_sheet`
  returns unit candidates with a confidence (`FILL_CONFIDENCE` typed 0.95, parking 0.9, numbered 0.85;
  `LOOP_CONFIDENCE` typed 0.9; grown faces 0.7) that the sheet editor turns into draft units one by one
  through `inventory.create_unit_from_boundary`; `inventory.approve_sheet` activates them and queues the
  massing. Nothing proposes the site frame, the placement, the facade sides, the gallery flags, the map
  position or the layout codes.
- **The 0.7 candidates are not safe to apply.** Plan §13.2 records that grown outlines "reached the right
  areas but traded balcony and partition slivers between neighbours" on the pilot set. A wrong unit
  cannot be re-keyed (AGENTS.md rule 3); it goes through merge or split lineage.
- **The checklist is read-only.** `GET /projects/{id}/setup` computes `done | todo | optional |
  attention` per step from the data. ADR-0017 Option E rejected a wizard because the steps run for
  minutes and interleave with waiting; a page that always shows the state was preferred.
- **Layouts have a home but no matcher.** ADR-0022 made `unit_layouts` the registry and `units.layout_id`
  the link; codes are typed by staff. `unit_media` and `unit_renders` owned by a layout serve every member
  (ADR-0022 Decision 5), so a wrong cluster would put a wrong render on a buyer page.
- **Jobs and locks exist.** `geometry.service.queue_massing` defers with `queueing_lock =
  "massing:<project>"` so one build waits per project; `process_revision` runs in the worker and ends by
  proposing floors; `regulatory.import_attachments` queues one ingestion per file.
- **One outbound dependency pattern exists.** `renders/gemini.py` calls one fixed host with a timeout, a
  file-secret key, a per-tenant daily cap and a cost line shown in the UI (ADR-0017 Decision 4).
- The migration chain is at `0018_published_units_layout`.

Third-party facts (plan §21 holds the sources):

- Nominatim (nominatim.openstreetmap.org, usage policy read 2026-10-27): at most 1 request per second,
  a valid `User-Agent` identifying the application, no bulk geocoding, results cached where possible.
  The public instance "may be withdrawn", the same risk as the tile embed (ADR-0016 E4), so the provider
  is a setting with `none` as its default. **Unverified:** how well it resolves Georgian street
  addresses as the permit prints them.
- Gemini's `interactions` endpoint (ADR-0017) accepts an image plus text and can answer with text; the
  raw JSON shape of a text answer is **not documented** on the pages read for ADR-0017, so the client
  parses `steps[].type == "text"` defensively and records the top-level keys of an unexpected answer.
  Input images bill at $1.50 per 1M tokens (plan §21); a 1024 px thumbnail is about 1 300 tokens, so a
  page classification costs under $0.003.

## Decision

1. **One intake, two entry points, no third create path.** Both cards of the Projects page get a
   "Set up automatically" switch (default on) with a sub-switch "Approve mapped sheets when every
   printed label is matched" (default on). The manual card also collects the address line, the
   currency (tenant default pre-filled), a building code (default `A`) and optional drawings; the files
   go through the ordinary upload path (`createDocument`, upload intent, complete) and land as
   `unclassified` documents under the building, so classification and processing are what an upload
   gets. `ProjectCreate` gains `building_code` and `setup_auto`; `PermitImportCreate` gains
   `setup_auto`. After a create the app opens the project's setup checklist.
2. **The settings live on the project.** `projects.setup_auto` (JSONB, migration `0019`) holds
   `{"enabled": bool, "approve_sheets": bool, "requested_by": <user id>, "since": <iso>}`; `PUT
   /projects/{id}/setup/auto` changes it (project write; `approve_sheets = true` also needs `mapping`
   APPROVE, since the worker approves as the requesting person); switching it on queues a run.
3. **The solver is a job, never request-path code.** Task `setup.autopilot` on the `docs` queue,
   `queueing_lock = "autopilot:<project>"` (one run waits per project), `retry = 0`. Triggers: the end
   of `documents.ingest_revision` (processing done or partial), the end of
   `regulatory.import_attachments`, `PUT /buildings/{id}/floors` and `POST
   /floor-proposal/blocks` (in the API, after the floors are saved), the switch turned on, and `POST
   /projects/{id}/setup/run` (202). `documents.resuggest_floors` carries no trigger: the floors pass
   calls it inline and must not re-queue a run. A trigger only defers when `setup_auto.enabled` is
   true; `queue_run` lives in `autopilot/queue.py`, a leaf that imports only `core.db`,
   `tenants.models` and the jobs app lazily, so `documents` and `regulatory` can call it without an
   import cycle. **A run first checks the project's revisions: while any is `queued` or `processing`
   it records one decision "waiting for N document(s)" and exits**, so a permit import of 16 files
   never decides floors on 3 processed documents; the last ingestion's end triggers the real run.
   Each run writes one `setup_runs` row (`id, tenant_id, project_id, status queued | running | done |
   failed | waiting, trigger, requested_by, started_at, finished_at, summary JSONB, error,
   created_at`; RLS from `migrations/rls.py`). Passes run in order, each in its own transaction; a pass
   that raises is recorded in the summary and the next one runs. The actor of every write is
   `(requested_by, "autopilot")`, so audit rows, code history and approvals say who decided.
4. **The solver never changes what a person set.** It acts only on: buildings with no floors; sheets
   with no confirmed floor; sheets with no boundary drawn by a person (boundaries the solver creates
   carry `unit_boundaries.source = "autopilot"`; one current boundary with another source blocks the
   sheet); sheets with `calibration_status = none`; a project
   without `site_frame.sheet_id`; buildings `unplaced`; buildings without facade assignments;
   render documents still `internal`; a project without `address.lat`; units without `layout_id`.
   A person's later change is never undone by a later run: every run reads the accepted
   decisions of the earlier runs (`setup_runs.summary.decisions[].entity_id(s)`) and skips what it
   decided once, so a deleted proposed layout, an unlinked member, a render document set back to
   internal or a removed solver unit (the sheet is then the person's) stay as the person left them.
5. **Passes, rules and thresholds** (the run summary records every decision with `step, kind,
   entity, detail, confidence, needs_you, link`):

   | Pass | Acts when | Writes through | Confidence recorded |
   |---|---|---|---|
   | floors | `floor_proposal` returns storeys, none `unmatched_existing`; with `split_level` and ≥ 2 blocks (ADR-0013 Decision 4) the one building gets the merged storey list when every storey is at least `FLOOR_MIN_HEIGHT_M` (2.2 m) and the split is listed as "needs you"; smaller steps set nothing. Never `accept_blocks`: on permit 1127975 the markers showed five blocks where the owner kept one building (changed 2026-10-27, D3) | `projects.set_floors`, then `resuggest_floors` | 0.9; 0.8 when the roof is not found |
   | calibration | exactly one printed scale in `hints.scales`, page size known, status `none` | `inventory.recalibrate_sheet` with `calibration.source = "printed_scale"` (a 1 m error on a 42 m sheet is 2.4 %) | 0.85 |
   | sheet floors | one suggested floor; or several, each with a region | `assignments.confirm_suggestions(source = "autopilot")` | 0.9 single, 0.85 regions |
   | outlines | candidate `confidence ≥ 0.85` (typed fills and loops; numbered fills, a zone with a number and its printed area, since 2026-10-27: 30 of 30 right on the storage floor of permit 1127975, D3), its label key not seen twice on the sheet, overlap with an existing boundary < 0.3 | `inventory.create_unit_from_boundary(source = "autopilot")`, drafts, printed area kept, type from the label | the candidate's |
   | approve | `approve_sheets` on, every current boundary of the sheet has `source = autopilot`, every labelled candidate of the sheet is covered by a boundary | `inventory.approve_sheet`, then `queue_massing` | min of the sheet's candidates |
   | site plan | exactly one processed `site_plan` document and no site frame | `projects.update_project(site_frame.sheet_id = page 1)` | 0.9 |
   | placement | site sheet calibrated, footprint known; a face of the site sheet within 25 % of the footprint area; best IoU after rotation search ≥ 0.9 → `confirmed`, 0.8 to 0.9 → `draft` (needs you) | `projects.update_building(site_transform, placement_status)` | the IoU |
   | facades | stacked-marker sheets of the building (`elevation_candidates`), each with a drawn width in metres from its line work; widths match the two side lengths of the footprint rectangle within 5 % and the match is unique | `projects.update_building(facades)` with `flip = false` | 0.6, flagged "verify which of the two parallel sides" |
   | gallery | processed `render` documents `internal` | `documents.update_document(visibility = public)` | 0.9 |
   | map | `UF_GEOCODER != none`, address line present, no `lat`; three forms of the address in turn, 1.1 s apart (as written; street, number, city; street and city): the answers of a form within 150 m of each other are one place, the street alone is no pin (D1, 2026-10-27) | `projects.update_project(address.lat/lng, address.geocoded = {provider, display_name, query, places})` | 0.7 |
   | layouts | apartments with `polygon_m` and no `layout_id`; outlines in metres, centred, aligned on the minimum-area rectangle, four orientations and the mirror; IoU ≥ 0.95 and printed areas within 8 % join a cluster; clusters of ≥ 2 | `sales.layouts.create(status = proposed, source = autopilot, match)` and `units.layout_id`; a mirror cluster gets code `<code>m`, name "Mirror of <code>", `match.mirror_of` | the cluster's minimum IoU |
   | classify | `UF_AI_CLASSIFY` on, document `kind_source = pending` after processing, first page is a drawing: ≥ 50 vectors and either ≤ 800 characters or ≥ 2 vectors per character (text-only pages never leave the host: a permit decision names people, ADR-0007 Decision 3) | `documents.update_document(kind)` with `kind_source = "ai"` | 0.8 |

6. **A proposed layout shares nothing until confirmed.** `unit_layouts` gains `status` (`confirmed` |
   `proposed`, default confirmed), `source` (`manual` | `autopilot`) and `match` JSONB. Media upload
   and render requests on a proposed layout answer 409 `layout-proposed`; the snapshot writes
   `layout = null` for units of a proposed layout, so the portal (ADR-0024 plan types, filters) never
   shows one. `POST /layouts/{id}/confirm` sets `confirmed`; delete with `unlink_units = true` rejects
   it. The Layouts page shows proposed layouts first with their members, the matched IoU and a
   "Confirm" button; the unit form's picker lists them with a "proposed" marker.
7. **The checklist is the review surface, not a wizard.** `GET /projects/{id}/setup` adds `auto`
   (`enabled, approve_sheets, running, last_run {status, trigger, started_at, finished_at, error}`),
   per step `auto_detail` (what the last run did for it, or what it left for the person) and
   `decisions[]` of the latest run, lowest confidence first, `needs_you` items first of all. The page
   gains the two switches, "Run now", a "Decided for you" card with a filter by step and a toggle
   "only what needs me", and polls every 5 s while a run is queued or running. Statuses stay the four of
   ADR-0017; a step done by the solver keeps `done` and says so in `auto_detail`.
8. **Outbound calls are settings with `none` defaults and fixed hosts.** `UF_GEOCODER` (`none` |
   `nominatim`, default `none`), `UF_GEOCODER_ENDPOINT` (default
   `https://nominatim.openstreetmap.org/search`), one request per run, `User-Agent:
   unitforma/<version> (+https://unitforma.com)`, 10 s timeout, TLS verification on.
   `UF_AI_CLASSIFY` (default `false`) uses the ADR-0017 provider (`UF_AI_IMAGE_PROVIDER`, key, host) with
   its own cap `UF_AI_CLASSIFY_DAILY_LIMIT` (default 200 pages per tenant per UTC day); the provider
   interface gains `describe(image, mime, prompt) -> str`.
9. **Defaults taken for the six picks of 2026-10-26** (each is one setting or one line to change):
   (1) proposal 1b is reopened and widened; (2) sheets are auto-approved only under the complete-coverage
   rule, and the sub-switch turns it off; (3) prices are **not** defaulted to "on request": the step
   stays the sales team's; (4) mirrors get their own code with an `m` suffix, no mirrored image; (5)
   geocoding ships behind `none`; (6) vision classification ships behind `false` and sends drawing
   pages only.

## Options considered

### Option A: a deterministic solver that applies the existing proposals above thresholds, plus four new matchers, reviewed on the checklist (chosen)

Pros: testable on the existing PDF fixtures, no cost per project, no drawing leaves the host unless
switched on, every decision reversible with the normal tools, the checklist and its statuses stay.
Cons: gives up on messy sheets and hands them to the person; two new matchers (placement, facades) are
geometry heuristics that will need the first real projects to tune.

### Option B: an LLM agent over the MCP server drives the steps

Pros: handles odd cases by reasoning over titles and text. Cons: needs the document, mapping and sales
tool families (backlog #31), is not deterministic, cannot be tested on fixtures, costs tokens and
minutes per project, and the drawings leave the host. Kept as a staff-assistant idea, not the pipeline.

### Option C: a vision model reads every sheet

Pros: page kinds and facade titles in any language. Cons: imprecise on geometry (outlines, scale),
every page leaves the host, a per-page cost. Taken only for the residue (Decision 5 "classify"),
behind a switch.

### Option D: a wizard that walks the person through the steps

Rejected in ADR-0017 Option E and unchanged: the steps are long-running and interleaved with waiting.

### Option E: do nothing; the checklist already shows the order

Pros: zero risk. Cons: the owner configured the sample project through the API because twelve screens
in order is too much; the request is explicit.

## Trade-off analysis

| Axis | A (chosen) | B agent | C vision | D wizard | E nothing |
|---|---|---|---|---|---|
| Testable on fixtures | yes | no | partly | yes | — |
| Cost per project | 0 (geocoding and classification optional) | tokens and minutes | per page | 0 | 0 |
| Data leaves the host | only with a switch on | drawings | every page | no | no |
| Handles messy sheets | hands them over | sometimes | sometimes | no | no |
| Reversible decisions | every one, audited | depends | depends | n/a | n/a |
| Fits long-running steps | yes (job + state page) | yes | yes | poorly | — |

## Consequences

**Easier:** a permit import or a manual upload becomes a project with floors, confirmed sheets, draft
or active units, a site frame, a placed building, a gallery and plan types without opening eight
screens; the checklist tells the person what the solver could not decide and why.

**Harder:** during a rolling update the previous release ignores `unit_layouts.status`: an API
container of that release building a snapshot reads every layout as confirmed and would publish a
proposed layout's code and plan type; the exposure is one publish in the update window, replaced
by the next publish from the new release. Reviewers hold three rules. A pass must refuse anything a person set (Decision 4); a layout
with `status = proposed` must never reach the snapshot or own media; thresholds (0.9 outlines, 0.95
layouts, 0.9 and 0.8 placement) are constants in one module and change only with a fixture that shows
why. Operations: two optional outbound hosts, each a setting that defaults to off, each with a usage
policy to keep. A run is one job per project and per trigger, so a 51-page permit import queues about
51 runs of which the lock collapses all but the waiting one; the pass work is proportional to the
project's sheets and units, bounded by the same data the checklist already reads.

**Revisit:** facade sides from axis labels once a real set with "ფასადი ღერძებში 1-9" titles is at
hand; the vision classifier's live response shape at the first call; placement for buildings without a
single face on the site plan (hatched roofs); layout facts (rooms, areas) summarised on the proposed
layout; an MCP tool that reports the checklist and runs the solver.

**Out of scope here:** prices (a product decision the owner has not taken); publishing (always a
click); the architect's IFC model; AI-detected outlines from rasters; an agent over MCP; a mirrored
copy of a layout's render.

## Action items

### Phase A: schema, settings, solver core

- [x] A1 Migration `0019_setup_autopilot.py` (expand): `projects.setup_auto` JSONB default `{}`;
      table `setup_runs` with RLS and index `(project_id, created_at desc)`; `unit_layouts.status`,
      `source`, `match`; `documents.kind_source` check gains `ai`. Models in `tenants/models.py`.
- [x] A2 `core/settings.py`: `geocoder`, `geocoder_endpoint`, `ai_classify`, `ai_classify_daily_limit`.
- [x] A3 New module `autopilot/`: `queue.py` (leaf: `queue_run`, enabled check), `service.py` (run
      row, processing guard, pass loop, decision record), `rules.py` (thresholds as named constants),
      `passes/floors.py`, `calibration.py`, `sheets.py`, `outlines.py`, `site.py`, `placement.py`,
      `facades.py`, `gallery.py`, `geocode.py`, `layouts.py`, `classify.py`; `jobs.py` body; task
      `setup.autopilot` in `jobs/tasks.py`.
      *Found while implementing:* the job carries the project, not the run, and executes the oldest
      queued `setup_runs` row when it starts, so the queueing lock can collapse a burst of triggers
      into one waiting job without ever dropping the row the checklist shows (an `AlreadyEnqueued`
      on a run-carrying job would have lost it). `documents.resuggest_floors` reads line counts from
      `sheets.hints.vectors`, which the worker never writes; the classify pass reads the page extract
      instead (the existing quirk in `resuggest_floors` is left as it was).
- [x] A4 `documents/assignments.confirm_suggestions`; `sales/layouts.create` with status and source;
      `sales/media` and `renders/service` refuse proposed layouts; `publishing/snapshot` drops the
      code of a proposed layout; `renders/provider.describe` and `renders/gemini.describe`.
- [x] A5 Triggers: `documents/jobs.process_revision` and `regulatory/service.import_attachments`
      call `autopilot.queue.queue_run` at their end; `api/admin_projects.set_floors` and
      `accept_blocks` after saving; `PUT /setup/auto` when switched on.
- [x] A6 API: `api/admin_setup.py` with `PUT /projects/{id}/setup/auto`, `POST
      /projects/{id}/setup/run`, `GET /projects/{id}/setup/runs`; `GET /setup` extended;
      `POST /layouts/{id}/confirm`; `ProjectCreate.building_code` and `setup_auto`,
      `PermitImportCreate.setup_auto`; schemas `SetupAutoIn/Out`, `SetupRunOut`, `SetupDecisionOut`.
- [x] A7 Tests `tests/test_autopilot.py` (9 tests): the matcher clusters rotations and tells mirrors
      apart; placement finds rotation and translation; facade widths need distinct side lengths; the
      classifier's one-word answers and the Gemini text block parser; the intake creates the building
      and the switches and a project manager cannot ask for approval (403); one run on a two-page plan
      and a 1:500 site plan sets floors (0, 3.2 m), calibrates from the printed scale, outlines three
      units, approves the complete sheet and leaves the bare "7" (0.65) as "needs you", picks the
      site frame, places the building (confirmed), publishes the render document and geocodes
      through a stub; the proposed layout L1 (3 units) refuses media and renders, hides its code from
      the row and the rules, and confirmation reverses that; a person's floor is never touched and a
      processing revision makes the run wait; the vision stub names a kind for a drawing page only,
      within the daily cap; a deleted proposed layout, a removed solver unit and a render set back
      to internal stay so after the next run; a page with table rules and a paragraph of text is
      never sent to the classifier. `setup_runs` gets the standard policies through
      `enable_tenant_rls`; `test_rls.py` exercises the policy set on `portal_domains` only.
- [x] A8 `openapi.json` and `npm run api:generate`.

### Phase B: admin app

- [x] B1 `pages/projects.page.ts`: switches, address, currency, building code, drawings; upload after
      create; navigate to the checklist. Guide `projects` entry.
- [x] B2 `pages/setup.page.ts`: switches, "Run now", `auto_detail` per step, "Decided for you" card
      with filters, polling while running. Guide `setup` entry.
- [x] B3 `pages/layouts`: proposed layouts first, members, IoU, Confirm; unit form picker marker.
- [x] B4 `api-client`: `setSetupAuto`, `runSetup`, `listSetupRuns`, `confirmLayout`.

### Phase C: deploy and docs

- [x] C1 `compose.yaml` and `.env.example`: `UF_GEOCODER`, `UF_GEOCODER_ENDPOINT`, `UF_AI_CLASSIFY`,
      `UF_AI_CLASSIFY_DAILY_LIMIT`; secrets README unchanged (the key is the ADR-0017 one).
- [x] C2 README status and decision list; plan §11.2 (Projects, Setup), §12.3 (`setup.autopilot`),
      §13.2 (the "auto" column), §21 (Nominatim policy); `frontend/README.md`; `docs/BACKLOG.md`
      header and the replaced "decided out" line.

### Phase D: done 2026-10-27

*Not done on 2026-10-27:* a screenshot pass over the Projects, Setup and Layouts pages (the dev
stack runs the `main` images; the branch was verified by `ng build admin`, `ng test admin` and the
backend tests, not in a browser).

- [x] D1 First live geocoding of the sample project's address with `UF_GEOCODER=nominatim`: judge the
      pin; if Georgian addresses resolve poorly, try the cadastral code route (napr.gov.ge) in a
      follow-up.
      *Found on 2026-10-27:* Nominatim has no answer for the register's form "ქალაქი თბილისი, ლეო
      კვაჭაძის ქუჩა, N 19გ" and three answers (19/4, 19/5, 19/6, within 40 m) for "ლეო კვაჭაძის ქუჩა 19,
      თბილისი"; the street alone resolves to two segments 600 m apart. `geocode.address_queries` now
      tries the three forms and `places_agree` (150 m) replaces "exactly one result"; the pin landed at
      41.74338, 44.72236, 40 m from the owner's hand-set pin on `permit-1127975` (41.7437, 44.7224).
      No cadastral route needed for this address.
- [x] D2 First live classification call: verify the text-answer parser against the live response.
      *Found on 2026-10-27:* the real elevation sheet of permit 1127975 (uploaded as "scan 0001", no
      kind) never left the host: its first page has 4 676 characters of dimensions, notes and title
      block against the 800-character cap, and the pass said nothing. The guard is now
      `classify.page_is_drawing`: at least 50 vectors and either ≤ 800 characters or ≥ 2 vectors per
      character (`CLASSIFY_MIN_VECTORS_PER_CHAR`; the sheet has 64 444), and the documents kept on
      the host are one "needs you" line. The live call then returned the one word `elevation`
      (`gemini-nano-banana-2.1`, one request, 200 OK); `parse_kind` took it, the document became
      `elevation` with `kind_source = ai`, the audit row holds the answer.
- [x] D3 Run the solver on `permit-1127975` (a fresh import in the dev stack) and record per pass what
      it decided and what it left; tune the thresholds only with a fixture that reproduces the case.
      *Record of 2026-10-27 (project `adr-0025-d3-1127975`, deleted afterwards; the owner's hand-made
      `permit-1127975` as the reference):* classify 0 (every import is classified by its fieldset);
      floors: five split-level blocks A–E accepted as buildings where the owner has one building A
      with B1, Ground, 1, 2, 3 → **changed**: blocks stay a proposal, the merged storey list (which
      equals the owner's) is applied when every storey is ≥ 2.2 m (`test_split_level_blocks_stay_a_proposal`);
      calibration: 30 plan pages and the site plan from the printed scale; sheet floors: 8 pages,
      16 assignments; outlines: pages 2–5 gave 34, 9, 11, 10 drafts (owner: 37, 11, 11, 10), page 1
      gave 0 because its 30 storage zones are numbered fills at 0.85 (owner: 30 units) → **changed**:
      threshold 0.85, page 1 then gave 27 (`#12` zone in `_plan_pdf`); "needs you" lists on every
      sheet repeat the digits 0–7 and `M2` as "labels printed twice" (room numbers and axis marks,
      not units: open as D4); site plan: the one site plan, 0.9; placement: no match for the split
      blocks (0.44, 0.66), the owner placed the one building by hand; facades 0 (needs the placed
      building); gallery 0 (renders arrive as `permit` kind from the fieldset); location: see D1;
      layouts: 10 proposed plan types from 64 apartments, L1 (6 units) to L7, three mirror types,
      IoU ≥ 0.96 (the owner has no layouts yet to compare). Two gaps fixed on the way: the run that
      follows one processed document ran while the import was still downloading the next (the guard
      now counts `regulatory_imports.status = importing`, `test_import_creates_project_building_and_documents`);
      one attachment download took about 80 min against `DOWNLOAD_TIMEOUT_S = 300`, which bounds a
      read, not the whole file (D5).
- [x] D4 Outlines: the "labels printed twice" list names room numbers and axis marks (0–7, `M2`) on
      every sheet; a label that repeats on most sheets of a set is not a unit label. Tune with a
      fixture that prints the same digit on two zones of two pages.
      *Done 2026-10-27:* `outlines.run` reads every sheet's candidates first; a label printed twice
      on at least 2 sheets and on half the sheets with candidates (`LABEL_SET_WIDE_MIN_SHEETS`,
      `LABEL_SET_WIDE_SHARE`) is dropped from the labels and from the coverage rule; printed twice on
      one sheet it is still listed. Fixture: the axis mark "4" at both ends of both pages of
      `_plan_pdf` (`_axis_marks`); page 1 is still approved, page 2 lists only "7".
- [x] D5 `regulatory/tasge.py`: bound the whole download (a total deadline next to `DOWNLOAD_TIMEOUT_S`),
      so a slow server cannot hold the import worker for an hour; record it in `stats.failed`.
      *Done 2026-10-27:* `DOWNLOAD_TOTAL_TIMEOUT_S = 900` (50 MB at 0.5 Mbit/s) around the whole
      transfer in `TasgeClient._capped`; past it a 504 "Download took too long" that the import loop
      already records in `stats.failed`; `test_download_has_a_deadline_for_the_whole_file`.
