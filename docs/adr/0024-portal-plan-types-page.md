# ADR-0024: The portal shows the project's plan types, with live counts from the read model

- **Status:** accepted (2026-10-27, the owner's "next" after ADR-0022 option 3; implemented 2026-10-27)
- **Date:** 2026-10-27
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.1 (navigation model), §7.4 (illustrative content), §11.3 (portal screens), ADR-0018 (live availability and price, structure waits for a version), ADR-0022 (layout registry), ADR-0016 Decision 1 (gallery)

## Context

ADR-0022 gave every project a registry of plan types (`unit_layouts`) that owns the media its units
share. The portal uses it only inside a unit page: a unit shows the layout's media after its own,
marked `from_layout`. Verified in the code on 2026-10-27:

- The project document (`publishing/snapshot.py`) has `stats`, `site`, `gallery`, `buildings`,
  `massing`, `payment_plans`, `promotions`. There is no project-level list of layouts, so a buyer
  cannot see "which plans exist and how many of each are left", the first question on a developer's
  site (lisihouse.ge lists plan types with a render, the area and the free units).
- `published_units` carries `code`, `building_code`, `floor_level`, `unit_type`, `availability`,
  `price_amount`, `area_m2`, `rooms` and the unit document in `data`, which already holds `layout`
  and `layout_name`. There is no `layout` column, so the units list cannot filter by plan type.
- A sale or a price change rewrites `published_units` and the unit document at once (ADR-0018);
  the project document is a frozen snapshot, patched at serve time only for the floor units'
  availability and the stats (`live.with_live_sales`). A per-layout "N available" written into the
  document would go stale between publications.
- `GET /projects/{slug}/units` returns full unit documents and caps at 500 rows. Grouping them in
  the browser would ship every unit's media list to draw six cards and miscount a project with more
  than 500 listed units.

## Decision

1. **The project document carries the static part of each plan type.** `layouts[]` =
   `{code, name, media[]}` for every layout that has at least one listed unit, ordered by code
   without case; `media` are the layout's public items in the shape of unit media (`url`, `mime`,
   `kind`, `alt_text`, `is_ai_generated`, `ai_disclosure_text`). The key is absent in documents
   published before this release and the portal renders without it. `schema` stays 1 (additive).
2. **Counts and prices come from the read model at request time.** `published_units.layout`
   (string, nullable, additive migration 0018, backfilled from `data->>'layout'` so the live
   publication serves it without a republish). `GET /api/v1/portal/projects/{slug}/layouts`
   answers `{items: [{code, name, media, units, available, price_from, area_min, area_max,
   rooms[], buildings[]}]}` from one grouped query over the listed rows of the publication
   (`price_from` only when every priced unit of the layout shares one currency, the snapshot's
   rule), merged with Decision 1's static entries. Cached like the units list. Linking or unlinking
   a unit is structure: it reaches the portal with the next publication, like every structure
   change under ADR-0018.
3. **The units list filters by plan type.** `layout` (repeatable, compared without case) on
   `GET /units`, a "Plan type" select among the filters when the document lists layouts, the URL
   parameter `layout`, a removable chip "Plan L1 (name)", and a plan line on the unit card.
4. **A "Plan types" page** at `/projects/<slug>/plans`: one card per layout with its first image
   (a `plan_render` first), code and name, rooms, area range, "from" price, "N of M available"
   from Decision 2 and a link to the filtered units list; a lightbox-free gallery strip of the
   layout's other images. The project page gets a "Plan types" section (in the sub-navigation,
   present only when layouts exist) with the same cards from the document and a link to the page;
   the unit page's layout note links to the filtered list ("all units of layout L1").
5. **Two requests per page, both bounded.** The plan-types page uses the cached project document
   and the one grouped call of Decision 2; nothing per layout, nothing per unit.

## Options considered

### Option A: everything in the project document
Pro: one request, no migration. Con: "N available" and "from" prices freeze at publish time while
the rest of the portal is live (ADR-0018); extending `with_live_sales` to patch per-layout counts
reads every row of the publication on every project-page request anyway.

### Option B: static part in the document, live counts from one grouped query (chosen)
Pro: honest numbers, one bounded query, the filter column serves the units list too. Con: an
additive column and a backfill; two requests on the plan-types page.

### Option C: group the units list in the browser
Pro: no backend change. Con: the list caps at 500 rows and ships every unit document to draw cards;
wrong counts past the cap.

## Trade-off analysis

| | A document only | B document + grouped query | C browser grouping |
|---|---|---|---|
| Live availability | no | yes | yes up to 500 units |
| Cost per plan-types request | document read | document read + 1 grouped query | document read + up to 500 unit documents |
| Migration | none | one nullable column, backfilled | none |
| Units list filter by layout | separate work | same column | not possible server-side |

## Consequences

**Easier:** buyers see the plan types with the live number left; sales can send a link to one
plan type's units (`/units?layout=L1`); the layout media uploaded once (ADR-0022) front the page.

**Harder:** two places describe a layout: the document (static) and the grouped query (live);
reviewers keep them in step (a field added to one is added to the other on purpose). A layout
whose units were all unlinked after publishing still shows until the next publication.

**Revisit:** typical facts stored on the layout (rooms, area) instead of derived from its units;
a plan-type picker on the home page when a tenant has several projects.

**Out of scope here:** ADR-0022 E1; importing layouts; a per-layout inquiry form (Phase 5).

## Action items

### Phase A: backend

- [x] A1 Migration `0018_published_units_layout.py` (expand): `published_units.layout`, backfill
      from `data->>'layout'` under the platform scope; downgrade drops it.
- [x] A2 `tenants/models.py` `PublishedUnit.layout`; `publishing/snapshot.py` writes it and the
      `layouts[]` section of Decision 1.
- [x] A3 `publishing/portal.py` `list_layouts` (grouped query merged with the document) and the
      `layout` filter in `list_units`; `api/portal.py` `GET /projects/{slug}/layouts`, `layout`
      query on `/units`.
- [x] A4 Tests in `tests/test_unit_layouts.py`: the document's `layouts[]` with the layout's public
      media only, the grouped endpoint (units, available, price_from, area range, rooms), the
      `layout` filter without case, a document without the key still served; `openapi.json`.

### Phase B: portal

- [x] B1 `portal-api.ts` `LayoutDoc`, `LayoutSummary`, `ProjectDoc.layouts`, `UnitFilters.layout`,
      `layouts(slug)`.
- [x] B2 `pages/plans.page.ts` and the route `projects/:slug/plans`.
- [x] B3 `project.page.ts` "Plan types" section and sub-navigation entry; `units.page.ts` filter,
      query parameter and chip; `ui/unit-card.ts` plan line; `unit.page.ts` link in the layout note;
      `guide/portal-guide.ts` section (shown by `how-to-use.page.ts`).
      *Found while implementing:* the layouts' media in the document were first taken from the
      lowest-coded member's unit view, which is empty when that unit's media switch is off; the
      section is built from the layout's own public media instead, and the test turns the switch off.

### Phase C: docs

- [x] C1 This ADR; plan §7.1 tree and §11.3; README status paragraph; `docs/BACKLOG.md` header.
