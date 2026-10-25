# ADR-0013: Split-level blocks drawn side by side become separate buildings

- **Status:** accepted (2026-10-26; implemented 2026-10-26)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §3.5 (buildings and floors), §13.2 "Page → floor" and the split-level notes, ADR-0010

## Context

The pilot set (permit 1127975) draws three blocks side by side on every plan sheet, at +0.00,
+1.00 and +2.00 on the ground sheet, +3.20, +4.20, +5.20 on the next, and so on. The plan's notes
model each block as its own building. ADR-0010 clusters marker heights without a notion of blocks,
so on 2026-10-26 the owner's accepted proposal gave one building 17 storeys of 1.0 m, and the
massing would show 17 thin slabs. ADR-0010 listed "creating buildings from drawings" as out of
scope; the owner chose to bring it in.

What `main` has: `sheets.hints.level_markers` with each marker's normalised `x`, `y` on its
sheet; `levels.floor_regions` already splits a multi-block sheet into Voronoi regions per marker
for the page → floor suggestions; `projects.create_building`, `set_floors`, `delete_building`
(ADR-0012, refuses a building with units or documents); the floor proposal endpoint and card of
ADR-0010; the `documents.resuggest_floors` job (added 2026-10-26) that re-runs suggestions after
floors change.

## Decision

1. **Blocks are columns of markers.** On plan sheets (markers not stacked) with two or more markers
   at distinct horizontal positions, the markers of all such sheets are clustered by normalised `x`
   (tolerance 0.12 of the sheet width). A column that appears on at least two sheets is a block.
   Fewer than two blocks: the ADR-0010 single proposal stands.
2. **Each block gets its own storey proposal** from its column's markers alone, with the ADR-0010
   rules (0.25 m storeys, numbering, heights = distance to the next storey, the top floor the
   median). The stacked sheets (sections, elevations) are not used for blocks: a section stacks
   every block's levels, so another block's storey would pass for this block's roof and stretch
   its top floor.
   Blocks are named by order from left to right: A, B, C; when such a code exists in the project,
   the source building's code is prefixed. The codes are editable before accepting.
3. **The proposal response carries both views**: `floors` as in ADR-0010 for the whole building, and
   `blocks` with per-block code and floors when two or more blocks were found; `split_level` says
   which view the card opens with.
4. **Accepting blocks creates buildings.** `POST /buildings/{id}/floor-proposal/blocks` with the
   chosen blocks creates one building per block with its floors in one transaction (`project`
   WRITE), queues `documents.resuggest_floors` so the project-level plan sheets get one suggestion
   per block floor with its region, and, when asked and the source building has no units and no
   documents, deletes the source building through ADR-0012's `delete_building`. Unit ids are not
   involved: there are no units yet when this is useful.
5. **The card.** With blocks found, the building card shows "Split-level blocks: N" with a code
   field and a floors table per block, a checkbox "Remove building X afterwards" preselected when
   the source is empty, and one button "Create N buildings with their floors". A link "treat as one
   building" shows the ADR-0010 table instead.

## Options considered

- **O1 (chosen): detect blocks from marker columns, create a building per block.** Pros: matches
  how the plan models blocks, how the sheets' regions already work and how the massing places
  buildings; no schema. Cons: a layout where blocks are stacked vertically on the sheet is not
  detected (then the owner adds buildings by hand, as before).
- **O2: one building, storeys 1 m apart.** Status quo; wrong massing, wrong floor count in the
  portal.
- **O3: one building with "sub-levels" per storey.** Rejected: a new concept in the model for one
  drawing convention; floors per building already express it.
- **O4: ask the owner to split the PDF per block.** Rejected: the sheets are what the architect
  delivers; the regions already split them.

## Consequences

**Easier.** The pilot set goes from upload to three correctly floored buildings in two clicks; the
page → floor suggestions then land per block with regions, as the split-level notes describe.

**Harder.** One more rule to know: blocks are read from marker positions, so a sheet whose markers
sit in a legend column, not over the block, misleads the detection (the card shows the column
positions as sheet counts, and the owner can switch to the single-building view).

**Operations.** None.

**Revisit.** Blocks stacked vertically on a sheet; naming from text near the markers ("ბლოკი A");
after the pilot: the 0.12 column tolerance.

**Out of scope here:** placing the new buildings on the site plan (the placement page does that),
splitting a building that already has units.

## Action items

- [x] 1 `documents/storeys.py`: `detect_blocks`, block codes; tests with a pilot-like three-column
      set and a single-column set.
- [x] 2 `documents/floor_proposal.py`: `blocks` and `split_level` in the response;
      `accept_blocks` creating buildings and floors, optional source removal.
- [x] 3 API: `POST /buildings/{id}/floor-proposal/blocks`, schemas; OpenAPI regenerated; test
      through the API with a two-page three-block PDF: three buildings, source removed, sheet
      suggestions per block floor.
- [x] 4 Admin project page: blocks view in the proposal card.
- [x] 5 Docs: plan §13.2 split-level note, README; ADR-0010 Revisit line closed by this ADR.
- [ ] 6 A legend column of level markers (a caption listing levels, printed beside the plan) can
      read as a block: require a block column to hold a unit label or line work in its region.
