# ADR-0022: A layout registry owns the media shared by units of one plan type

- **Status:** accepted (2026-10-26, the owner's "2" on the options; implemented 2026-10-26; the contract step E1 waits for the next release)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §5.3 (unit media, AI disclosure), §6.6 (`public_view`), §7.1 (unit page), §11.2 (admin screens), §11.3 (portal screens), §12.3 (`renders.generate`), ADR-0016 Decision 4 (media shared by layout code, superseded here), ADR-0017 Decision 3 (generated plan renders), ADR-0021 (retention)

## Context

ADR-0016 Decision 4 made `units.attributes.layout` a free-text code and let the snapshot share media
between units with the same code. Verified in the code on 2026-10-26:

- `publishing/snapshot.py` picks one donor per code: the first unit by code that has media of its own.
  A unit **without** media borrows the donor's public media and each item carries `shared_from: <unit
  code>`. A unit **with** media of its own shares nothing and borrows nothing.
- The image therefore belongs to a sellable unit. Which unit is the donor is implicit (the lowest
  code), so the owner asked on 2026-10-26 "where is a place to set image for each layout code?" and
  there was none: the answer was "upload on the lowest-coded unit".
- Selling, re-coding or clearing the media of the donor silently changes what every twin shows.
- A generated 3D plan render (ADR-0017) is requested per unit and costs 0.0336 USD per image. The
  "shared by layout code" promise holds only when the request is made on the donor unit.
- `sales/media.py` is one service keyed on `unit_media.unit_id` (presigned upload, complete, update,
  reorder, delete, audit, signed preview). `renders/service.store_result` writes the generated image
  into the same table. The retention sweep (ADR-0021) removes project, document and `pub/` prefixes
  whose rows are gone; it does not know unit or layout media prefixes.
- `rules.validate` accepts any string of 1 to 40 characters as a layout; the inventory grid and the
  unit form are free-text fields, so a typo makes a new "layout".

The owner chose, on 2026-10-26, a registry per project ("separate registry for layout images to better
link") over a master flag on the unit.

## Decision

1. **A `unit_layouts` table is the home of a plan type.** Columns: `id`, `tenant_id`, `project_id`,
   `code` (1 to 40 characters), `name` (nullable, up to 120 characters), `version`, `created_at`,
   `updated_at`; unique on `(project_id, lower(code))`; the standard tenant RLS policies. Staff with
   the `sales` write right create, rename and delete layouts.
2. **Units link to a layout by foreign key.** `units.layout_id` is a nullable FK to `unit_layouts`
   with `ON DELETE SET NULL`. The API keeps the field `layout` as the code string on the inventory
   row, the unit form, the bulk edit and `SalesChanges`; a written code must exist in the project's
   registry (compared without case, stored in the registry's spelling), `null` unlinks; an unknown
   code is refused with 422. This release also writes the code into `units.attributes.layout` and
   reads it when `layout_id` is null (expand step); the next release stops the mirror (E1).
3. **Layout media are `unit_media` rows owned by the layout.** `unit_media.layout_id` is a nullable
   FK to `unit_layouts` with `ON DELETE CASCADE`, `unit_media.unit_id` becomes nullable, and a check
   constraint requires exactly one owner. Objects of a layout live under
   `t/<tenant>/p/<project>/media/layout/<layout_id>/`. Endpoints: `GET` and `POST
   /layouts/{id}/media`, `PUT /layouts/{id}/media/order`; `/media/{id}/complete`, `PATCH` and `DELETE
   /media/{id}` serve both owners unchanged. Deleting a layout deletes its media objects at once.
4. **A generated render can be requested for a layout.** `unit_renders.layout_id` is a nullable FK
   (`ON DELETE SET NULL`); `POST /layouts/{id}/renders` takes an optional `unit_id` (a member whose
   outline is cropped; default: the first member by code with a current outline) and queues the same
   `renders.generate` job; the stored image is owned by the layout and its alt text names the layout.
   `GET /layouts/{id}/renders` lists them. Approve and reject are unchanged. A render with a joined
   partner (ADR-0017 E4) stays unit-owned. The tenant's daily cap counts both kinds.
5. **The snapshot merges own and layout media, own first.** A unit's public `media` is its own public
   items followed by the public items of its layout, each layout item marked `from_layout: <code>`;
   the unit document carries `layout` (the code) and `layout_name` when the registry has one. The
   hero of the unit page is the first `plan_render` in that order, so a unit's own render wins. The
   donor rule and `shared_from` are gone from new snapshots; the portal still reads `shared_from` in
   publications made before this release until they are republished.
6. **The admin app gets a Layouts page** at `projects/:projectId/layouts` under the Sales menu: one
   card per layout with code, name, member units as availability chips, media count and cover; a
   create form; a media card and a render card that are the same components the unit page uses; rename
   and delete (409 `layout-in-use` while members exist unless `unlink_units=true` is sent). The unit
   form's Layout field and the grid column pick from the registry; both link to the page.
7. **Deleting a layout refuses while units are linked** unless the caller asks to unlink them; a
   rename of the code updates the mirror of every member in the same transaction; an audit row records
   create, rename, delete and the media actions with `entity_type = unit_layout` and `unit_media`.

## Options considered

### Option A: keep the donor rule, add a "layout master" flag on the unit
Pro: no new table. Con: the image still hangs on a sellable unit; selling, re-coding or clearing the
master changes every twin; nothing shows which unit is the master in the portal data.

### Option B: a registry per project; layout media reuse `unit_media` with a nullable owner (chosen)
Pro: one home per plan type, one upload flow, one audit entity, one retention path; the generated
render is spent once per plan; the picker stops typos. Con: a migration with a backfill, a nullable
`unit_id` with a check constraint, a mirror to contract next release.

### Option C: a registry per project with its own `layout_media` table
Pro: a clean one-owner table. Con: a second copy of `sales/media.py`, `store_result`, the signed
preview and the retention rules; two media shapes for the portal to read.

### Option D: a buyer-facing "plan types" page per project
A follow-up once B exists: the registry plus a portal page listing each layout, its render and the
available units. Out of scope here.

## Trade-off analysis

| | A master flag | B registry, shared table | C registry, own table |
|---|---|---|---|
| Migration | one column | one table, three columns, a backfill | two tables, two columns |
| Media code | unchanged | one service, two list and create routes | duplicated service |
| Where the image lives | on a unit | on the layout | on the layout |
| Render cost per plan type | once if staff pick the master | once | once |
| Typos | still possible | refused | refused |
| Retention | unchanged | one prefix rule | two prefix rules |

## Consequences

**Easier:** one place to upload per plan type; the unit page says which layout it belongs to and
links there; a generated render is reviewed once; the portal shows a unit's own media and its
layout's.

**Harder:** reviewers hold two rules on `unit_media`: exactly one owner, and unit-keyed queries never
see layout rows. The code mirror in `units.attributes.layout` must be written on every link change
until E1 lands. A renamed code touches every member row. The "one render at a time" check is per
owner: a unit render is refused with "already running for this unit" while a layout render is
cropping that same unit, and the other way round, until the running one finishes (10 to 60 s). In
the rolling-update window a worker of the previous release that picks up a layout render ignores
`layout_id` and stores the image as media of the source unit; the reviewer then sees it on the unit
page, not on the Layouts page, and uploads or regenerates it for the layout.

**Revisit:** Option D when the owner wants a plan-types page; a layout-level "typical area" or room
facts, which today are read from the member units.

**Out of scope here:** a buyer-facing plan-types page (Option D); layout facts beyond code and name;
importing layouts from a spreadsheet; moving the joined (partner) render to the layout.

## Action items

### Phase A: backend

- [x] A1 Migration `0017_unit_layouts.py` (expand): `unit_layouts` with RLS; `units.layout_id`;
      `unit_media.layout_id`, `unit_media.unit_id` nullable, check `one_owner`; `unit_renders.layout_id`;
      backfill one row per distinct `(project_id, lower(attributes->>'layout'))` under the platform
      scope, then `units.layout_id`; downgrade drops all of it.
- [x] A2 `tenants/models.py` `UnitLayout`, the three columns; `sales/layouts.py` list with counts and
      cover, create, rename (mirror update), delete (409 `layout-in-use`, `unlink_units`), resolve a
      code; `sales/rules.py` validation of `layout` against the registry; `sales/service.py` writes
      `layout_id` and the mirror, `row_dict` reads the code from the registry first.
- [x] A3 `sales/media.py` owner-agnostic: `list_media(unit_id | layout_id)`, `create_intent(owner)`,
      `reorder(owner)`, audit `entity_id` is the owner; `renders/service.py` `request_render(layout=)`,
      `list_renders(layout_id=)`, `store_result` owned by the layout; `renders/jobs.py` passes the layout.
- [x] A4 `api/schemas.py` `LayoutIn`, `LayoutUpdate`, `LayoutOut`, `LayoutRenderRequest`,
      `MediaOut.unit_id | layout_id`, `RenderOut.layout_id`, `InventoryRow.layout_name`;
      `api/admin_layouts.py` routes of Decisions 3, 4 and 6; `main.py` includes the router.
- [x] A5 `publishing/snapshot.py` own-then-layout media with `from_layout`, `layout_name`;
      `sales/service.public_view` passes `layout_name`; the donor code removed.
- [x] A6 Tests `tests/test_unit_layouts.py`: unique code without case, link by code and refusal of an
      unknown code, rename updates members, delete refused then forced, layout media upload and order,
      a layout render from a chosen member and from the default member, the snapshot merge (own first,
      `from_layout`, hero rule, internal items kept out), a unit with the mirror set but `layout_id`
      null still publishes; `test_phase4_publishing.py` shared-layout assertions moved to the registry.
- [x] A7 `openapi.json` regenerated, `npm run api:generate`.

### Phase B: admin app

- [x] B1 `sales/media-list.component.ts` and `sales/render-list.component.ts`: the media and render
      cards as input/output components; `unit-sales/unit-media.component.ts` and
      `unit-renders.component.ts` wire them to the unit store.
- [x] B2 `pages/layouts/layouts.page.ts`, `layouts.store.ts`, `layouts.model.ts`: the Layouts page of
      Decision 6; `app.routes.ts`, `shell/menu.model.ts` (Sales group, segment), breadcrumb.
- [x] B3 `unit-sales.page.ts` Layout field as a picker with a link to the page; the layout-mates note
      says "they share the layout's media"; `inventory.model.ts` layout column as a select from the
      registry; `inventory.store.ts` loads the registry.
- [x] B4 `guide/guide-content.ts`: `layouts` entry; inventory tip and unit-sales controls reworded.

### Phase C: portal

- [x] C1 `portal-api.ts` `from_layout`, `layout_name`; `unit.page.ts` note "Renders of layout L1
      (name): the same plan, the finish may differ" over layout items, hero rule unchanged.

### Phase D: docs

- [x] D1 This ADR; ADR-0016 status line (Decision 4 superseded); README status paragraph; plan §5.3
      schema rows (`unit_layouts`, `units.layout_id`, `unit_media` owner), §11.2 and §11.3 sentences;
      `docs/BACKLOG.md` header and the E1 reference on row 34 (the next-release contract steps).

### Phase E: next release

- [ ] E1 Contract step: stop writing `units.attributes.layout`, read only `layout_id`, migrate
      leftovers, drop the key from the JSON; `rules.ATTRIBUTE_FIELDS` loses `layout`.
