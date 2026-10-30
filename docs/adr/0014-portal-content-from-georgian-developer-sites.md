# ADR-0014: The buyer portal shows what Georgian developers' sites show: elevation floor picker, entrance, building status and terms, price note, table of units

- **Status:** accepted (2026-10-26; implemented 2026-10-26)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §6.6 (public fields), §7.1 (navigation model), §7.3 (3D and fallbacks), §9.3 (portal settings), §13.2 (automation classification)

## Context

The owner named https://lisihouse.ge on 2026-10-25 as a site Unitforma should produce automatically from
the CAD documents. The site was read on 2026-10-25 (static HTML, headless Chrome screenshots, the plugin's
markup). What it does and how, against `main` at commit e687e43:

- The chooser is the WordPress plugin `building_planner` 1.7. Every polygon is hand-drawn SVG `points` on
  a raster image: 13 house polygons on the site plan, 4 floor bands per house on a 2D **elevation drawing**,
  one polygon per apartment on a floor plan PNG. Nothing is derived from CAD. Unitforma already covers the
  path site → building → floor → unit (`portal/pages/project.page.ts`, `building.page.ts`) and takes the
  outlines from the drawings (plan §13.2).
- The house step of the reference is a 2D elevation with one clickable band per floor. Unitforma's building
  page offers the floor stack and the 3D massing (ADR-0006 Decision 6), nothing in between. Elevation and
  section sheets are uploaded today and their level markers are extracted and stored
  (`documents/jobs.py` writes `sheet.hints["level_markers"]` with normalised `x`, `y`, top-down: on a
  three-level fixture `+6.40` sits at `y = 0.155` and `+0.00` at `y = 0.827`), but
  `levels.is_stacked` skips them for floor suggestions and nothing else reads them.
- Every apartment on the reference carries `სადარბაზო` (entrance) next to house, floor and number. `units`
  has `rooms`, `bedrooms`, `bathrooms`, `orientation` (`tenants/models.py`, `sales/rules.UNIT_FIELDS`) and no
  entrance; `published_units` cannot filter by it.
- The reference colours houses by phase (legend: under construction, completed, planned) and prints a
  completion month and a handover specification per house ("terms" tab: white-shell spec, mortgage
  partners, instalment). Unitforma has one `construction_stage` and `completion` text per project
  (`projects.portal_settings`, `publishing/snapshot.sanitise_portal_settings`), nothing per building, and
  no terms text anywhere.
- The reference prints prices in USD with the note that payment is settled in GEL at the National Bank
  rate of the payment day. Unitforma has one currency per project and no note.
- The reference's "apartments for sale" tab is a plain table (house, floor, price, entrance, apartment,
  area). Unitforma's units list (`portal/pages/units.page.ts`) is cards only.
- `api/admin_projects.update_building` builds `changes` with `exclude_none=True` and
  `projects/service.update_building` skips `None`, so no building field can be cleared through the API.
- `_site` in the snapshot emits only buildings that have a public unit and a mapped footprint; a planned
  house without drawings never reaches the site plan.

Out of this ADR by the owner's priority list of 2026-10-25: a second portal language (R3, plan §2.3),
booking and leads (Phase 5), proposing the entrance from the drawing (revisit, see Consequences).

## Decision

1. **A building can name one elevation (or section) sheet, and the portal gets a clickable elevation
   floor picker from it.** `buildings.elevation_sheet_id` (nullable, FK `sheets.id` `ON DELETE SET NULL`)
   is chosen by the reviewer. `GET /buildings/{id}/elevation-candidates` lists the building's current,
   non-excluded sheets whose level markers are stacked (`levels.is_stacked`), with the sheet's page,
   document title, marker count, how many floors they match and the raster URL. `PATCH /buildings/{id}`
   accepts `elevation_sheet_id` (a sheet of this project, else 422 `elevation-sheet-unknown`) and `null`
   to clear it. At publish time `publishing/elevation.bands(markers, floors)` matches markers to floors by
   `floors.elevation_m` (± 0.02 m, the tolerance of ADR-0010), or by order when no floor has an elevation
   and the distinct marker levels equal the floor count, and needs at least two matched floors. One band
   per matched floor runs from that floor's marker line up to the next higher floor's line; the topmost
   band ends at a stacked marker above the highest floor (the roof) when there is one, else one median
   band height up. The snapshot crops the sheet vertically to the bands plus 3 % and emits
   `buildings[].elevation = {plan, bands: [{level, published, ring}]}`. The portal building page shows the
   elevation as a third view beside "Plan only" and "3D + plan"; it is the default on phones and when the
   device cannot show 3D, and desktop keeps the 3D default of ADR-0006 Decision 6, which is unchanged. A
   band tap sets `?floor=` exactly like the floor stack; unpublished floors draw as inert regions. Bands
   are built at publish time, so floor edits reach the picker with the next publication.
2. **`units.entrance` (20 characters, nullable) is a unit fact that travels every path.** It joins
   `UNIT_FIELDS`, so inline edit, bulk edit and spreadsheet import accept it (import targets `entrance`
   with synonyms `staircase`, `stair`, `podezd`, `სადარბაზო`), the inventory grid and the unit sales page
   edit it, and exports carry it. It is public by construction like the floor (no switch): the public view,
   the floor-plan units and `published_units.entrance` carry it. `GET /portal/projects/{slug}/units` takes
   `entrance` (list) and applies it only together with `building`, because entrance 1 of house 5 is not
   entrance 1 of house 7; each `buildings[]` document lists its distinct `entrances`. The portal shows the
   entrance filter once a building is chosen and the building has entrances, and prints the entrance on
   the unit page, the unit card, the floor pick card and the table.
3. **Buildings get a construction status, a completion text and terms.** `buildings.construction_status`
   (nullable, check `planned | under_construction | completed`), `buildings.completion` (80 characters) and
   `buildings.terms` (4 000 characters). `projects.portal_settings.terms` (4 000 characters) is the default
   a building without its own terms inherits. The snapshot emits `construction_status`, `completion` and
   the effective `terms` on `buildings[]` and `construction_status` on `site.buildings[]`. The status
   vocabulary (`libs/ui` `status.ts`, ADR-0009) gains the domain `building.construction`. The site plan
   colours footprints by construction status when any public building has one (planned neutral, under
   construction warning, completed good, with a legend), else by the primary colour as today. Building
   cards and the building page show the status chip and the completion; the building page and the unit
   page show a "Terms" section when terms exist. The admin building card edits all three and the
   elevation sheet, and the publish page edits the project default terms. `PATCH /buildings/{id}` is
   built with `exclude_unset`, so an explicit `null` clears `name`, `completion`, `terms`,
   `construction_status` and `elevation_sheet_id`.
4. **`projects.portal_settings.price_note` (200 characters) is printed next to every price.** It passes
   `sanitise_portal_settings`, lands in `project.price_note` of the snapshot and shows under the price on
   the unit page and once above the results of the units list (the building page's pick card has no
   price). It is text only; no conversion is performed, no second currency is stored (currency stays
   one per project, plan §6.2).
5. **The units list has a table view.** A "Cards | Table" switch; `?view=table` in the URL so a link
   shares it, the last choice remembered in `localStorage` (`uf:units-view`). Columns: building, floor,
   entrance (when any unit of the result has one), unit, type, rooms, area, price, status; every row links
   to the unit page; the same filters and sort apply.
6. **Migration `0012_portal_content` (the migration sequence is independent of the ADR numbers) is additive** (five nullable columns, one check constraint, one
   foreign key, one read-model column), backward compatible with the running release; the snapshot
   `schema` stays 1 because every new key is optional and the portal treats a missing key as "not
   stated".

## Options considered

### Option A: elevation picker from the stored markers of a sheet the reviewer names (chosen)

Pros: zero drawing, uses markers the pipeline already extracts, the reviewer picks the sheet and sees the
preview, floors without elevations still work when the counts agree. Cons: a sheet with noisy markers
(single-page documents never pass `drop_repeated`) can give odd bands; the reviewer sees it before
publishing and can pick another sheet or none.

### Option B: hand-drawn bands on the elevation (the reference's way)

Pros: always right. Cons: a drawing step per building that the pipeline can do; contradicts the product's
promise of deriving the portal from the documents.

### Option C: render an elevation from the 3D massing (orthographic side view)

Pros: no sheet needed. Cons: a schematic box, not the architect's facade, which is what buyers recognise;
needs a server-side renderer for the GLB (a new dependency) or client-side work that phones avoid.

### Option D: do nothing (floor stack and 3D only)

Rejected: the floor stack is a list of names; the reference shows that buyers pick floors on the facade,
and phones do not get 3D.

For the content fields (Decisions 2 to 5) the only real alternative was a free-form `attributes` JSON per
unit and building. Rejected: typed columns filter and validate; a JSON bag cannot be a read-model filter
and would make the spreadsheet import guess.

## Trade-off analysis

| | A (chosen) | B hand-drawn | C from massing |
|---|---|---|---|
| Reviewer work per building | pick a sheet | draw 4 to 20 bands | none |
| Looks like the facade | yes | yes | no |
| Works without elevation sheet | no (fallback: floor stack) | no | yes |
| New dependency | none | none | GLB renderer |
| Size | M | M | L |

## Consequences

Easier: a building with an uploaded facade drawing gets the reference's house step for free, phones get a
floor picker that is not a list, Georgian sales tables (house, floor, entrance, apartment, area, price)
exist in the portal as is, and the per-building status and terms replace the one project text.

Harder: three rules to hold on every review. First, `entrance` is public by construction: nothing
private may be typed into it (the guide says so). Second, the elevation bands are built at publish time
from `floors.elevation_m`; a floor renumbered after publishing shows the old bands until the next
publication. Third, `update_building` now writes explicit `null`s for the clearable fields, so a caller
that sends `{"terms": null}` clears the terms; the Angular client sends only the fields it edits.

Known gaps, written where a reader would assume the opposite: a building without a single public unit
or without a mapped footprint is not on the site plan (`_site`), so a planned house with no drawings
cannot be shown grey as the reference does; floors without `elevation_m` and a marker count that differs
from the floor count get no picker; a one-page elevation document keeps its title-block markers, which
only bite when one of them equals a floor elevation. Deleting the elevation document is not refused
(ADR-0012 refuses only mapped documents): the foreign key clears `elevation_sheet_id` and the picker
disappears with the next publication, without a warning. An elevation set filed at project level is a
candidate only when the project has one building, because `markers_for_building` reads project-level
documents only then.

Revisit: proposing the entrance from the drawing (the stair core labels sit on the plan next to the
units); a second language; drawn footprints for planned buildings. Done 2026-10-30 (BACKLOG 26): deleting the document that
holds a building's elevation sheet answers 409 `document-holds-elevation` naming the buildings until
the caller sends `clear_elevation` (the admin dialog asks, the MCP tool has the flag); the audit row
lists the cleared pickers. Browser pass done 2026-10-26 on the published sample
project: the admin building "Shown to buyers" row (construction status, completion, elevation drawing
picker, terms), the portal units table view with its filters, the building page with the floor list, the
project page with the site plan and legend. The elevation floor picker, the construction-status colours,
the Terms section and the entrance filter could not be seen because the sample project has none of that
data yet; the owner enters it (backlog row 32).

**Out of scope here:** booking and leads (Phase 5), a mortgage calculator, a second currency, a second
portal language, drawn footprints for planned buildings, deleting a floor.

## Action items

### Phase A: backend

- [x] A1 Migration `0012_portal_content`: `units.entrance`, `buildings.construction_status` (+ check
      `ck_building_construction_status`), `buildings.completion`, `buildings.terms`,
      `buildings.elevation_sheet_id` (FK `sheets`, `SET NULL`), `published_units.entrance`; models in
      `tenants/models.py`.
- [x] A2 `sales/rules.py` (`UNIT_FIELDS`, 20-character rule), `sales/spreadsheet.py` (target, synonyms,
      export column), `sales/service.py` (inventory row, `public_view`); `api/schemas.py` (`InventoryRow`,
      `SalesChanges`, `BuildingOut`, `BuildingUpdate`, `PortalSettings`, `ElevationCandidateOut`).
- [x] A3 `publishing/elevation.py` `bands()` (pure) and `tests/test_elevation_bands.py`: elevation match,
      order fallback, roof marker, median top, too few floors, noise marker ignored.
- [x] A4 `publishing/snapshot.py`: `entrance` on units and floor units, `entrances` per building,
      building `construction_status`/`completion`/`terms`, site `construction_status`, project
      `price_note`, `_elevation()`; `publishing/portal.list_units` `entrance` filter;
      `api/portal.units` parameter.
- [x] A5 `projects/service.py` (`BUILDING_FIELDS`, clearable fields, `elevation_candidates`,
      sheet ownership check) and `api/admin_projects.py` (`exclude_unset`, candidates route).
- [x] A6 `tests/test_phase4_publishing.py`: ADR-0014 section: entrance through sales PATCH, building
      fields, price note and terms in the snapshot, entrance filter with and without building, elevation
      candidates and bands from an uploaded section PDF, `null` clears a building field.
- [x] A7 Regenerate `openapi.json` and the typings.

### Phase B: admin app

- [x] B1 `inventory.model.ts` column and change mapping; `unit-sales` form field and summary.
- [x] B2 `project-detail.page.ts`: building "Portal" row (construction status, completion, terms,
      elevation sheet with candidates and preview, Save); `api-client.ts` `elevationCandidates`.
- [x] B3 `publish.page.ts`: price note and default terms.
- [x] B4 `guide-content.ts`: project-overview, publish, inventory, unit-sales entries.

### Phase C: portal

- [x] C1 `portal-api.ts` types; `libs/ui` status domain `building.construction`.
- [x] C2 `building.page.ts`: elevation view with bands, default on phones; `floor-first-navigation.spec.ts`
      extended with a band tap; entrance on the pick card; Terms section.
- [x] C3 `project.page.ts`: site plan coloured by construction status with legend; building cards with
      status chip and completion.
- [x] C4 `units.page.ts`: entrance filter (with a building), table view, price note; `unit-card.ts`
      entrance; `unit.page.ts` entrance fact, price note, Terms section.
- [x] C5 `guide/portal-guide.ts` (the "How to use" page's content): elevation picker and table view.

### Phase D: docs

- [x] D1 README status line; plan §5.3 rows (`projects`, `buildings`, `units`), §6.6, §7.1, §9.5 and the
      §13.2 row "Elevation → floor picker"; this ADR ticked.
