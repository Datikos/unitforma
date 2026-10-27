# ADR-0012: Archiving a project, deleting a document or an empty building, and the tenant admin's permanent project delete

- **Status:** accepted (2026-10-25; implemented 2026-10-25; the S3 branch of `delete_prefix` verified on Garage 2026-10-26, see A1)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §3.4 (roles), §4.4 (object storage keys), §5.1 ("soft delete only where history matters"), §5.3 (`units`: permanent identity), §12.3 (background jobs)

## Context

What `main` does today (commit 3e2dde3):

- There is no way to remove a project, a building or a document from the product. The only deletions are
  `DELETE /media/{id}` (`sales/media.py`, removes the row and the object) and `POST /units/{id}/remove`
  (marks the unit `removed`, keeps the row). `projects.status` accepts `archived` through
  `PATCH /projects/{id}` (`api/schemas.py` `ProjectUpdate`), but no screen offers it, the projects list
  shows archived projects like any other, and nothing stops archiving a project whose portal is live.
- The owner asked on 2026-10-25 how to delete a document, a project or a building after a permit import
  (ADR-0007) created a test project with 16 drawings on the dev stack. The honest answer was "SQL inside
  the container, and the files stay in the volume".
- Foreign keys (`tenants/models.py`): everything tenant-owned cascades from `projects.id`
  (buildings, floors, documents, units, geometry models, sales rows, media, import batches, publications,
  regulatory imports, membership access). `units.building_id` and `units.floor_id` are `RESTRICT`, so a
  building with a unit row cannot be deleted at database level. `document_revisions`, `sheets`,
  `sheet_floors`, `mapping_proposals` cascade from a document; `unit_boundaries.sheet_id` cascades from a
  sheet, so deleting a mapped document silently deletes the units' outlines. `geometry_models.building_id`
  and `documents.building_id` are `SET NULL`: a deleted building would leave its IFC model looking like a
  site model. `portal_domains.project_id` has no foreign key. `audit_log` has no foreign keys and survives
  every delete. PostgreSQL runs referential actions outside row-level security, so cascades work under
  `tenant_session`.
- Storage keys (`storage/service.py` `object_key`) are `t/{tenant}/p/{project}/...`: a document's files
  (`documents/{document_id}/r{n}-{id}/file`, page rasters and extracts next to them), geometry under
  `geometry/`, publications under `publications/`. `Storage` has `delete(key)` for one object only;
  `S3Storage` has no prefix delete.
- Plan §5.1 already states the rule: "Soft delete only where history matters (`units.lifecycle_status`),
  hard delete elsewhere with audit rows." AGENTS.md rule 3 says `units` rows are never deleted; it was
  written for the life of a project and does not say what happens when the whole project goes.
- Jobs are Procrastinate tasks (`jobs/tasks.py`) deferred from the API with
  `jobs.configure_task(...).defer_async(...)`; the deferral uses its own connection and is not part of the
  request transaction (see `admin_documents.py` `complete_upload`, which tolerates an enqueue failure).

## Decision

1. **Archive is the normal way to retire a project; it changes nothing but `projects.status`.**
   `PATCH /projects/{id}` with `status: "archived"` was refused with 409 `project-published` while a
   publication with `status = published` existed. **Amended 2026-10-27:** it retires the live
   publication in the same transaction instead (`publishing.unpublish`, audited as `unpublish`, portal
   cache invalidated), and when a publication exists the caller also needs publication `publish`
   (tenant admin and project manager both have it). Reason: since ADR-0029 the solver publishes a
   project early, so every archive and delete of a test project met the refusal on 2026-10-27; archiving
   means taking the project off the market, and the unpublish is part of that intent. Reactivating does
   not publish again. Archived projects keep every row and file, stay readable, and the projects list
   hides them behind a "Show archived" toggle. `status: "active"` reactivates. Role: project `write`
   (tenant admin, project manager). The problem type `project-published` is gone.
2. **`DELETE /documents/{document_id}` removes a document, its revisions, sheets and files.** Role:
   documents `write`. Rows go by cascade; the storage prefix `t/{t}/p/{p}/documents/{document_id}/` goes
   by the job of Decision 5. When any `unit_boundaries` row lies on one of its sheets the call is refused
   with 409 `document-mapped` and `extra.units = n`; the same call with `?detach_units=true` proceeds, the
   outlines are deleted with the sheets, the units keep their identity and every other row, the audit row
   lists the detached unit ids, and a massing rebuild is queued (ADR-0011).
3. **`DELETE /buildings/{building_id}` removes an empty building.** Role: project `write`. Refused with
   409 `building-has-units` and `extra.units = n` while any `units` row, in any lifecycle state, points to
   it. Otherwise: floors go by cascade; the building's `geometry_models` rows and their GLB objects are
   deleted explicitly (the `SET NULL` would turn them into site models); documents filed under it become
   project-level; sheets whose `floor_id` or `suggested_floor_id` was one of the building's floors get both
   cleared and `assignment_status = unassigned` (the `SET NULL` alone would leave the status stale and the
   suggestion dangling); IFC space links cascade.
4. **`DELETE /projects/{project_id}?confirm={slug}` is the tenant admin's permanent delete.** Role:
   project `manage` (tenant admin only; project managers get 403). Refused with 400 `confirm-mismatch`
   when `confirm` is not the project's slug; that check runs first, so a wrong slug never touches the
   portal. **Amended 2026-10-27:** a `published` publication no longer refuses the call (it was 409
   `project-published`); it is retired first, audited as `unpublish`, and the audit row survives the
   delete. The typed slug and the tenant admin role are the guard. On success the project row is deleted and the cascades remove everything under it,
   including `units` rows: the permanence rule of plan §5.3 holds for the life of a project, and this call
   ends the project. Because `units.building_id` and `units.floor_id` are `RESTRICT`, the service deletes
   the project's `units` rows explicitly before the project row, so the nested cascade from `buildings`
   never meets a unit. Project-scoped `portal_domains` rows are set to `status = removed`. One audit row
   (`entity_type = project`, action `delete`, `before` = slug, name and counts of buildings, units,
   documents) is written before the delete and survives it. The prefix `t/{t}/p/{p}/` goes by the job of
   Decision 5.
5. **Storage prefixes are deleted by a job, guarded by the database.** `Storage.delete_prefix(prefix)` is
   added to the protocol: `LocalStorage` removes the directory, `S3Storage` pages `list_objects_v2` and
   calls `delete_objects` in batches of at most 1000 keys. Task `storage.delete_prefix` (queue `default`,
   up to 5 attempts, 30 s apart) takes `tenant_id`, `prefix` and a guard `(table, id)`; it refuses to run,
   and retries later, while the guarded row still exists, so a deferral that lands before the request
   transaction commits, or a request that rolls back after deferring, never deletes files of a living
   project or document. The job refuses a prefix that does not start with `t/{tenant_id}/p/` for the
   tenant it was given, and `LocalStorage.delete_prefix` refuses the storage root itself, so a caller's bug
   cannot reach another tenant's files. An enqueue failure is logged and tolerated: the rows are gone, the orphaned prefix
   waits for the retention sweep (plan §10.3, Phase 5).
6. **Every delete is a typed confirmation in the admin app.** Documents: a confirm dialog; on
   `document-mapped` a second dialog states the unit count and retries with `detach_units`. Buildings: a
   confirm dialog; `building-has-units` shows as the page error. Project: a danger-zone card on the
   overview with a prompt that must equal the slug; after success the app navigates to the projects list.
   The Archive and Reactivate buttons sit in the overview header. Each screen's guide entry names the
   action and what it refuses.
7. **AGENTS.md rule 3 and plan §5.1/§5.3 gain one sentence:** units are never deleted or re-keyed while their
   project exists; permanent project deletion (ADR-0012) removes the project's identity space as a whole.

## Options considered

### Option 1: archive project, delete document with its files, delete building only when empty

Pros: no row of a living project is ever lost; matches plan §5.1 and §5.3. Cons: a test project imported by
mistake stays forever; the owner has to clean the dev stack with SQL, which leaves files behind.

### Option 2: Option 1 plus a tenant admin's permanent project delete with typed confirmation (chosen)

Pros: the one escape hatch the owner actually needs, behind the strongest role, a typed slug, a live-portal
check and an audit row. Cons: the first place the product hard-deletes tenant data; needs the guarded
storage job and a sentence of exception in the unit-identity rule.

### Option 3: soft delete everywhere (`deleted_at` on projects, buildings, documents)

Pros: everything restorable. Cons: every list query, RLS policy, unique constraint (`uq_project_slug`,
`uq_building_code`) and publication snapshot must learn the flag; files are never reclaimed; a week of work
for a property the owner did not ask for.

### Option 4: do nothing (SQL in the container)

Rejected: leaves files in the volume, bypasses audit, and is not available to a tenant admin.

## Trade-off analysis

| | Option 1 | Option 2 (chosen) | Option 3 |
|---|---|---|---|
| Removes a mistaken project | no | yes, tenant admin, typed slug | yes, restorable |
| Reclaims storage | documents only | documents and projects | never |
| Rows touched | documents, buildings | plus the project cascade | every tenant table |
| Code surface | 2 endpoints, 2 buttons | 3 endpoints, 1 job, 4 buttons | queries, RLS, constraints, snapshots |
| Size | M | M plus a day | L |

## Consequences

Easier: a wrong upload, an empty building or a test project is removed from the screen where it lives,
with the files, and the audit log says who did it.

Harder: two rules to hold on every review. First, any new table that references a document's sheets or a
building must choose its `ondelete` deliberately, because Decisions 2 and 3 rely on the cascades being
complete. Second, any new storage key must stay under `t/{t}/p/{p}/`, or the prefix job will not find it.
A job queued for a project or document that is then deleted (`documents.ingest_revision`,
`regulatory.import_attachments`) fails on its `scalar_one()` lookup, retries once or twice and ends
failed without creating rows. Operations: the `default` queue now carries deletes; a worker outage leaves prefixes orphaned until the
job runs (at most 5 attempts over about 2 minutes, then it fails and the prefix waits for retention).

Known gap: published assets are copied under `pub/{tenant}/{project}/…` (`publishing/snapshot.py`
`Assets.prefix`), outside the project prefix, so the prefix job does not reach them. Closed by
ADR-0021 (2026-10-26): the daily sweep lists the project, document and `pub/` prefixes against the rows
and removes the assets of retired versions. Since 2026-10-27 (A7) a published project can be deleted:
its publication is retired and then cascades away with the project, so `pub/{t}/{p}/` is left to the
sweep's orphan walk (`housekeeping._orphan_prefixes`, no publication rows → prefix removed after
`retention_orphan_days`), not to the retired-version rule.
When Phase 5 adds leads, `DELETE /projects` must decide what happens to a lead of a deleted project (plan
§10.3 says anonymise, not delete).

**Out of scope here:** deleting a tenant; deleting one revision or one floor; soft delete; recovering a
deleted project from backup (runbook, plan §15); hiding archived projects from the portal (a published
project cannot be archived, so the portal never shows one).

## Action items

### Phase A: backend

- [x] A1 `storage/service.py`: `delete_prefix` on the protocol, `LocalStorage` (rmtree) and `S3Storage`
      (paginated `list_objects_v2`, `delete_objects` ≤ 1000); unit test on the local backend.
      *Found while implementing:* the S3 branch is written against the boto3 API only; tests and the
      dev stack run the local backend, and Garage was stopped when this was finished, so it is
      **unverified** against a real bucket (AGENTS.md rule 8).
      *Verified 2026-10-26 on Garage v2.5.0:* 1005 keys under a throwaway prefix removed in 0.2 s across two
      batches, 0 left; `delete_prefix("/")` refused (ADR-0005 PoC V6 note).
- [x] A2 `jobs/tasks.py` `storage.delete_prefix` with the row guard and retry; `storage/jobs.py` holds the
      body; test that the guard refuses while the row exists.
- [x] A3 `projects/service.py`: `archive` check in `update_project`, `delete_building`, `delete_project`
      (counts, audit, domains, enqueue); `api/admin_projects.py` routes; `ProblemError` types
      `project-published` (removed 2026-10-27, A7), `building-has-units`, `confirm-mismatch`.
- [x] A4 `documents/service.py` `delete_document` (mapped-units check, detach, enqueue, massing rebuild);
      `api/admin_documents.py` route.
- [x] A5 `tests/test_delete_and_archive.py`: role matrix, archive refused while published, document delete
      removes files and sheets, `document-mapped` then `detach_units`, building refused with units then
      deleted when empty, project delete with wrong slug, as project manager, while published, and the full
      cascade with the prefix gone and the audit row kept.
      *Found while implementing:* the project-delete test world has two approved units, so the
      explicit `units` delete before the project row is exercised, not assumed; a sheet assigned by
      `PATCH /sheets/{id}/floor` has `assignment_status = confirmed`, not `assigned`.
- [x] A6 Regenerate `frontend/projects/libs/api-client/src/generated/openapi.json` and the typings.
- [x] A7 (2026-10-27) Archive and delete take a published portal offline: `admin_projects._take_offline`
      (publication `publish` right, `publishing.unpublish`), `projects.check_confirm` before it;
      `test_archive_takes_the_portal_offline_and_a_wrong_slug_does_not` and the unpublish audit row in
      `test_project_delete_cascades_units_and_keeps_audit`; project page texts, guide, README, plan §5.3.

### Phase B: admin app

- [x] B1 `api-client.ts`: `deleteDocument`, `deleteBuilding`, `deleteProject`.
- [x] B2 `projects.page.ts`: hide archived by default, "Show archived" toggle, archived count.
- [x] B3 `project-detail.page.ts`: Archive and Reactivate in the header; Delete building on each building
      card; danger-zone card with the typed slug prompt; navigate to the list after the delete.
- [x] B4 `documents.page.ts`: Delete on the card with the two-step dialog.
- [x] B5 `guide-content.ts`: entries for projects, project-overview and documents.

### Phase C: docs

- [x] C1 README status line, AGENTS.md rule 3, plan §5.1 and §5.3 sentences, plan §12.3 jobs table row;
      this ADR ticked. The plan has no endpoint table.
