# ADR-0029: Publish with defaults: one click on the checklist or a switch at intake makes the first portal version live; one calibration serves a whole document

- **Status:** accepted (2026-10-27, the owner's "3" on the options of the same day, then "also make it an option while creating the project"; implemented 2026-10-27 on branch `adr-0029`)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §11.2 (Projects, Setup screens), §12.3 (`setup.autopilot`), §13.1 (document → published project), §13.2 (automation classification), ADR-0012 (publication flags, permanent delete), ADR-0016 (gallery), ADR-0017 (setup checklist), ADR-0022 (layouts), ADR-0025 (the setup solver), ADR-0028 (the vision route for what the rules cannot read)

## Context

The owner's goal, stated on 2026-10-27 after two days with the setup solver: "my goal is to have some
published pre-configured portal, after that possibility to make some adjustment". ADR-0025 built the
opposite end state on purpose: the solver leaves drafts and proposals for review, approves a sheet only
when every printed label is outlined, and never publishes. What the code does today (read 2026-10-27):

- **The solver stops short of the portal.** `autopilot/service.run_autopilot` runs eleven passes and
  records decisions; units it outlines are `draft` unless `approve_sheets` is on and the sheet is fully
  covered (`passes/outlines.py`); plan types are `unit_layouts.status = proposed` and share nothing
  (ADR-0025 Decision 6); no unit gets `publication_status = published`; nothing calls
  `publishing.publish`. On the owner's `test2` (permit 1127975 uploaded as four files) the solver's
  run of 06:27 left 88 drafts and 10 proposed plan types; the owner then set three kinds, approved
  four sheets, marked the units and published by hand: about twenty clicks across four screens.
- **Publishing is one service call with a readiness gate.** `publishing.publish(db, project, mode,
  actor)` refuses with 422 while `readiness()` has an `error` item; today the only error is "No units
  are marked for publication". Warnings (drafts marked public, no description, no renders, no site
  plan, no massing) publish fine. `set_unit_publication(all_active=True, status="published")` marks
  every active unit; a hidden unit stays linkable, an unpublished one is left out. Prices stay the
  sales team's: an available unit without a price shows "price on request" (ADR-0025 Decision 9).
- **The checklist already knows the publish step.** `publishing/setup.py` ends with the step
  `publish` ("Published to the portal": `done` when a publication is live, `attention` with the
  blocking messages, else "Preview, then publish the first version"); the Setup page shows it with
  the solver's decisions (ADR-0025 Decision 7).
- **Calibration is per page.** `passes/calibration.py` calibrates a sheet only from its single printed
  scale (`hints.scales`). The Jan Homeri set (`nino`, 2026-10-27) prints its scale through a legacy
  CAD font that comes out as single glyphs, so neither the 27 plan pages nor the site plan have a
  scale, and a person calibrates them one by one with two clicks each
  (`PATCH /sheets/{id}/calibration`, `geometry.calibration_from_points`, stored as `m_per_px` against
  the sheet's raster size). A probe of a dimension-string calibration on the same day (consecutive
  metre values in one row, their spacing against the page) gave the right 1:100 as the median on the
  permit's plan pages but with only 20 of 68 pairs within 2 %, and a standard-scale vote picked 1:125
  on one page: not a 0.8-confidence source without the dimension-line geometry, and nothing at all on
  a legacy-font set.
- **Roles.** `publication` PUBLISH is the right that publishes; `mapping` APPROVE approves sheets;
  `sales` WRITE confirms layouts. The solver acts as the person who asked (ADR-0025 Decision 3), so
  whoever switches "publish with defaults" on must hold all three.

## Decision

1. **"Publish with defaults" is one action that ends with a live portal.** It is a solver run
   (trigger `publish_defaults`) whose passes run as usual and which ends with a `defaults` pass that,
   in order: approves every sheet whose current boundaries are all the solver's and still drafts
   (`inventory.approve_sheet`, whatever the coverage); confirms every proposed plan type
   (`sales.layouts.confirm`); writes a project description when neither `description` nor
   `portal_settings.hero_text` exists, from facts the project knows (name, address line, buildings
   with their floor counts, the permit's application number and decision date), marked "needs you"
   so the person replaces it; marks every active unit `published`
   (`publishing.set_unit_publication(all_active=True)`); publishes (`publishing.publish(mode =
   "publish")`). Prices are not touched (ADR-0025 Decision 9: "price on request"). Each step is a
   decision with its confidence; the publication is `accepted` with the version and the portal
   address, or `skipped` "needs you" with the blocking messages when readiness refuses.
2. **Two doors, one right set.** `POST /projects/{id}/setup/publish-defaults` (202, the run) is the
   checklist's button, usable any time (it publishes a new version). The project switch
   `setup_auto.publish_defaults` (ADR-0025 Decision 2's JSONB, no migration) is the intake form's
   third switch: the first run that finishes with nothing left processing and **no publication yet**
   ends with the `defaults` pass; later runs leave publishing to the person, who adjusts and
   publishes by hand. Both doors require `project` WRITE, `mapping` APPROVE, `sales` WRITE and
   `publication` PUBLISH, since the worker acts as the person (403 otherwise, as ADR-0025 Decision 2).
3. **One calibration per document.** When a person has calibrated a sheet, the calibration pass gives
   the same calibration (`m_per_px` scaled by the raster width ratio when the rasters differ) to every
   sibling sheet of the same document that has the same page size (`width_pt`, `height_pt` within
   0.5 pt), no printed scale and `calibration_status = none`, with `calibration.source = sibling`
   and `from_sheet_id`, confidence 0.8. Siblings of another page size are one "needs you" line. A
   printed scale still wins, and a person's calibration is never replaced.
4. **The checklist stays the review surface.** The `defaults` decisions appear under the `publish`
   step (`CHECKLIST_STEP["defaults"] = "publish"`); the Setup page's "Publish with defaults" button
   asks for confirmation with the list of what it will do; the Projects page's cards carry the third
   switch under the two solver switches.

5. **Every "needs you" line says what to do and opens the place.** The owner's words on
   2026-10-27: "in some cases there is a need to make some approval/change/set but I can't understand
   what to do". Each decision with `needs_you` carries `todo`, one imperative sentence
   (`rules.TODO_OF_STEP` per step, a pass may give a more specific one); the Setup page shows it as
   "To do:" under the line and its button names the place ("Open sheet p.5", "Open Documents"),
   deep-linking to the sheet when the decision names one. Checklist steps keep their detail as the
   instruction.

## Options considered

### Option A: publish first on every run, unlisted
Pros: no click at all. Cons: every processed document would republish; "unlisted" does not exist at
project level (units are `published` or `hidden`, `published_units.listed`), so half-right data would
reach the tenant host; the owner's reply was "3".

### Option B: publish first only above a floor (one building with floors, one unit)
Pros: never a portal with an empty chooser. Cons: the floor is arbitrary; a project without labelled
units still deserves its project page; folded into Option C as the readiness gate that already exists.

### Option C: one click on the checklist, plus the same as an intake switch for the first version (chosen)
Pros: the person chooses the moment, or chooses it once at intake; one action replaces about twenty
clicks; the existing readiness gate and audit rows cover it. Cons: a project published with defaults
shows drafts approved by a rule and a description a person has not written, until adjusted; the
first version stays "on request" for prices.

### Option D: dimension-string calibration
Rejected on the probe of 2026-10-27 (Context): the median is right, the agreement is not, and a wrong
scale distorts every area silently. Revisit with the full dimension-line geometry or the vision route
(ADR-0028).

## Trade-off analysis

| | A every run | B with a floor | C click + switch | D dimensions |
|---|---|---|---|---|
| Clicks to a live portal | 0 | 0 or many | 1, or 0 with the switch | unchanged |
| Risk of a wrong public state | highest | medium | one confirmed moment, readiness gate | wrong areas |
| New code | small | small | small (one pass, one endpoint, one switch) | large, uncertain |

## Consequences

**Easier:** a project goes from drawings to a live portal in one action; the Jan Homeri set needs two
clicks for its 27 plan pages instead of 54.

**Harder:** reviewers must know that "published with defaults" is a state: approved drafts, confirmed
plan types and a generated description are live until adjusted; the checklist marks the description
"needs you" and the readiness warnings stay visible.

**Revisit:** reading the printed scale off the page image for legacy-font sets (ADR-0028's residue
passes); an unlisted project state if a developer wants a live-but-hidden portal.

**Out of scope here:** prices and availability (sales), the vision route, dimension-line geometry.

## Action items

### Phase A: backend
- [x] A1 `autopilot/passes/defaults.py`: approve, confirm, describe, mark, publish; decisions under
      step `defaults`; `rules.DEFAULTS_*` confidences; `CHECKLIST_STEP` and `LINK_OF_STEP`;
      `rules.TODO_OF_STEP` and `SetupDecisionOut.todo` (Decision 5).
- [x] A2 `autopilot/service.py`: `Context.publish_defaults`; the run ends with the `defaults` pass when
      the run's switch says so, or when the project switch is on and no publication exists yet.
- [x] A3 `api/admin_setup.py`: `POST /projects/{id}/setup/publish-defaults` (202); `PUT .../setup/auto`
      accepts `publish_defaults` and checks the three rights; `SetupAutoIn/Out`.
- [x] A4 `passes/calibration.py`: sibling calibration (Decision 3).
- [x] A5 Tests in `tests/test_autopilot.py`: `test_publish_with_defaults_makes_the_first_version_live`
      (approved, confirmed, described, marked, published, the checklist step `done`, pm 403),
      `test_the_intake_switch_publishes_the_first_version_once`, `test_a_persons_calibration_serves_the_sibling_pages`.

### Phase B: admin app and docs
- [x] B1 `api-client.ts`: `publishSetupDefaults`, `SetupAutoIn.publish_defaults`; regenerated client.
- [x] B2 `setup.page.ts`: the button with its confirmation, the third toggle, the hint; `projects.page.ts`:
      the third switch on both cards; `guide-content.ts` entries.
- [x] B3 README status sentence, plan §11.2, §12.3, §13.2, `frontend/README.md` (no backlog row: the ADR has no open items).
