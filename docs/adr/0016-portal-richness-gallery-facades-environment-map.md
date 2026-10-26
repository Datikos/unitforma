# ADR-0016: A buyer portal that shows the building: render gallery, facade drawings on the 3D massing, site environment, layout renders, map, and imports that cannot get stuck

- **Status:** accepted (2026-10-26; implemented 2026-10-26; E4 and the E5 contract step open, E2 decided in ADR-0017)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner); AI-generated renders (Out of scope) are his call
- **Plan reference:** §6.6 (public fields), §7.1 (navigation model), §7.3 (3D and fallbacks), §9.3 (portal
  settings), §11.3 (portal screens), ADR-0009 (design system), ADR-0011 (massing follows mapping),
  ADR-0014 (portal content)

## Context

The owner configured the first real project from a permit on 2026-10-25 (`permit-1127975`, tenant `lisi`:
99 units on five floors, published v1) and judged the portal on 2026-10-26: "the building is without
rendered facade", "the page is not polished and comfortable to view or navigate", "there is no apartment
renders to imagine how it will be", "the building in the open area, no trees, no grass, no infrastructure
which is possible to get from the render". What `main` had at that point, and what the project held:

- The massing GLB (`geometry/massing.py`) extrudes each unit outline with one flat colour per availability
  state; walls carry no texture, the viewer (`libs/viewer-3d/massing-viewer.ts`) renders on a plain grey
  background with no ground, no shadows and no surroundings.
- The architect's drawing set holds nine elevation pages (document "2": four facades named by their axes,
  `1-10`, `10-1`, `ა-გ`, `გ-ა`, plus details) and a render document ("1", five pages of exterior
  renders). Documents had no notion of "public": `documents.visibility` existed only as an unused default
  `internal`, so nothing from the drawing set could reach the portal except plans and the elevation floor
  picker (ADR-0014).
- `site_features` existed as a table and an admin list (kind, name, polygon, `is_public`) with a create
  endpoint only: no update or delete, no drawing on the site plan, nothing in the snapshot, nothing in 3D.
- Unit media is per unit (ADR-0004): a developer with 99 apartments of four plan types would upload the
  same interior renders 99 times, and the sample project has none. The unit page showed the whole floor
  plan at sheet scale with the unit outlined, and no 3D context.
- The project address is a free `jsonb` (`line1`, `city`, ...). No map anywhere.
- The project page was one long column (hero text, 3D, buildings, floors) without section navigation, a
  gallery or a facts strip; the home page cards had no image.
- A permit import of the sample project was "importing" since 2026-10-25 14:53 because the
  heavy worker was restarted while the other branch's migration `0013` kept `db-migrate` failing; `refresh`
  answered 409 "An import is still running" for ever (`regulatory/service.py`).
- The migration line is blocked for this branch: the dev database is at the other session's revision
  `0013`, `main` ends at `0012`, so a new migration here would fork the chain until that branch merges.

The owner's standing rules apply: nothing synthetic in the product (no invented renders, prices or
surroundings), the developer configures everything through the screens, zero-warning builds, docs with the
code.

Third-party facts (checked 2026-10-26):

- OpenStreetMap embed: `https://www.openstreetmap.org/export/embed.html?bbox=<w>,<s>,<e>,<n>&layer=mapnik
  &marker=<lat>,<lng>` renders a map in an iframe without a key or a script. The OSMF tile usage policy
  requires attribution ("© OpenStreetMap contributors") and asks heavy users to run their own tiles; the
  volume threshold is not stated as a number. **Unverified:** whether a public portal with thousands of
  views a day counts as heavy use; a self-hosted tile server or a paid provider is the fallback (Revisit).
- Nominatim (`nominatim.openstreetmap.org/search`) is a one-request-per-second, attributed, no-bulk
  geocoder for the reviewer's manual lookup; it resolves the sample street ("ლეო კვაჭაძის ქუჩა") and the
  numbered buildings `19/4`, `19/5`, `19/14`, not the permit's `19გ`. The product does not call it; the
  Publish page links to the OSM search for the typed address.
- glTF 2.0 textures: `KHR_texture_transform` is not needed; per-primitive `TEXCOORD_0` with an embedded
  JPEG image (`bufferView` + `mimeType image/jpeg`) is core glTF and loads in three.js `GLTFLoader` 0.170
  (already in the viewer). Texture width 1024 px keeps four facades under 1 MB per building.

## Decision

1. **Render documents marked `public` are the gallery.** `documents.visibility` becomes editable
   (`PATCH /documents/{id}` with `visibility: internal | public`, audited) and shows as a slide toggle "Show
   in portal gallery" on the document card for `render` documents. The snapshot (`publishing/snapshot.py::
   _gallery`) publishes every processed, non-excluded page of each public render document, in natural title
   and page order, as `gallery[] = {asset, url, width, height, caption, document, page}`; the first item is
   the tenant site's project-card `cover`. Readiness adds the warning `gallery` ("No renders in the portal
   gallery") that never blocks publishing. `GALLERY_KINDS = ("render",)`: plans, sections and elevations
   stay internal unless this list grows.
2. **Facade drawings are mapped onto the massing.** For each building the reviewer assigns an elevation sheet,
   a region on it (normalised ring) and an optional `flip` to one of the four sides of the building's
   minimum-area rectangle (`massing.building_rectangle`, sides numbered clockwise on the y-down sheet from the
   smallest `(x, y)` corner, outward normal `(dy, -dx)`). The choices live in
   `projects.site_frame.facades[building_id] = [{side, sheet_id, region: {ring}, flip}]` (no migration while
   the chain is blocked; Revisit). `GET /projects/{id}/footprints` returns `sides` (endpoints and length in
   building metres) and `facades`. The massing builder crops the sheet raster to the region (Pillow, JPEG
   ≤ 1024 px wide). The drawing is an orthographic projection, so every unit wall that *faces* a side
   (outward normals within 25°) and lies within `FACADE_DEPTH_M` = 6 m of it, inside (recesses) or outside
   (balconies), gets a textured primitive whose `u` is the wall's projection on the side as seen from
   outside (`1 − t` unless `flip`) and `v` runs from the building top to its base; other walls keep the
   availability colour. The rectangle comes from the lowest floor that has units other than parking
   stalls (`massing.facade_rings`), the same rule as the footprint endpoint. Saving facades queues a
   massing rebuild.
3. **Site features are drawn on the site plan and published.** `site_features.polygon = {ring}` is normalised
   to the project's site sheet, like unit outlines. `PATCH` and `DELETE /site-features/{id}` complete the
   endpoint set. The placement page draws, clears, renames, deletes and toggles `is_public` per feature with
   one colour per kind. The snapshot publishes public features with a ring as `site.features[] = {kind,
   name, ring, ring_m}` (`ring_m` = ring × `m_per_px` × raster size, present only with a calibrated site
   sheet). The portal site plan fills them; the 3D viewer gets a sky gradient, a ground disc, soft shadows
   and draws `garden` as grass with a deterministic grid of generic trees, `road` and `parking_zone` as
   paving, the rest as light ground. Nothing is invented: without features the ground is a plain disc.
4. **One layout code shares renders between units.** `units.attributes.layout` (1 to 40 characters) is a
   sales-editable field (`rules.ATTRIBUTE_FIELDS`), in the inventory grid and the unit sales form. In the
   snapshot a unit without media of its own shows the public media of the first unit (by code) with the same
   layout and media, each item marked `shared_from: <code>`; the portal unit page says so. The unit page
   also focuses its plan on the unit (`plan-viewer` `focus` input, 2.2 × the outline's box) and shows the
   building in 3D with the unit lit.
5. **The map position is part of the address.** `projects.address.lat` and `.lng` (decimal degrees) are
   edited on the Publish page ("Location", with a link to the OSM search for the typed address); the
   snapshot's `_public_address` passes the text lines and the position, nothing else; the portal project
   page embeds the OSM map around the marker with the attribution line. No key, no script, no tiles served
   by Unitforma.
6. **An import cannot stay "importing" for ever.** `regulatory.STALE_AFTER = 20 minutes`: a `refresh`
   finding a running import older than that closes it as `failed` with the error "worker did not finish within
   20 minutes" and starts the new one; younger imports still answer 409. The project overview shows the stale
   state as a "stalled" chip with the hint to use "Check registry".
7. **The project page is one guided page.** Hero with the cover image and thumbnails, a facts strip (units,
   available, price from, floors, completion), a section sub-navigation (Overview, Buildings, Gallery, Map,
   Units), the first render beside the 3D view, a gallery with a `<dialog>` lightbox, the map section, and
   the home page cards with cover images. All styling through the ADR-0009 tokens; the portal's initial
   bundle stays under the 400 kB budget (374.00 kB on 2026-10-26).

## Options considered

### Option A: public render documents form the gallery; drawings become facade textures; reviewer-drawn features and generic trees form the environment; one layout code shares renders (chosen)

Pros: everything shown comes from the developer's own files and choices, so nothing is synthetic; no new
upload path, no new table, no migration; the 3D view shows the real facades the architect drew.
Cons: a facade drawing is a flat orthographic image, not a photoreal render; features must be drawn by hand
on a site plan; renders shared by layout can mislead when the layout code is set carelessly.

### Option B: a separate "project media" upload for the gallery and per-unit renders only

Pros: a dedicated upload is familiar from unit media. Cons: the renders already exist in the drawing set the
permit import brought in, so the developer would upload them twice; 99 apartments of four types would need
99 uploads of the same images; another media table and policy to carry.

### Option C: procedural facades (window grids from the floor count) and surroundings imported from OSM

Pros: no drawing work; every building gets windows and a street network. Cons: invented facades and
buildings around the site are exactly the synthetic content the owner forbids in the product; OSM building
footprints near a new development are usually missing or wrong.

### Option D: AI-generated interior and exterior renders from the plans

Pros: "renders to imagine how it will be" for every unit. Cons: generated images presented to buyers as the
future apartment are a legal and trust problem, cost per render, and the owner has not asked for them;
`media.is_ai_generated` exists from ADR-0004 for the day he does. Out of scope here.

### Option E: Leaflet or Google Maps for the location

Pros: Leaflet gives marker styling and offline tiles; Google gives Georgian addresses and Street View. Cons:
Leaflet adds ~40 kB of script and a tile provider to pay or run; Google needs a key per tenant and billing.
The iframe embed costs nothing and can be swapped later.

### Option F: do nothing until a real architect's site plan and renders arrive

Rejected: the sample project already holds renders and elevations; the owner asked for all four points.

## Trade-off analysis

| Axis | A (chosen) | B media upload | C procedural + OSM | D AI renders | E map libraries |
|---|---|---|---|---|---|
| Synthetic content in the product | none | none | facades and surroundings invented | images invented | none |
| New storage | `site_frame.facades`, `attributes.layout` | media table | none | media rows | none |
| Migration now | no | yes | no | no | no |
| Reviewer work per project | mark 4 regions, draw features, set layouts | upload renders twice | none | review each render | none |
| Portal bundle | +0 kB script, CSS only | +0 | +0 | +0 | +40 kB (Leaflet) |
| Cost per view | OSM iframe only | — | OSM API | render cost | tiles or key |

## Consequences

Easier: the portal shows the developer's renders, facades, surroundings and location without a designer;
the gallery and the cover follow a document toggle; a stuck import heals on the next click.

Harder: reviewers must keep the layout code consistent across units, or a buyer sees another plan's renders
(the portal states "renders of plan type X"); facade textures only look right when the marked region is the
drawing itself without the title block; two JSON shapes without format markers (`site_frame.facades` and
`attributes.layout`) are read tolerant of missing keys and must stay so on every review; the massing GLB
grows by up to four JPEGs per building (≤ 1 MB). The facade rectangle is fixed per building by
`geometry.collect` from every unit (`BuildingSolids.facade_rect`) before the portal build drops unlisted
units, so withdrawing the storage rooms that define it does not move the drawings.

Revisit: move `site_frame.facades` to `buildings.facades jsonb` (or a table) once the migration chain is
free again (after ADR-0015's branch merges); OSM embed volume against the tile policy before a tenant goes
live, with a self-hosted tile server as the fallback; a site-plan import from the permit (the architect's
გენგეგმა) so features can be drawn without a manual upload; trees and paving stay generic until the owner
decides whether a tenant may upload its own ground textures.

**Out of scope here:** AI-generated renders (Option D; the owner decides); DWG conversion (ADR-0006 D);
buyer accounts and inquiries (plan Phase 5); custom map providers.

## Action items

### Phase A: backend

- [x] A1 `api/schemas.py`: `DocumentUpdate.visibility`, `SiteFeatureUpdate`, `InventoryRow.layout`,
      `SalesChanges.layout`, `FootprintOut.sides` and `facades`; `documents/service.py::update_document`
      handles `visibility` with an audit row.
- [x] A2 `projects/service.py` `update_site_feature`, `delete_site_feature`; `api/admin_projects.py`
      `PATCH`/`DELETE /site-features/{id}`.
- [x] A3 `sales/rules.py` `ATTRIBUTE_FIELDS = ("layout",)` and validation; `sales/service.py` writes
      `units.attributes.layout`, inventory row and `public_view` emit `layout`;
      `tests/test_sales_layout_attribute.py`.
- [x] A4 `geometry/massing.py`: `FacadeImage`, `building_rectangle`, `rectangle_sides`, `facade_rings`,
      `_faces_side`, textured primitives and embedded images in the GLB; `geometry/service.py`
      `facade_assignments`, `facade_images`, footprints `sides`/`facades`; `tests/test_massing_facades.py`
      (rectangle, sides, textured GLB, flip, recessed walls and balconies, parking excluded).
      *Found while implementing:* the first build on the sample project textured 11 of 99 units: the
      rectangle was taken over all units, so the ground-floor parking stalls north of the house defined
      it, and only walls exactly on the rectangle counted. Both rules changed on 2026-10-26 (projection
      within 6 m, parking excluded, lowest floor as in the footprint endpoint).
- [x] A5 `publishing/snapshot.py` `_gallery`, `_site_features`, layout donor media with `shared_from`,
      `_public_address` with `lat`/`lng`; `publishing/service.py` readiness warning `gallery`;
      `publishing/portal.py` project-card `cover`.
- [x] A6 `regulatory/service.py` `STALE_AFTER` and the stale-row close in `refresh`.
- [x] A7 Tests: `test_phase4_publishing.py::test_portal_gallery_site_features_map_and_shared_layout_media`
      (gallery and cover, readiness warning, features in sheet and metre coordinates, internal feature and
      address keys kept out, shared media with `shared_from`), `test_regulatory_tasge.py::
      test_stale_import_is_closed_by_the_next_refresh`; the readiness expectation gained the `gallery` warning.
      *Found while implementing:* tenant tables `FORCE ROW LEVEL SECURITY` on their owner too, so a test's
      direct `UPDATE` needs `set_config('app.scope', 'platform', true)` first.
- [x] A8 `openapi.json` and the api-client typings regenerated (`npm run api:generate`).

### Phase B: admin app

- [x] B1 `documents.page.ts`: "Show in portal gallery" toggle and "In portal gallery" chip on render cards.
- [x] B2 `placement.page.ts`: site features card (add, draw on the site plan, clear, rename, delete,
      public toggle, one colour per kind); facades card per building side (elevation sheet, "Mark area" on a
      second plan viewer, flip) saving into `site_frame.facades` and queuing the massing rebuild.
- [x] B3 `publish.page.ts`: "Location" section (`lat`, `lng`, OSM search and view links).
- [x] B4 `inventory.model.ts`, `unit-sales.model.ts`, `unit-sales.page.ts`: layout column and field.
- [x] B5 `project-detail.page.ts`: "stalled" chip and hint for imports older than 20 minutes.
- [x] B6 `guide/guide-content.ts`: documents (gallery toggle), placement (features, facades), publish
      (location), inventory and unit sales (layout), project overview (stalled import) entries.
- [x] B7 Placement page: the plan viewer is hidden until a site sheet is chosen (no blank 550 px box);
      each facade side says which edge of the plan it is (top, right, bottom, left); the admin side menu
      paints its dark background through Material's `--mat-sidenav-container-*` tokens (MatSidenav's own
      styles come after the global sheet and had turned the menu light with light text).

### Phase C: portal

- [x] C1 `portal-api.ts` types (`GalleryItem`, `SiteFeatureDoc`, `cover`, `features`, `layout`,
      `shared_from`, address position).
- [x] C2 `project.page.ts`: hero with cover and thumbnails, facts strip, section sub-navigation, render
      beside the 3D view, gallery with lightbox (styles in `styles.scss` to stay under the component budget),
      map embed with attribution; `home.page.ts` cover images.
- [x] C3 `viewer-3d/massing-viewer.ts`: `siteFeatures` input, sky gradient, ground disc, shadows, edges,
      feature shapes and generic trees; infos deduplicated per unit.
- [x] C4 `plan-viewer.ts` `focus` input; `unit.page.ts` plan focus, "In the building" 3D with the unit
      lit, shared-renders note; `building.page.ts` passes the features.
- [x] C5 Screenshot pass (desktop and phone) over home, project, building and unit pages after publishing
      the sample project (v5 on 2026-10-26). Fixed on the way: `lucideChevronLeft` was not registered
      (lightbox arrow), `PCFSoftShadowMap` no longer exists in three r18x (`PCFShadowMap`), gallery
      captions of a document titled only with a number read "Render n".

### Phase D: docs

- [x] D1 This ADR; README status paragraph and decision list; plan §11.3; `docs/BACKLOG.md` rows for the
      open items; `frontend/README.md` portal section.

### Phase E: the sample project and open decisions

- [x] E1 Sample project `permit-1127975` (2026-10-26, published v6): render document "1" public (5 pages
      in the gallery); map position 41.7437, 44.7224 (the OSM cluster of the street's `19/x` buildings,
      about ±100 m: the permit's `19გ` is not in OSM, the owner can correct it on the Publish page); the
      import stuck since 2026-10-25 14:53 closed as failed by "Check registry", whose new import brought 10
      more permit files, among them the 1:500 general plan; that plan's page 1 calibrated on the building's
      62.30 m length (height check 15.04 m against 15.20 m printed), chosen as the site frame, building A
      placed on it (tx 14.96 m, ty 12.70 m, no rotation); the four facades assigned (document "2" pages
      2, 4, 1, 3 for the top, right, bottom and left sides, regions marked by eye); 11 public features drawn
      from the general plan's legend (2 roads, 3 parking zones, 2 green areas, the playground, 3
      entrances), rectangles and an ellipse within about 1 % of the sheet: approximate, for the owner to
      refine on the placement page. No prices (owner's request). Open: apartments №3 and №15 without a
      closed outline, the three February documents of the first import still "queued".
- [x] E2 Decided 2026-10-26: AI-generated 3D plan renders are allowed behind staff review and a visible
      "generated" label (ADR-0017); exterior AI renders and tenant-uploaded ground textures stay out.
- [x] E3 Done 2026-10-26 (expand release): migration `0015_building_facades` adds `buildings.facades`
      `{"v": 1, "items": [{side, sheet_id, region, flip}]}` and backfills it from the site frame;
      `PATCH /buildings/{id}` takes `facades` (validated: one per side, current sheets of the project);
      `geometry.facade_assignments` reads the column and falls back to the legacy key; every write is
      mirrored into `site_frame.facades` so the previous release keeps reading. Test:
      `tests/test_building_facades.py`. *Found while implementing:* the backfill matched no rows until
      the migration took the platform scope (`FORCE ROW LEVEL SECURITY` binds the owner too); noted
      in `migrations/rls.py`. The dev database was backfilled by hand after the first run.
- [ ] E5 Contract release (the one after 0015): stop mirroring into `site_frame.facades`, migrate any
      remaining legacy entries, drop the key from `site_frame`, remove the fallback in
      `facade_assignments`.
- [ ] E4 OSM embed volume against the tile usage policy before the first tenant goes live; fallback plan
      (self-hosted tiles) written into the runbooks.
