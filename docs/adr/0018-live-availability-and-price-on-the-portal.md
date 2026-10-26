# ADR-0018: Availability and price reach the portal live; structure stays versioned

- **Status:** accepted (2026-10-26; implemented 2026-10-26)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §6.6 (public fields), §7.1 (navigation model), §13.1 (publishing), §13.2 (read models), ADR-0004 (unit sales), ADR-0011 (massing follows mapping)

## Context

The owner sold a unit on 2026-10-26 and found that the portal still showed it as available until he
published a new version: "after the apartment sold, you need to publish new version. it is not necessary".
What the code does today:

- `publishing/snapshot.build` writes one immutable JSON document per publication (`publications.snapshot_key`)
  with the project text, site, buildings → floors → unit outlines, each floor unit carrying its
  `availability`, and a precomputed `stats` block (`units`, `available`, `price_from`, areas, rooms). The
  portal serves that document from an in-process LRU (`publishing/portal.load_doc`) under `max-age=5`.
- The same build writes one `published_units` row per listed unit (`availability`, `price_amount`,
  `currency`, `area_m2`, `rooms`, `entrance`, `listed`, and `data`, the unit's public view from
  `sales.public_view`). The unit list, its filters and the unit page read those rows.
- `sales/service.apply_changes` records availability and price changes on `unit_sales` with history events
  and audit rows; nothing touches the live publication. A sale therefore waits for the next
  `POST /publications` (snapshot, massing copy, asset copies: seconds, plus a version in the history).
- Listing a unit ("Make public", "Link only", "Withdraw") is a publication decision: the next build adds or
  drops the unit from the snapshot; outlines, plans and renders are structure that reviewers approve.

## Decision

1. **A sales change to a unit of the live publication lands on the portal in the same transaction.**
   `apply_changes` calls `publishing/live.sync_unit(db, project, unit)` after its own updates: it finds
   the live publication (`current_publication`) and the unit's `published_units` row keyed by
   `(publication_id, unit_id)`; when the row exists it writes `availability`, `price_amount`, `currency`
   and patches `data["availability"]` and `data["price"]` with the values `sales.public_view` produces
   for the current inventory row, so the public-field switches, "price on request" and the per-m²
   figures follow the same rules as a build. No job, no new version. A unit outside the live
   publication, and every preview publication, is left alone: previews stay a picture of their build.
2. **The project document is overlaid at read time.** `portal.with_live_sales(db, pub, doc)` reads the
   publication's rows (one indexed query) and returns a new document whose floor units carry the live
   `availability` and whose `stats.available` and `stats.price_from` are recomputed with the snapshot's
   rules (`price_from` is null unless every priced unit shares one currency). The cached document is
   never mutated. The unit list and the unit page need no overlay: they read the rows.
3. **Listing stays a publish decision.** "Make public", "Link only" and "Withdraw" still take effect with
   the next version, like outlines, plans, renders and texts; the Publish page says which changes are
   live and which wait for a version.
4. **Costs.** Write path: one SELECT and one UPDATE per sales change, inside the existing transaction.
   Read path: one SELECT of the publication's rows per project-document request (about a hundred rows
   here), behind the 5-second cache; nothing for the unit list and unit page.

## Options considered

### Option A: write-through to the read-model rows plus a read-time overlay on the document (chosen)

Pros: the portal reflects a sale within the 5-second cache window; the snapshot file stays immutable
and reproducible; no new table; cost is one UPDATE per sales change and one query per project page.
Cons: two places must agree on the rules (the snapshot build and the overlay); reviewers must keep
`sales.public_view` the single source for the unit's price shape.

### Option B: rewrite the snapshot document on every sales change

Pros: one read path. Cons: a storage write per sales change, concurrent changes race on one file, the
in-process document cache on every replica must be invalidated, and "immutable snapshot" stops being true.

### Option C: publish a new version automatically after each sales change

Pros: no new code path. Cons: a version per sale in the history, seconds of massing and asset copying per
change, and bulk edits would create dozens of versions.

### Option D: do nothing, keep "publish after a sale"

Rejected by the owner.

## Trade-off analysis

| Axis | A (chosen) | B rewrite | C auto-publish | D nothing |
|---|---|---|---|---|
| Delay after a sale | ≤ 5 s | ≤ 5 s | seconds to minutes | until someone publishes |
| Cost per sales change | 1 UPDATE | 1 storage PUT + cache purge | a full build | 0 |
| Cost per project page | +1 query | 0 | 0 | 0 |
| Snapshot immutable | yes | no | yes | yes |
| History noise | none | none | a version per change | none |

## Consequences

Easier: sales staff mark a unit sold or change its price and buyers see it at once; the Publish page is
for structure and texts, not for every price edit.

Harder: two rules to hold on every review: `sales.public_view` is the only producer of a unit's public
price shape (the live sync reuses it, never hand-builds it), and `with_live_sales` must be applied
wherever the project document is served (today: one endpoint). The publication `summary.unit_counts`
is still the count at build time; the Publish page shows it as such.

Revisit: listing changes live (hide a sold unit at once) if the owner asks; a signal to refresh the
massing colours without a reload.

**Out of scope here:** listing changes, outlines, plans, renders and texts (versioned as before); the
admin massing page (reads the project directly).

## Action items

- [x] A1 `publishing/live.py` `sync_unit`; call from `sales/service.apply_changes` (local import, same
      transaction).
- [x] A2 `publishing/portal.py` `with_live_sales`; applied in `api/portal.project`.
- [x] A3 `tests/test_phase4_publishing.py::test_a_sale_reaches_the_portal_without_a_new_version`:
      availability and price flip on the unit page, the list filter and the project document (floor
      unit and stats) with the version unchanged; an earlier preview keeps its picture.
- [x] A4 Publish page text: which changes are live, which need a version; plan §6.6 and §13.1; README.
