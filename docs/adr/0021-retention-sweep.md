# ADR-0021: The retention sweep removes what nobody can reach any more

- **Status:** accepted (2026-10-26, the owner's "next" on backlog row 5; implemented 2026-10-26)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner): the grace periods below, and whether the first production run is a dry run
- **Plan reference:** §10.3 (consent and retention), §12.3 (`housekeeping.retention`), ADR-0012 (deletes and the `pub/` known gap), ADR-0005 (S3 contract), ADR-0017 (render crops), ADR-0015 (API tokens)

## Context

`housekeeping.retention` ran daily at 03:15 and only wrote a log line (`jobs/tasks.py`, "implemented in
Phase 5"). What accumulates today, verified in the code on 2026-10-26:

- **Upload intents that never completed.** `POST /documents/{id}/uploads` creates a `document_revisions`
  row with `processing_status = "pending"` and a presigned PUT; when the browser never calls `complete`,
  the row stays, with or without an object under its `object_key`. The bulk uploader creates one document
  per file first, so an abandoned upload also leaves a document without any revision.
- **Expired staff invitations** (`staff_invitations.expires_at`, 7 days) and **expired or revoked API
  tokens** (`api_tokens.expires_at`, `revoked_at`): rows only, the audit log keeps the events.
- **Render crops.** Every generated 3D plan render stores the plan crop sent to the model under
  `renders/{unit}/{id}-plan.png` (`unit_renders.input_key`); it is read once, by the reviewer who wants to
  see what the model got, and never after the render is approved or rejected.
- **Orphaned storage prefixes.** A project or document delete queues `storage.delete_prefix` after the
  rows are gone (ADR-0012 Decision 5); when the enqueue or all five attempts fail, the objects stay with no
  row to find them. Nothing lists the bucket against the tables.
- **Assets of retired publications.** `publishing/snapshot.Assets` writes every public file of a version
  under one prefix `pub/{tenant}/{project}/` with content-hashed names shared between versions, so the
  files that only a superseded version used stay until the project is deleted (ADR-0012 known gap).
  `publications.assets` maps each version's public names to their keys, so the live set is known.
- **The job table.** Procrastinate keeps every finished job row (`procrastinate_jobs`); `documents.requeue_stuck`
  alone adds 144 rows a day. Procrastinate 3.10 ships `remove_old_jobs(max_hours, remove_failed, …)`.

Not yet existing, so not swept: inquiry drafts, auth attempts, leads, soft-deleted media (Phase 5),
ended renovation boards (ADR-0020 E8). They join this job when they exist.

## Decision

1. **One daily job, six targets, each with a grace period from settings** (`UF_RETENTION_*`), run by
   `housekeeping.sweep(now)` and returning the counts per target, logged as `job.retention`:

   | Target | Rule | Setting (default) |
   |---|---|---|
   | pending uploads | revision `pending` older than the period: object and row deleted; a document left without any revision and older than the period is deleted too | `UF_RETENTION_PENDING_UPLOAD_HOURS` (24) |
   | invitations | not accepted and expired longer ago than the period | `UF_RETENTION_INVITATION_DAYS` (30) |
   | API tokens | expired or revoked longer ago than the period | `UF_RETENTION_TOKEN_DAYS` (90) |
   | render crops | `input_key` of a render finished longer ago than the period: object deleted, key set to null; the render row stays | `UF_RETENTION_RENDER_INPUT_DAYS` (30) |
   | orphaned prefixes | `t/{tenant}/p/{project}/` without a project row, `…/documents/{document}/` without a document row, `pub/{tenant}/{project}/` without a project row, when the newest object is older than the period | `UF_RETENTION_ORPHAN_DAYS` (7) |
   | retired assets | under `pub/{tenant}/{project}/` of an existing project: every object that no non-retired publication references and that is not a version's snapshot document, older than the period | `UF_RETENTION_RETIRED_ASSET_DAYS` (30) |

   Snapshot documents of retired versions stay (small, and the Publish page's history reads their summary
   row); their images and models go, so a retired version cannot be opened again after the period.
2. **The job table is cleaned by Procrastinate's own task.** After the sweep, `retention` defers
   `procrastinate.builtin_tasks.remove_old_jobs` twice on the `periodic` queue: succeeded jobs older than
   `UF_RETENTION_JOB_DAYS` (7), and failed, cancelled and aborted jobs older than
   `UF_RETENTION_FAILED_JOB_DAYS` (30).
3. **Dry run is a switch.** `UF_RETENTION_ENABLED=false` makes the sweep count and log without deleting,
   so a new installation can watch one run before the first real one.
4. **The storage contract grows by two reads**: `list_prefixes(prefix)` (the immediate children, S3
   `Delimiter="/"`) and `list_objects(prefix)` (keys with size and last-modified time), on both backends.
5. **Cost.** One run a day on the `periodic` queue: a handful of table scans on indexed timestamps, one
   bucket listing per tenant, per project and per published project (a few hundred LIST calls on a
   platform with a hundred projects), deletes in batches of 1000. Nothing on the request path.

## Options considered

### Option A: one sweep with grace periods and a dry-run switch (chosen)

Pros: every target in one place with one log line, grace periods protect work in progress, the bucket
walk closes the ADR-0012 gap without a new table. Cons: the bucket walk grows with the number of projects
(one LIST per project per day); a retired version's media are gone after 30 days.

### Option B: reference counting on write

Keep a table of every storage key with its owner row and delete at write time. Pros: no listing. Cons: a
new table on every upload and publish, a migration over existing objects, and it still misses the
objects written by a failed job; a week of work for the same result.

### Option C: keep everything until the project is deleted

Pros: nothing to decide. Cons: dead uploads and retired versions grow without bound; the plan's retention
promise (§10.3) would be false.

## Trade-off analysis

| Axis | A sweep | B counting | C nothing |
|---|---|---|---|
| New code | one module, two storage reads (M) | a table, a migration, hooks on every write (L) | 0 |
| Finds objects written by a failed job | yes | no | no |
| Daily cost | LIST per project | 0 | 0 |
| Risk of deleting live data | bounded by the grace periods and the live-publication set | low | none |

## Consequences

Easier: an installation's bucket and tables stop growing with abandoned work; the ADR-0012 known gap is
closed; the job table stays small.

Harder: two rules to hold on every review: a new kind of stored object needs a row that the sweep can find
it by (or a target here), and a new publication status must be listed as live or retired in
`housekeeping.service`. Operations: the first run on an installation with history deletes a lot; run it
with `UF_RETENTION_ENABLED=false` once and read the counts (runbook).

Revisit: per-tenant retention policies (plan §10.3, the Settings screen) once Phase 5 brings buyer data;
a minimum interval or a sample of projects per run if the LIST count ever matters.

**Out of scope here:** leads, drafts, attempts, soft-deleted media (Phase 5), renovation boards
(ADR-0020 E8), per-tenant settings, backups (plan §16).

## Action items

- [x] A1 `storage/service.py`: `list_prefixes`, `list_objects` and `ObjectInfo.modified` on `LocalStorage`
      and `S3Storage`.
- [x] A2 `housekeeping/service.py` `sweep(now)` with the six targets and the dry-run switch;
      `jobs/tasks.py` `retention` calls it and defers `remove_old_jobs` twice; settings `retention_*`.
- [x] A3 `tests/test_retention.py` on the publishing world: a dead upload and a fresh one, an expired
      invitation and token, an old render crop, an orphaned prefix old and new, a retired asset next to a
      referenced one; the dry run counts and keeps everything.
- [x] A4 Docs: plan §12.3 row, ADR-0012 known gap note, `.env.example` and `compose.yaml` variables,
      runbook upgrade note, README status; backlog row 5 removed.
