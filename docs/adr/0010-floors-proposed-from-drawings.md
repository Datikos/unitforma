# ADR-0010: Floors are proposed from the drawings' level markers

- **Status:** accepted (2026-10-25; implemented 2026-10-25)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §13.2 "Page → floor" row, §3.5 (floors with `level`, `elevation_m`, `height_m`), §11.3 massing

## Context

The owner's question on 2026-10-25: after a PDF upload, what produces the floors and the 3D model?
Answer from the code: nothing automatic. Floors come from "Generate floors" on the project page
(lowest level, highest level, one height; no elevations), sheets are matched to floors by level
markers only when floors already exist, and the massing is built on approval from the floors'
elevations or, without them, from stacked heights with a 3.0 m default.

What `main` has:

- `documents/levels.py` finds level markers ("+3.20", "-4.05 (652.2)") per sheet, drops title-block
  repeats across pages, recognises stacked markers (sections, elevations) and matches markers to
  floors by `elevation_m` within 0.02 m; `_suggest_floors` in `documents/jobs.py` stores every
  sheet's cleaned markers in `sheets.hints.level_markers`.
- `projects.set_floors` creates missing levels and updates existing ones, never deletes, audited.
- `geometry.service.floor_elevations` prefers `elevation_m` and stacks `height_m` otherwise.
- The pilot set (plan §13.2 notes) prints a marker on every plan sheet and the full stack on
  sections; the basement marker of one block is printed without a sign.

## Decision

1. **A floor proposal per building, computed on demand from stored markers.**
   `GET /buildings/{id}/floor-proposal` reads `level_markers` of every non-excluded, non-duplicate
   sheet of the building's documents (current revisions), plus the sheets of project-level
   floor-plan documents when the project has one building besides SITE, and returns proposed
   floors. No new table: the proposal is derived data and recomputed after every processing run.
2. **Storeys from clusters.** Marker values within 0.25 m form one storey (elevation = median,
   rounded to 0.01 m). A storey needs at least one marker from a plan sheet (markers of that sheet
   not stacked); a storey seen only on sections or elevations is the roof when it is the topmost
   and then sets the last floor's height, otherwise it is dropped. Heights are the difference to
   the next storey up; the top floor takes the roof, else the median height of the others, else
   3.0 m.
3. **Numbering as the project does it.** The storey nearest 0.00 (within 0.5 m) is level 0
   "Ground"; else the lowest storey at or above zero. Storeys above count up ("1", "2"), below
   count down ("B1", "B2"), matching "Generate floors".
4. **Existing floors are respected.** A storey within 0.05 m of an existing floor's elevation is
   `existing` (that floor's level and name are kept); a storey whose level number matches an
   existing floor without elevation is `update` (fills elevation and, when empty, height); the
   rest are `new`. Existing floors with no storey are listed as `unmatched` and left alone.
5. **Accepting uses the floors endpoint that exists.** The admin page sends the chosen rows to
   `PUT /buildings/{id}/floors`; `set_floors` creates and updates, the audit row says
   `set_floors`. No second write path.
6. **Admin page.** Each building card shows "Floors proposed from the drawings: N" with a table
   (level, name, elevation, height, status, how many sheets support it), checkboxes on by default
   for `new` and `update`, and one "Accept N floors" button; a line explains where the numbers
   come from and that heights can be edited after accepting. The card disappears when every
   storey is `existing`.

## Options considered

- **O1 (chosen): on-demand proposal from stored markers, accepted through `set_floors`.** Pros:
  no schema, no job, uses what the worker already stores, one click. Cons: computed on every
  project-page load (a few sheets, milliseconds).
- **O2: create floors automatically during processing.** Rejected: the owner's rule is that he
  enters structure; a wrong automatic floor set would move units.
- **O3: a `floor_proposals` table written by the worker.** Pros: history. Cons: a table and a
  status machine for data that is cheap to recompute; `sheets.hints` already is the history.
- **O4: read storey heights from the sections' dimension strings.** Deferred (idea 3 in the
  conversation): markers already give heights as differences.

## Consequences

**Easier.** A building's floors, with elevations and heights, come from the drawings in one click;
level-marker matching then works exactly; massing uses real elevations.

**Harder.** Two more rules for reviewers to know: section-only storeys are roofs, and a storey
within 0.25 m of another is the same storey (split levels closer than that are not told apart).

**Operations.** None.

**Revisit.** After the pilot building: unsigned basement markers ("0.55" printed without "-") and
whether to show the proposal on the sheet editor too. Split-level blocks side by side are handled by
ADR-0013 (2026-10-26).

**Out of scope here:** creating buildings from drawings, floors for project-level sets with
several blocks (markers cannot be attributed to a block without regions), heights from sections.

## Action items

- [x] 1 `documents/storeys.py`: clustering, roof rule, numbering, matching to existing floors;
      tests `test_floor_proposal.py` (pilot-like stack with basement and roof, split-level block,
      existing floors without elevations, nothing when no markers).
- [x] 2 `documents/floor_proposal.py`: gather markers for a building, build the proposal.
- [x] 3 API `GET /buildings/{id}/floor-proposal`, schema `FloorProposalOut`; OpenAPI regenerated.
- [x] 4 Admin `project-detail.page.ts`: proposal table per building with accept; API client method.
- [x] 5 Docs: plan §13.2 row and note, README status.
      *Found while implementing (2026-10-25):* this ADR was numbered 0009 for about an hour and
      renumbered to 0010 when ADR-0009 (admin shell and design system) landed in the same working
      tree from another session; every reference was updated. Two markers of one storey printed
      0.02 m apart give the median elevation (+3.20 and +3.22 → 3.21), which the test records.
      *Found on the pilot set (2026-10-26):* the sheets were processed before the floors existed,
      so accepting the proposal left every sheet unassigned; `PUT /buildings/{id}/floors` now queues
      `documents.resuggest_floors`, which re-runs the page → floor suggestions from the markers
      stored in `sheets.hints` (confirmed assignments untouched). The pilot's three split-level
      blocks (+0.00 / +1.00 / +2.00 side by side on each sheet) came out as 17 storeys of 1.0 m in
      one building: the clustering has no notion of blocks yet (listed under Revisit); the card says
      so and the user accepts one block's storeys or models the blocks as separate buildings. The
      proposal table itself was lost when another session rewrote the project page on 2026-10-25
      and was put back on 2026-10-26.
