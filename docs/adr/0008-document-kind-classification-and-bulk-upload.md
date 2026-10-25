# ADR-0008: Documents classify themselves; one upload button for many files

- **Status:** accepted (2026-10-25; implemented 2026-10-25)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §13.1 step 2, §13.2 "File intake" row ("Classification kind from filename/title block: assisted")

## Context

The owner's request on 2026-10-25: the Documents page asks for a Kind before every upload and
takes one file at a time; the platform should categorise the files itself, take several at once,
and let the reviewer fix only what stayed uncategorised.

What `main` has:

- `documents.kind` is one of `site_plan, floor_plan, section, elevation, render, schedule,
  model_ifc, model_glb, texture, permit, other` (check constraint `ck_document_kind`, migration
  0003); it is set once at `POST /projects/{id}/documents` and never changed afterwards (no PATCH).
- The worker already decides a kind per page in `documents.processing.hints_from_text`
  (`floor_plan` when typed unit labels sit on vector line work, `drawing`, `text_sheet`,
  `unknown`), stored in `sheets.hints.kind` and shown under each sheet thumbnail.
- The permit import (ADR-0007) assigns kinds from Georgian section titles with a keyword table.
- Floor suggestions for project-level documents run only when `kind == "floor_plan"`
  (`documents/jobs.py`), so a wrong kind silently withholds them.
- The admin upload (`documents.page.ts`) creates one document per upload with the chosen kind,
  then runs the presigned PUT and `complete`.

## Decision

1. **Two-step guess, confirm in place.** A document created without a kind (or with
   `unclassified`) gets a kind from its title and file name at creation (`documents/classify.py`
   `kind_from_name`, Georgian, Latin-transliterated Georgian and English keywords); after
   processing, the worker refines from page content (`kind_from_pages`: at least half of the pages are floor plans →
   `floor_plan`, text-only pages with areas → `schedule`, an image without text → `render`).
   A content guess replaces a name guess; nothing replaces a kind a person set.
2. **The origin of the kind is stored.** `documents.kind_source` ∈ `manual | filename | content |
   pending` (migration 0010, default `manual` for existing rows); `kind` gains the value
   `unclassified`, used together with `kind_source = pending`. Permit-imported documents keep
   `manual`, since their kind comes from the registry's section title.
3. **`PATCH /documents/{id}`** sets `kind` (→ `kind_source = manual`), `title` and `building_id`,
   audited as `document update` with before and after. The only write path for a kind after
   creation.
4. **Floor suggestions follow the final kind.** The worker classifies before it decides whether a
   project-level document gets level-marker floor suggestions; setting a kind by hand on an
   unclassified document does not re-run suggestions (a new revision does).
5. **Upload: one button, many files.** The upload card loses the Kind field; it keeps Building
   (optional, applied to all) and Source note, takes several files, and creates one document per
   file with the file name as title and `kind = unclassified`. Progress shows files done of total.
   "Upload new revision" on a card keeps the single-file path.
6. **Every card shows the kind as a chip with its origin** ("guessed from name", "guessed from
   content", "set by you", "uncategorized"), a select beside it to confirm or change, and a filter
   "Needs a kind" with a count. Guessed kinds are tinted until confirmed; uncategorised ones are
   highlighted. A guide line under the upload explains the two steps.

## Options considered

- **O1 (chosen): name at upload, content after processing, confirm in place.** Pros: a kind on
  nearly every file at once, refined for free by the worker, one click to confirm. Cons: a new
  column and kind value (expand migration), a PATCH endpoint.
- **O2: content only.** Pros: no name heuristics. Cons: no kind for a minute after upload;
  elevations and renders are not told apart from content.
- **O3: name only.** Pros: smallest. Cons: "project.pdf" stays uncategorised every time.
- **O4: split a PDF into documents by page kind.** Rejected here: a document keeps one kind; the
  sheet-level `hints.kind` and exclusions already handle mixed sets (plan §13.2 sheet sets).

## Consequences

**Easier.** Drag ten files, confirm chips, map. Permit imports and manual uploads share the chip
UI. Wrong kinds are visible and fixable instead of permanent.

**Harder.** Two keyword tables to keep (`classify.py` for files, `regulatory/tasge.py` for
registry sections); reviewers must hold the rule that the worker never overwrites a manual kind;
clients that relied on `kind` being final at creation must read `kind_source`.

**Operations.** None: one column, one constraint, no new container or job.

**Revisit.** After three real drawing sets: the keyword table and whether a per-page split (O4)
is wanted; re-running floor suggestions when a kind is set by hand on a project-level document
(today they come with the next revision).

**Out of scope here:** classification of IFC/GLB models (kind is fixed by type), OCR of title
blocks on scans, moving pages between documents.

## Action items

- [x] 1 Migration `0010_document_kind_source`: `kind_source` column with check, `unclassified`
      added to `ck_document_kind`; model `Document.kind_source`.
- [x] 2 `documents/classify.py`: `kind_from_name`, `kind_from_pages`; tests
      `test_document_classify.py` (names in three scripts, page mixes, image, nothing).
- [x] 3 `documents/service.py`: classify on create when the kind is `unclassified`;
      `update_document`; `documents/jobs.py`: content classification before floor suggestions.
- [x] 4 API: `DocumentCreate.kind` defaults to `unclassified`, `DocumentOut.kind_source`,
      `DocumentUpdate`, `PATCH /documents/{id}`; OpenAPI regenerated.
- [x] 5 Admin `documents.page.ts`: multi-file upload, kind chips with origin, inline select,
      "Needs a kind" filter, guide line; `UnitformaApi.updateDocument`.
- [x] 6 Docs: plan §13.2 "File intake" row and §13.1 note, README status.
      *Found while implementing (2026-10-25):* the plan-page share for a content guess is one half, not
      60 %, because a two-page set of a plan and its section sheet is the common case. Setting a kind
      by hand does not re-run floor suggestions (the card says so); permit-imported documents show
      "set by you" because the import passes the registry's kind explicitly. The 0010 downgrade needs
      the platform RLS scope to rewrite rows, as 0007 did.

- [ ] 7 When a kind set by hand turns a project-level document into `floor_plan`, queue
      `documents.resuggest_floors` (it exists since ADR-0010) so its sheets get floor suggestions
      without a new revision.
