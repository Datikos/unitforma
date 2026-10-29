# ADR-0035: The drawn outline of a placed building, confirmations that survive a re-run, and walls the extract keeps

- **Status:** accepted (2026-10-29, the owner's "start" on the recommended option of BACKLOG 58); Decisions 1 to 3 implemented 2026-10-29 on branch `adr-0035`; Decision 4 measured and not shipped (Phase C); D2 done 2026-10-29 (v12)
- **Date:** 2026-10-29
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §3.5 (site frame, footprints), §11.3 (geometry), §13.2 (unit boundaries from line work); ADR-0011 (massing), ADR-0025 Decision 5 (placement pass), ADR-0030 (plan spaces), ADR-0031 #E4 and #E5, ADR-0032 #C1

## Context

Three re-dos were left after N4's setup on 2026-10-29 (BACKLOG 58, 55 and 53).

- **The portal draws an L-shaped building as its convex hull.** `geometry.service.footprints`
  unions the lowest floor's unit outlines and takes the convex hull when the union is not one
  polygon. N4's ground floor gives 20 outlines, a 862.2 m² union in two parts (the stair core holds
  no unit), and a 1,557.6 m² hull. Published v9 draws it over the courtyard with a diagonal. The
  placement pass matched that hull against the site plan at IoU 0.75, below
  `PLACEMENT_DRAFT_IOU = 0.8`, and skipped. Closing the union does not help: a closing of 0.5,
  1, 1.5, 2 or 3 m leaves two parts; 2.5 m gives 1,134.9 m² with a hole; 4 m gives 1,224.1 m².
  The site plan itself draws the building's envelope as a closed face of 1,364.6 m² (92 faces on
  the sheet; `autopilot.passes.placement.site_faces`, 0.86 s on N4 in the dev API container).
- **A re-run of the IFC conversion drops every confirmation.** `geometry.ifc_service._ingest_ifc`
  marks the old model not current and writes new `ifc_space_links` with status `suggested`. The
  owner's re-run of 2026-10-29 06:37 (job 916, 2 min 55 s) produced the same GLB (834,456 bytes,
  158 meshes, 122 spaces) and the same plan fit (tx −22.199, ty 26.78, 2.5°, IoU 0.389), and all
  122 plan spaces went from `confirmed` back to `suggested`. Plan spaces carry
  `guid_for(unit_id)`, so a GlobalId is stable across re-runs; an ArchiCAD zone keeps its GlobalId
  across exports.
- **The extract drops walls on large sheets.** `documents.processing.MAX_SEGMENTS = 20_000`
  keeps line work first, then annotation. N4's five floor plans (pages 10 to 14) draw 30,222 to
  55,715 lines, all line work, so 10,222 to 35,715 wall, partition and furniture lines are dropped
  in the file's drawing order. On page 11 the labels 121 (43.2 m²) and 122 (61.2 m²) then share
  one 52.3 m² face. Keeping all 42,085 lines is not the fix: each label then sits in its own
  0.3 m² label frame, furniture splits the rooms, and the page gives no candidate for 121, 110 or
  111 (with the cap: 110 grown at 65.3 m², 111 at 47.2 m², 121 as the shared loop).
- **Found on the way:** `PATCH /buildings/{id}` with a new `site_transform` or `placement_status`
  does not queue the massing; on 2026-10-29 the massing kept "buildings_unplaced: A" until a
  rebuild was queued by hand.

## Decision

1. **A placed building is drawn with the site plan's own outline.** The massing job
   (`geometry.build_massing`, background) finds, for each building with a placement on a
   calibrated site sheet, the smallest closed face of that sheet that holds at least
   `OUTLINE_MIN_COVER = 0.8` of the placed lowest-floor unit union (balconies and terraces lie
   outside the drawn envelope: N4's holds 0.862, every other face of its sheet 0) and whose area
   is at most
   `OUTLINE_MAX_GROWTH = 1.25` times the footprint's. It stores
   `buildings.site_outline = {"v": 1, "sheet_id", "m_per_px", "transform": {tx, ty, rotation_deg, scale},
   "ring": [[x, y], ...] (site metres), "area_m2", "cover"}` (migration `0022`, nullable, expand
   only), or `null` when no face qualifies. The published site plan and `GET /footprints`
   (`site_outline_m`) use it only while its sheet, scale and transform equal the current ones;
   otherwise the hull, as today. The cost is one face extraction per site sheet per massing
   build (0.86 s on N4), never in a request.
2. **Saving a placement queues the massing.** `PATCH /buildings/{id}` and the MCP tool
   `update_building` queue `geometry.build_massing` when `site_transform` or `placement_status`
   changed.
3. **A re-run keeps the person's confirmations when nothing moved.** A new link is confirmed
   when the building's previous current model had a confirmed link with the same GlobalId and
   source, its unit is not removed and not already confirmed on another space, and the two space
   footprints overlap at IoU `CARRY_MIN_IOU = 0.98` or more. The old link's unit is kept. The
   model's stats count `spaces_carried`; one audit row `carry_confirmations` (actor `system`);
   one extra GLB write (`relink_model`, as "Confirm all plan spaces" does; the first file of
   the run is left for in-flight viewers). A moved fit or a redrawn outline changes the footprint, so those spaces stay
   suggested.
4. **The extract keeps the walls first (time-boxed).** When a page's line work passes the cap,
   the longest segments are kept, and the grower looks through a label's own frame (a face under
   2 m² that holds only label words) to the room around it. This ships only if, on N4 page 11,
   121 and 122 become candidates within `AREA_MATCH` (8 %) of their printed areas and no N4 floor
   plan page gives fewer candidates at 0.7 or more than today; otherwise the code is not merged
   and the measurement is recorded here.

## Options considered

### Outline: A, the site plan's closed face under the placed footprint (chosen)
Pros: the architect's own envelope, already drawn and calibrated; no new parameter for the shape.
Cons: needs a calibrated site plan with closed line work; 0.86 s per sheet, so it runs in a job.

### Outline: B, a concave hull of the outlines
Pros: no site plan needed. Cons: a ratio to tune per building; still bridges the stair core with
an invented edge; not what the architect drew.

### Outline: C, close the union by a fixed distance
Cons: measured on N4, no distance from 0.5 to 4 m gives the envelope (two parts or 1,135 to
1,224 m² against 1,364.6 m²).

### Confirmations: A, carry by GlobalId and unchanged footprint (chosen)
Pros: exact for the identical re-run; a real change still asks the person. Cons: a space whose
outline moves by a few centimetres asks again.

### Confirmations: B, carry by GlobalId only
Cons: a zone the architect reshaped would keep a unit it no longer matches, without review.

### Extract: A, longest line work first plus a transparent label frame (chosen, time-boxed)
Pros: walls are long, hatch strokes and furniture short; small change. Cons: furniture edges are
long too; it may not separate every shared face.

### Extract: B, no cap
Cons: measured: no candidate for 121, 110 or 111 on page 11; 42,085 segments in the stored
extract.

### Do nothing
The owner draws seven units by hand and re-confirms 122 spaces after every re-run.

## Trade-off analysis

| | Outline A | Outline B | Outline C |
|---|---|---|---|
| N4 result | 1,364.6 m² envelope | unmeasured, ratio-dependent | wrong (measured) |
| Needs | calibrated site plan | nothing | nothing |
| Cost | 0.86 s per sheet in a job | ms | ms |
| Synthetic edges | none | yes | yes |

## Consequences

**Easier:** the portal's site plan shows what the architect drew; re-running a conversion no
longer costs 122 clicks.

**Harder:** two rules on review: the stored outline is valid only for the sheet, scale and
transform it records; a carried confirmation needs both the GlobalId and the footprint.

**Revisit:** a site plan line that crosses the building (N4's west wing) cuts the chosen face;
the union of the faces the units cover would follow the envelope instead. The placement pass could fit against the faces holding the unit union instead of
the hull (N4 would then place itself); a stored outline for a site plan without closed line work.

**Out of scope here:** facade sides on an L-shaped building (ADR-0016 numbers four rectangle
sides); the IFC model's placement on the site (BACKLOG 24).

## Action items

### Phase A: the drawn outline
- [x] A1 Migration `0022_building_site_outline.py` (expand): `buildings.site_outline` JSONB null;
      model column.
- [x] A2 `geometry/site_outline.py`: `site_faces(sheet)` (moved from the placement pass, which
      imports it), `drawn_outline(units_placed, hull_placed, faces)`, the two constants.
- [x] A3 `geometry.build_massing` writes `site_outline` per building; `footprints` returns
      `site_outline_m` when valid; the snapshot's site block uses it.
- [x] A4 `PATCH /buildings/{id}` queues the massing on a placement change (Decision 2).
      *Found in review:* the MCP `update_building` writes the same fields; it queues too.
      *Not done:* the admin placement page still draws the hull; only the portal's site plan and
      `GET /footprints` (`site_outline_m`) carry the drawn outline.
- [x] A5 Tests: an L-shaped building whose drawn face is chosen over the hull; a stale outline
      ignored after the transform changes; the queue on a placement change.
      *Done 2026-10-29:* `tests/test_site_outline.py` (four pure tests and
      `test_the_massing_job_stores_the_outline_and_a_new_placement_drops_it` on the publishing
      world with the site faces stubbed). *Found while implementing:* N4's drawn envelope holds
      0.862 of the placed units (balconies and terraces lie outside it), so `OUTLINE_MIN_COVER`
      is 0.8, not the 0.9 first written; every other face of the sheet holds none.

### Phase B: confirmations across a re-run
- [x] B1 `geometry.ifc_service`: carry confirmed links from the previous current model (Decision 3),
      `spaces_carried`, the audit row, one relink.
- [x] B2 Tests: an identical re-run keeps every confirmation; a moved footprint does not; a removed
      unit does not.
      *Done 2026-10-29* in `test_ifc_without_spaces_takes_the_plan_outlines`: the identical re-run
      carries 2 of 2 and the GLB picks both units; a footprint moved by 1 m carries 1 of 2. The
      removed-unit rule (`Unit.lifecycle_status != 'removed'`) has no test of its own.

### Phase C: walls the extract keeps (time-boxed)
- [x] C1 Measure Decision 4 on N4 pages 10 to 14; ship or record.
      *Measured 2026-10-29 (worktree code on N4's 14,126,855-byte plan PDF, the pages' own
      dimension calibrations), not shipped:* apartment labels with a candidate at 0.7 or more
      within 8 % of the printed area, per page 10 / 11 / 12 / 13 / 14:

      | Extract | p10 (stalls) | p11 | p12 | p13 | p14 |
      |---|---|---|---|---|---|
      | today: cap 20,000 in drawing order | 23 | 19 | 22 | 22 | 22 |
      | cap 20,000, longest line work first | 20 | 0 | 0 | 0 | 0 |
      | no cap (page 11 only) | — | 0 | — | — | — |

      The file draws walls before furniture, so the drawing order already keeps the walls; the
      longest-first order keeps furniture and hatch edges and loses the rooms, and without a cap
      every label sits in its own 0.3 m² frame. The missing ones stay as before: 103, 121, 122,
      223/224, 323/324, 423/424 (and 404 read as "04"). Splitting a face between two labels stays
      ADR-0031 #E4 (BACKLOG 53) with this evidence; the label frame ("transparent" to the grower)
      was not tried.

### Phase D: docs and N4
- [x] D1 Plan §3.5 and §11.3, README, BACKLOG (58, 55, 53), ADR-0031 #E5 and ADR-0032 #C1 pointers.
- [x] D2 On the dev stack, in this order: apply 0022 from the worktree before the merge (the
      dev API runs the main checkout live and would select a missing column), merge, restart
      `worker-light` and `worker-heavy`, rebuild N4's massing so its outline is stored, publish;
      the 122 plan spaces confirmed once more on the owner's word (the carry helps the next re-run).
      *Done 2026-10-29 on the owner's "commit and merge":* 0022 applied 07:25 UTC, merged as
      `d227223`, `api`, `worker-light` and `worker-heavy` restarted 07:26, N4's massing rebuilt in
      4 s with a 22-point outline stored for building A, 122 plan spaces confirmed, v12 published
      (v10 and v11 were published by someone else in between). The live site plan draws the L
      along the grid; the courtyard is free. A diagonal line the site plan draws across the west
      wing cuts its face, so a thin triangle of the wing lies outside the outline.
