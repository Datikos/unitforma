# ADR-0031: Drawing sets without a printed scale, lettered small: text in drawing order, line work apart from annotation, scale from the dimensions

- **Status:** accepted (2026-10-27, "1"; implemented 2026-10-27)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §13.2 (automation classification: page → floor, scale, unit boundaries, labels), ADR-0025 Decision 5 (solver passes "calibration" and "outlines"), ADR-0029 Decision 3 (a person's calibration serves the sibling pages)

## Context

The owner's request on 2026-10-27: complete project N4 (`nn4`, one building A, the GRC drawing set
`P1-M1-V06-2025-10-13 Jan Homeri`) so that a buyer picks an apartment on the 3D building. The
architect's IFC is filed under building A and converted (ADR-0030), but N4 had no unit, so every one
of the 8 conversions ended with `stats.plan_fit = {"reason": "no calibrated unit outline in this
building"}`. The setup checklist listed 12 floor-plan sheets as "needs you" with candidates such as
`110`, `011`, `122` at 0.65. What the floor-plan PDF (27 pages, A3, 4000 × 2829 px rasters) showed,
measured on page 12 (the 2nd storey, apartments 201–224):

- **Labels.** Every apartment carries a boxed label in three rows, "ბინა" / "221" / "43.9 მ2", set in
  AcadMtavr (decoded by `labels.decode_legacy`) at 3.32 pt on rows 3.5 pt apart. `page.extract_words()`
  with pdfplumber's default `y_tolerance = 3` clusters the tops of every character on the page and
  chains the rows of neighbouring labels into one line: 1,401 single-letter "words", 3 "ბინა", 1
  apartment code. With `y_tolerance = 0.5`, or with `use_text_flow = True` (the order the file draws
  the characters), all 24 codes come back; text flow keeps the PDF's own order and is used. `labels`
  required a label on one line ("labels never span lines"), so even separated rows read as a bare
  "221" without its area.
- **Line work.** 55,715 lines. Each apartment is hatched with yellow diagonals
  (`stroking_color (1.0, 0.98, 0.55)`, 3,128 lines), blue dash-dot grid axes run across every room,
  dimension and plot-boundary lines are red. `polygonize` over all of them cut every room into
  diagonal slivers; one axis ran through the label box of apartment 220. The 20,000-segment cap
  dropped mostly tiny pieces (median length 1.3 cm on the sheet), not walls.
- **Scale.** The title block prints "NTS"; `hints.scales = []` on every page, so nothing was
  calibrated and no area could be compared. The pages carry dimension chains in centimetres
  ("620", "530", "6,475"). Pairing each upright whole number with the horizontal line just above or
  below it whose span covers it gives value ÷ span = the page width: 30 of 63 pairs on page 12 agree
  on 10,818–10,819 cm; the rest are axis bubbles and label boxes. The five plan pages are each scaled
  differently: 110.26 m (basement), 111.95, 108.19, 108.96, 107.59 m.
- **Prototype result** with the three changes (text flow, line work only, stacked labels) and the
  measured page widths: 22 of 24 apartments on each of the 2nd–4th storeys and 19 of 22 on the ground
  floor grow to their printed area (measured within 4 % of the printed living area), at 0.7 for
  review. Misses: on every floor the two units in the north-west wing (x23 and x24) share one face —
  no dark wall is drawn between them — and that face was offered as x23 at 0.9; the 4th-storey label
  of 404 is printed "04" in the drawing (the schedule says 404). The basement's 36 stalls read as
  "P / 01 / 13.3 m2" stacked; each stall fill has the car symbol drawn over it as a second, smaller
  fill carrying the same label.
- **Regression evidence.** On `permit-1127975` (pages 1–5 and 39 of the "9.10 გეგმები" set), every
  fill candidate at 0.85–0.95 is unchanged; page 5 gains apartment №15 at 0.95 (BACKLOG 32 lists it as
  having no closed outline), page 2 reads "ბინა №3" instead of "ბინა 5 №3", bare room-number loops drop
  from 84 to 38, and a vertical "1500" that the old top-to-bottom reading gave as "0051" now reads as
  printed. Extraction time on N4 pages 11 and 12: 4.4 and 5.8 s, against 4.9 and 5.9 s before; the
  stored extract is 5 % smaller.
- **Found on the way.** Pages 16–20 and 22–23 reprint pages 10–14 (accessibility and egress sets);
  with no labels read, `jobs.duplicate_pages` could not see it, so all 12 pages were assigned floors
  and would have produced every unit twice. Page 11 (ground, ±0.00) is assigned to B1 and Ground: the
  floor "B1 at −0.80" comes from the outside ground mark "−0.80", not a storey. The checklist's "8
  model(s) linked" counts the eight conversions of one building; "Prices: done" holds on a project
  with no unit. The plan comment in `extract_page` said the segments serve snapping in the boundary
  editor; only `mapping/suggest.py` and `autopilot/passes/facades.py` read them.

## Decision

1. **Text is read in the order the file draws it.** `processing.extract_page` takes words and text
   with `use_text_flow=True`. Rows of a CAD label are separate text objects in the stream, so they
   stay separate lines however densely labels are packed; rotated text keeps its reading order.
2. **Coloured and light strokes are annotation, not line work.** A line whose stroke is chromatic
   (max − min channel > `LINE_WORK_MAX_CHROMA = 0.25`) or light (mean > `LINE_WORK_MAX_LIGHTNESS = 0.6`)
   is kept in `segments` with a fifth element `1`; `suggest._faces` skips it; line work is stored
   first, so the `MAX_SEGMENTS = 20_000` cap drops annotation before walls. A segment with four
   numbers (every extract written before this ADR) is line work, as before. Rectangles are unchanged.
3. **A page without a single printed scale is scaled from its own dimensions.**
   `processing.dimension_page_width` pairs upright whole numbers (`DIMENSION_RE`: "620", "6,475",
   "6 475") with the nearest horizontal line within 1.2 text heights above or below whose span covers
   the number and is at least as wide as it; the densest ±0.5 % window of value ÷ span ratios is
   taken when it holds at least 5 pairs and 30 % of all pairs; the agreeing values' median decides
   centimetres (< 1000) or millimetres; a page width outside 5–2,000 m is refused. The result is
   `hints.dimension_scale = {page_width_m, unit, agree, pairs}`. `mapping.sheet_metres` uses it after
   a calibration and a single printed scale. The solver's calibration pass writes it as a calibration
   with `source = "dimensions"`, `dimension_unit`, `dimensions_agreeing`, at confidence
   `rules.CALIBRATION_DIMENSIONS_CONFIDENCE = 0.8`, **before** a person's calibration is copied to
   siblings (an NTS set is scaled per page), never over a person's calibration, and it is not a
   person's calibration for the sibling rule.
4. **A boxed label lettered in rows is one label.** `labels.find_labels` accepts the unit word alone on
   its row and the number (optionally with №) alone on the next ("ბინა" / "221"; "P" / "01" for
   parking), strength 2; a row holding anything else does not form one, so legend lines stay out.
   The label's text is shown on one line ("ბინა 221").
5. **Two labels in one face, and a symbol inside a labelled zone, are not units of their own.** A face
   whose text holds two or more unit labels is offered under the first at 0.5 ("two units without a
   drawn wall"); a fill lying inside a larger fill with the same label (a car drawn over its stall) is
   dropped. Grown outlines stay at 0.7, so none of this creates a unit without a person: the solver
   creates drafts only at `OUTLINE_MIN_CONFIDENCE = 0.85`.
6. **Existing documents take the new extractor by being processed again.** The extract is written
   per revision; a revision processed before this ADR keeps its old words and segments until it is
   processed again (the "Process again" button is BACKLOG 40; N4 was re-queued by an operator script
   on 2026-10-27). Re-processing keeps sheets, floor assignments, calibrations and boundaries.

## Options considered

### Option A (chosen): read the drawing as drawn, keep line work apart, scale from the dimensions
Pros: three small changes to the extractor and one to the label grammar fix the whole N4 set and
improve the permit set; the reviewer's flow (candidates in the sheet editor, accepted per sheet)
does not change; the dimension scale also serves every other NTS set. Cons: colour is a convention,
not a law (an office that draws walls in red loses them, see Revisit); the dimension pairing reads
horizontal chains only.

### Option B: the owner draws the 130 outlines in the sheet editor
Pros: no code; immediate. Cons: about 30–90 s per unit (plan §13.2) after calibrating five pages by
hand, and the next GRC set costs the same again.

### Option C: smaller `y_tolerance` instead of text flow
Pros: equally recovers the N4 labels (24 of 24 at 0.5 pt). Cons: a fixed tolerance splits a line that
mixes type sizes on one baseline (their tops differ by about the size difference) and still chains on
denser sheets; it does not fix rotated text, which text flow reads in its own order.

### Option D: raster segmentation of the yellow apartment hatch
Pros: independent of the line work. Cons: depends on one office's colour of hatch, needs image
processing in the worker and loses the walls the vector faces already give; rejected.

## Trade-off analysis

| | A: drawn order, line work, dimensions | B: by hand | C: tolerance | D: raster hatch |
|---|---|---|---|---|
| N4 apartments as candidates ≥ 0.7 | 86 of 94 | 0 (all drawn) | 86 of 94 (with A's other parts) | unknown |
| Scale on NTS pages | automatic, per page | two clicks per page | — | — |
| Permit set regression | none on fills; №15 gained | — | not measured | — |
| Cost per page in the worker | −0.1 to −0.5 s | — | ≈ 0 | + image pass |
| Next set of the same office | free | hours again | free | free |

## Consequences

**Easier.** NTS sets get metres without a click; small stacked labels read as units with their
printed areas; the reprint detector sees reprints of such sets, so the solver skips them
(`autopilot/passes/common.py`); rooms are no longer cut by hatching or grid axes on any drawing.

**Harder.** Two meanings of a segment (line work and annotation) to hold on every change to
`suggest._faces` and the facade pass (which reads every segment, by design). The calibration pass has
three automatic sources with an order that matters (printed scale, dimensions, sibling). ADR-0029
Decision 3 ("a person's calibration serves the sibling pages") now holds only for pages whose
dimensions do not agree on a width: a page with a dimension chain is calibrated from its own
dimensions first, even when a person calibrated a sibling. On the permit set no page yields a
dimension scale (checked 2026-10-27), so its behaviour is unchanged; the ADR-0029 sibling test passes
because its fixture prints no dimension numbers.

**Operations.** No migration, no new container or setting; the stored extract gains an optional fifth
element per segment and an optional `hints.dimension_scale` (both read backward-compatibly). A
revision must be processed again to benefit.

**Revisit.** Colour thresholds after the first office that draws walls in colour (a stroke-width rule
or a per-document override); an elevation sheet over the 20,000-segment cap now loses coloured lines
first, and `facades.drawn_width_m` measures horizontal segments at the level markers, which some
offices draw in colour (before, the file's order decided what was cut); vertical dimension chains and dimensions in metres ("6.20"); matching a
printed "04" against the page's own area schedule (which lists ბინა № 404); a face holding two labels
could be split along the line between the labels' printed areas instead of being offered at 0.5.

**Out of scope here:** the "Process again" button (BACKLOG 40), the phantom floor from an outside
ground mark and the two checklist counts found on the way (BACKLOG rows), raster segmentation of
scans.

## Action items

### Phase A: extractor and labels
- [x] A1 `documents/processing.py`: text flow for `extract_text` and `extract_words`; `is_line_work`
      and the annotation mark; line work first under `MAX_SEGMENTS`; `dimension_page_width` and
      `hints.dimension_scale`; the stale snapping comment removed.
- [x] A2 `documents/labels.py`: `_STACKED` (unit word or "P" alone on its row, number alone on the
      next), one-line label text; module docstring.
- [x] A3 `mapping/suggest.py`: annotation skipped in `_faces`; `dimension_metres`; two labels in one
      face at 0.5; a labelled fill inside a larger fill with the same label dropped.
      *Found while implementing:* a first rule, "a face larger than the printed area by 15 % is 0.5",
      failed `test_autopilot` (its fixture rooms are larger than their printed areas, as a printed
      living area can be); the N4 case is two labels in one face, which is the rule kept.
- [x] A4 `mapping/service.sheet_metres`: calibration, printed scale, then the dimensions.

### Phase B: solver
- [x] B1 `autopilot/passes/calibration.py`: `from_dimensions`, `_from_dimensions` before
      `_from_siblings`, `"dimensions"` not a person's source; `rules.CALIBRATION_DIMENSIONS_CONFIDENCE`.
      *Found while implementing (the live run on N4, 2026-10-27):* text flow made page 11 read the
      ramp note "1:12 900.36 cm" intact, `SCALE_RE` took it as the only printed scale, and the pass
      calibrated the page 5.04 m wide; the outlines pass then drafted 15 single rooms at 0.9, because
      every face measured 0.0 m² and `if measured` treated 0.0 as unknown. Hence
      `suggest.scale_metres`: a single printed scale is used only when the page's dimensions are
      absent or agree within `SCALE_AGREE = 5 %` (else the calibration is `source = dimensions` with
      `printed_scale_ignored`), and the area checks test `measured is not None`. The 15 drafts were
      withdrawn with `inventory.remove_unit` (lineage and audit rows, note naming this ADR) and the
      page recalibrated from its dimensions (111.95 m); since a solver unit was removed there, the
      outlines pass leaves page 11 to the person (its 21 candidates show in the sheet editor).
      Tests: `test_calibration_takes_a_printed_scale_only_when_the_dimensions_agree`,
      `test_a_labelled_room_measured_at_zero_is_still_a_room_of_the_unit`.
      *Also found:* page 1, the legend sheet, now reads its sample level symbol "−0.10" and the
      solver confirmed it as Ground; it was set to "shows no floor" (an empty floor list). A legend's
      sample markers are a Revisit for `documents/levels.py`.

### Phase C: tests and docs
- [x] C1 `tests/pdf_fixture.make_nts_stacked_pdf` (two apartments, 2.5 pt rows offset to chain, a
      yellow hatch, a blue axis, red dimension chains in cm); `tests/test_drawing_sets_without_scale.py`
      (rows, page width, annotation and growth, an old extract, agreement and mm/cm, two labels in
      one face, a car inside its stall, calibration yields to a printed scale);
      `test_unit_labels` stacked cases; `test_autopilot::test_a_page_without_a_printed_scale_is_calibrated_from_its_dimensions`.
      The fixture fails on the code before this ADR (single-letter words, no label).
- [x] C2 Plan §13.2 (scale row, notes), README status sentence, BACKLOG rows.

### Phase D: N4
- [x] D1 Re-process N4's floor-plan revision with the new extractor (operator script, 2026-10-27):
      pages 10–14 calibrated from their dimensions (110.26, 111.95, 108.19, 108.96, 107.59 m), pages
      16–20 and 22–26 marked reprints of 10–14 (`hints.duplicate_of`, skipped by the solver), page 11
      limited to Ground (the B1 region from the outside mark "−0.80" removed), page 1 set to no
      floor. Apartment candidates at 0.7 or more: ground 20 of 22, storeys 1–3 22 of 24 each.
      The two basement stalls the solver drafted at 0.95 (P 22, P 03) stay.
- [ ] D2 Pages 16–20 and 22–26 excluded as reprints and the candidates accepted on the owner's "continue"
      (2026-10-27, operator script on the editor's accept path, `source = vector_suggest`, codes
      generated): 34 stalls (the stall rectangle, not the stall grown into the aisle; P 03 and P 22
      were the solver's), 20 ground-floor apartments, 22 on each of storeys 1–3, "04" stored as
      "ბინა 404"; "№1" by the basement stairs left out; 122 draft units. Pages 10–14 approved on the
      owner's "publish" (admin API, his session): 122 units active. Open: the owner draws 121, 122,
      223/224, 323/324, 423/424. The basement B2 is 3.0 m high on the
      section (−3.00 to ±0.00), recorded as 2.2 m; saving the floors queues a floor re-suggestion that
      can suggest Ground again on page 1 and B1 on page 11, so it is changed on the building card
      together with a look at those two pages. The phantom floor B1 (−0.80, 0.8 m) stays: the app has
      no way to delete a floor (E1); it holds no unit.
- [ ] D3 IFC conversion of building A re-run (2026-10-27 14:41 UTC): 122 plan spaces, one per unit,
      scope building, rotation 2.5°, mean IoU 0.389 (per level 0.29–0.44), every level 85–98 % inside
      its slab target. On the owner's "publish": the 122 plan spaces confirmed and "Publish with
      defaults" run (22 plan types confirmed, 122 units listed, v2 live at
      `lisi.unitforma.localhost/projects/nn4`; the public GLB carries 122 unit nodes). Open: prices
      (all empty, shown as unknown), the conversion re-run and a new version after the remaining
      units are drawn.

### Phase E: found on the way (open)
- [x] E1 A floor no unit uses can be deleted (API, admin building card, MCP); `projects.set_floors`
      only creates and updates, while the MCP tool `set_floors` says it replaces the list. N4's B1
      (−0.80, from the outside ground mark) cannot be removed today.
      *Done 2026-10-29:* `DELETE /buildings/{id}/floors/{floor_id}` (project write) → 204, 409
      `floor-has-units` with the count while any unit row points at it, removed ones included
      (`units.floor_id` is RESTRICT); its `sheet_floors` rows go and each sheet that showed it gets
      its mirror columns from the floors it still shows (`assignments.sync_primary`: N4 page 11
      keeps Ground when B1 goes), or becomes unassigned when none is left; IFC space links keep their space (SET NULL); the page → floor
      suggestions and the massing are queued; an audit row `delete_floor` keeps the old values. A bin
      per row of the building card's floor table, with a confirmation. The MCP part is only the
      docstring of `set_floors` (it never claimed replacing in the code; it now points at the building
      card): a `delete_floor` tool waits for BACKLOG 31's choice of the confirmation form for the
      `delete_*` family; that tool is not built. Test:
      `test_floor_without_units_is_deleted_and_one_with_units_refused` (a sheet showing two floors).
- [x] E2 Setup checklist: "Architect's 3D model" counts `geometry_models` rows (N4: 8 conversions of
      one building, "8 model(s) linked"), not buildings with a ready model; "Prices" is done on a
      project with no unit.
      *Done 2026-10-29:* the step counts buildings with a current ready IFC model ("1 of 1
      building(s) shown from the architect's model"); "Prices" is `todo` until a unit is active
      (`publishing.setup.prices_status`). Tests: `test_setup_checklist_counts_buildings_with_a_model_not_conversions`,
      `test_prices_are_not_done_before_there_is_a_unit`.
- [ ] E3 `documents/levels.py`: a legend's sample level symbol ("±0.00 / −0.10" on N4 page 1) is not a
      floor marker.
- [ ] E4 Revisit items above: colour thresholds, vertical and metre dimensions, a printed code checked
      against the page's area schedule, a two-label face split between its labels.
      *N4, 2026-10-29:* the ground plan's 121 (43.2 m²) and 122 (61.2 m²) are one loop candidate
      of 52.3 m² holding both labels, so no split of it gives the printed areas; drawn walls
      separate them on the sheet.
- [ ] E5 A building's footprint is the convex hull of its lowest floor's outlines when they do not
      union into one polygon (`geometry.service.footprints`): on N4's L-shaped block the hull
      (1,557.6 m²) covers the courtyard with a diagonal, the placement pass matched it at 0.75 and
      skipped, and the published site plan (v9) draws that diagonal. A closing of the outlines does
      not help (0.5 to 4 m give two parts or a 1,135 to 1,224 m² shape: the stair core has no
      unit). Options: the closed face of the calibrated site plan the placed footprint lands on as
      the drawn outline (N4: 1,364.6 m², the architect's envelope), or a concave hull; the owner
      picks.
      *Found while placing N4 (2026-10-29), done on the owner's "can you do it for me":* the site
      plan prints NTS and has no dimension chain the reader takes, so it was calibrated on the
      admin API from the column grid it draws: axes 1 and 13 on axis A, 6,475 cm (the twelve bays
      620 + 530 + 300 + 400 + 640 + 640 + 620 + 620 + 620 + 595 + 320 + 570 and the printed total),
      raster x 1447 and 3113 at y 2130, 0.038866 m/px; axes 2, 4, 8, 10 and 11 land within 1 px of
      that scale. The same axes on the ground plan (page 11, its dimension calibration
      0.027988 m/px) measure 64.748 m; axis 1 × A is (15.312, 53.150) m there and (56.238,
      82.239) m on the site plan, so building A is placed at tx 40.926, ty 29.089, 0°, confirmed
      after the 20 ground-floor outlines were drawn over the site plan on the grid. Floor B1 was
      deleted (no unit, no sheet). The massing was rebuilt with the building placed and v9
      published. Facade drawings were not assigned: N4 shows the architect's IFC model, which
      replaces the massing they would texture.
