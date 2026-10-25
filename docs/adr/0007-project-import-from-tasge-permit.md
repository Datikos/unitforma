# ADR-0007: Bootstrap a project from a Tbilisi building permit (tas.ge)

- **Status:** accepted (2026-10-25; implemented 2026-10-25)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §13 (document workflow), §15 epic E10, `docs/research/regulatory-permit-data.md`

## Context

The owner's request on 2026-10-25: the Tbilisi Architecture Service publishes every building permit
with its drawings at `https://tas.ge/?p=publicpage&documentId=<id>`; given that URL the platform
should pull the whole record and build the project from it.

What is known (research note of 2026-10-25, verified on permit 1127975, prototype in
`tools/research/tasge/`):

- The public page is a shell. The data comes from one unauthenticated DWR POST on
  `docs.tbilisi.gov.ge` returning about 370 KB of JavaScript; attachments download from
  `docs.tbilisi.gov.ge/DownloadServlet?downloadCase=2&attachedFileId=<id>` without a session; signed
  decisions sit on a third host, `esign.tbilisi.gov.ge`. No robots.txt, no terms of use, no search.
- The record holds the permit identity and dates, nomenclature (category, class, action, stages),
  class-calculator values (height above and below 0.00, K2 area), parcels from the national registry
  (cadastral code, area, purpose, owner), 13 technical-economic indicators with Georgian labels, and
  about 170 attachment rows (115 PDF, 20 JPG, 20 ArchiCAD `.pla`, 10 `.rar`), of which one per
  fieldset is current. The floor-plan PDF of the sample is a 51-page vector ArchiCAD export, the
  format the mapping pipeline was tuned on (plan §13.2 notes).
- The record also holds personal data: names, personal numbers, phones and emails of the applicant,
  the architect, experts and the handling official, and the decision text names people. The prototype
  drops these by field label.
- What exists on `main`: `projects.regulatory` JSONB (migration 0002, returned by `ProjectOut` on
  every project read and writable through `PATCH /projects/{id}`), `documents.service.create_document`
  / `create_upload_intent` / `complete_upload`, the `documents.ingest_revision` task, `httpx` as a
  dependency (used by the Kratos client), api and workers on the Compose `egress` network,
  `import-linter` forbidding only `core` → feature imports. `safe_filename` keeps Georgian letters.
- Unit outlines are never in the permit data; they come from the drawings through the review flow
  (ADR-0006 Decision 7 applies: 2D sources give the schematic model).

## Decision

1. **A new backend module `regulatory`** with `tasge.py` (fetch, DWR parse, normalise, PII filter,
   ported from the prototype) and `service.py` (preview, import, document creation). It imports the
   `documents` and `projects` services; nothing imports it except `api` and `jobs`.
2. **Input is an id, never a host.** `POST /api/v1/admin/tenants/{tenant_id}/regulatory/tasge/preview`
   takes `{"reference": "<url or id>"}`; the service extracts `documentId` digits with a regex and
   builds every request from three constant hosts (`docs.tbilisi.gov.ge`, `tas.ge`,
   `esign.tbilisi.gov.ge`). A pasted host is ignored. The DWR call has a 20 s timeout and a 5 MB
   response cap; attachment downloads 300 s and 50 MB each; every request carries
   `User-Agent: unitforma/<version> (+https://unitforma.com)`. TLS verification stays on.
3. **Personal data never persists.** The raw payload lives only in the request that parses it. The
   stored record is the normalised, PII-filtered shape of the prototype: fields whose label or fieldset
   contains a marker (personal number, phone, email, first and last name, power of attorney) are
   dropped, `decision_text_html` is not stored, parcel owners that do not look like a company are
   stored as `<redacted person>`. Audit rows carry the external document id, the project id and counts.
4. **Home of the record: `regulatory_imports`** (migration 0009, RLS from `migrations/rls.py`):
   `id, tenant_id, project_id, source = 'tasge', external_id, status fetched | importing | done |
   failed, requested_by, started_at, finished_at, record JSONB, stats JSONB, error, created_at`.
   `projects.regulatory` gets only a summary: `{source, external_id, application_no, status,
   decided_at, address, cadastral_codes, import_id}`. One import row per fetch; the latest one is the
   project's current permit record.
5. **Import = project + building + documents, floors stay the user's.**
   `POST .../regulatory/tasge/import` with `{"reference", "slug", "name", "building_code"}` (slug and
   name default from the record: name from the functional-purpose field, slug from it) creates the
   project (`project` WRITE), one building with the given code (default "A", the preview proposes the
   code found in the functional-purpose text such as "A-9/10"), writes the summary into
   `projects.regulatory`, inserts the `regulatory_imports` row with status `importing`, and enqueues
   `regulatory.import_attachments` on the `docs` queue. Floors are not created: the preview shows the
   heights above and below 0.00 as hints next to the existing "Generate floors" control.
6. **Attachments go through the normal upload path.** The worker task takes every attachment with
   `latest_in_fieldset = true` and extension `.pdf`, `.jpg`, `.jpeg`, `.png`: `create_document` with
   kind by fieldset keyword (plans → `floor_plan`, general plan → `site_plan`, sections → `section`,
   facades → `elevation`, photomontage and axonometric → `render`, everything else → `permit`),
   title = fieldset title, `source = {system: "tasge", document_id, fieldset_id, attached_file_id,
   download_url}`, then `create_upload_intent` + `put_bytes` + `complete_upload` + enqueue
   `documents.ingest_revision`. `.pla` and `.rar` are listed in `stats.skipped` with the reason "no
   open parser" / "archive". A failed download marks only that attachment in `stats.failed`; the import
   ends `done` when every eligible file was tried, `failed` only when the record itself cannot be
   fetched. Documents are filed at project level (multi-block sets are the norm, plan §13.2).
7. **Re-import is idempotent per attachment.** `POST .../projects/{project_id}/regulatory/tasge/refresh`
   fetches the record again, updates the summary and creates a new revision only for attachments
   whose `attached_file_id` is not yet on a document of this project (matched through
   `documents.source`). A refresh while an import is `importing` returns 409.
8. **Authorization and flag.** Preview and import need `project` WRITE; refresh needs `documents`
   WRITE. Setting `UF_REGULATORY_TASGE_ENABLED` (default `true`) switches the endpoints off with 404
   and hides the card in the admin app (`/api/v1/admin/me` capabilities are not touched; the card
   handles the 404).
9. **Admin screen.** A "Start from a building permit" card on the projects page: paste URL or id →
   preview (permit number, status, address, category, class, heights, indicators table, attachments
   grouped by kind with the ones that will be imported marked, skipped ones with reason) → editable
   slug, name, building code → Import → project detail with an import status card (counts, failures,
   link to documents). Every label on the card is explained in a guide line under it.
10. **Politeness toward the source.** One fetch per user action, no enumeration, no scheduled polling
    in this ADR. The research note's rules are copied into the module docstring.

## Options considered

### A. Where the record lives

- **A1 (chosen): `regulatory_imports` table plus a summary in `projects.regulatory`.** Pros: history
  per fetch, status and error with the row, project reads stay small. Cons: one more table and RLS set.
- **A2: whole record in `projects.regulatory`.** Pros: no migration. Cons: 140 KB on every project
  GET and list, overwritable by `PATCH /projects/{id}`, no import status or history.
- **A3: record as a `permit` document in object storage only.** Pros: no table. Cons: the preview and
  the project card need queryable fields; a JSON object is not a status.

### B. How the drawings arrive

- **B1 (chosen): worker task through the existing upload functions.** Pros: ingest, sheets, floor
  suggestions, lineage all unchanged; failures per file. Cons: the API process never touches the
  files, so the user waits for the status card.
- **B2: download in the API request.** Pros: simpler code. Cons: 20 files of up to 50 MB in one HTTP
  request; the admin request would run minutes.
- **B3: store only the download URLs and fetch lazily on first open.** Pros: fastest import. Cons:
  the source can disappear; the pipeline needs the bytes anyway.

### C. Input validation

- **C1 (chosen): id only, constant hosts.** Pros: no server-side request forgery surface. Cons: a
  second municipality needs its own adapter.
- **C2: fetch the pasted URL.** Rejected: an authenticated staff user could point the worker at the
  internal network.

### D. Floors

- **D1 (chosen): none created; heights shown as hints.** Pros: floors come from the drawings' level
  markers after ingest, which is already built and reviewed. Cons: one extra click.
- **D2: create floors from storey count in the explanatory note.** Rejected: the count is prose
  ("სართულიანობა-4") and unreliable; the owner's rule is that he enters structure himself.

## Trade-off analysis

| Axis | A1 | A2 | B1 | B2 | C1 | C2 |
|---|---|---|---|---|---|---|
| Migration | yes | no | no | no | no | no |
| Project GET size | unchanged | +140 KB | — | — | — | — |
| Request duration | ms | ms | ms + worker | minutes | — | — |
| Failure granularity | row | none | per file | all or nothing | — | — |
| Security surface | none | none | worker egress to 3 hosts | api egress | none | SSRF |

## Consequences

**Easier.** A Georgian developer starts a project from a permit id with the drawings already in the
pipeline; address, parcel and building parameters are filled; the mapping flow is unchanged.

**Harder.** Preview and import hold the request's database connection (RLS context set at session start) across the registry call, up to 20 s; admin-only and one per click on a pool of 10, so accepted here, but it breaks the "no connection across a network call" rule and must not be copied to a buyer-facing path. One more outbound dependency on an undocumented municipal endpoint; when it changes the
import fails with a clear message and the upload path still works. Reviewers must hold the rule that
the import never creates floors or units. Tests use synthetic DWR bodies, never the sample record,
which carries a real company name and parcel.

**Operations.** No new container; the worker downloads at most 50 MB per file to object storage. A
failed import is visible on the project card and in `regulatory_imports.error`.

**Revisit.** After three real imports: the fieldset → kind keyword table, the per-field label map, and
whether a daily refresh is wanted (then a scheduler job with the same politeness rules).

**Out of scope here:** scheduled refresh, pre-scan port (`scan_plans.py`; the ingest hints cover it),
ArchiCAD `.pla`, `.rar` archives, signed decision files, other municipalities, buyer-visible permit
data (publication snapshot).

## Action items

Phase A: backend
- [x] A1 Migration `0009_regulatory_imports`: table of Decision 4 with RLS; model `RegulatoryImport`
      in `tenants/models.py`.
- [x] A2 `regulatory/tasge.py`: `extract_document_id`, `parse_dwr`, `fetch_record` (httpx, caps,
      User-Agent), `normalise` with PII filter, `kind_for_fieldset`, `suggest_building_code`,
      `suggest_slug`.
- [x] A3 `regulatory/service.py`: `preview`, `start_import` (project + building + summary + row +
      enqueue), `refresh`, `import_attachments` (worker body), summary writer.
- [x] A4 `jobs/tasks.py`: `regulatory.import_attachments` on queue `docs`.
- [x] A5 `api/admin_regulatory.py`: preview, import, refresh, `GET .../projects/{id}/regulatory/imports`;
      schemas in `api/schemas.py`; router in `main.py`; setting `regulatory_tasge_enabled`.
- [x] A6 Tests `test_regulatory_tasge.py`: synthetic DWR body parses; PII-labelled field and person
      owner are absent from the normalised record; kind mapping; id extraction refuses a foreign host
      and accepts URL and bare id; API preview/import/refresh with the fetcher swapped for a fake
      (project, building, summary, documents with revisions and `source`, 409 on concurrent refresh,
      wrong role refused, cross-tenant read empty).
- [x] A7 OpenAPI regenerated (`openapi.json`, `openapi.d.ts`).

Phase B: admin app
- [x] B1 `UnitformaApi`: `tasgePreview`, `tasgeImport`, `tasgeRefresh`, `listRegulatoryImports`.
- [x] B2 `projects.page.ts`: "Start from a building permit" card with preview and import (Decision 9).
- [x] B3 `project-detail.page.ts`: permit card (summary, latest import status, counts, failures,
      refresh button) and height hints beside "Generate floors".
- [x] B4 `ng build admin`, `ng test admin`.

Phase C: docs
- [x] C1 Plan §15 E10 → "ADR-0007, on `main`"; §13.1 flow gets the permit entry point.
- [x] C2 `docs/research/regulatory-permit-data.md` §6 marked superseded by this ADR.
- [x] C3 README status; `.env.example` line for `UF_REGULATORY_TASGE_ENABLED`.
      *Found while implementing (2026-10-25):* attachments are dropped not only when the fieldset title
      carries a personal-data marker but whenever any field of that fieldset does (the client-information
      section holds identity scans next to the company name). The admin card learns that the import is
      switched off from the 404 of the preview call, so no capability flag was added to `/admin/me`. The
      building page of the dev stack was not rebuilt here; the containers run the committed images.
      The permit's explanatory note is not copied into `project.description`: that field is shown to
      buyers on the portal's project page and in snapshots; the note stays in `regulatory_imports.record`.
