# ADR-0011: The 3D massing follows the mapping, draft outlines included

- **Status:** accepted (2026-10-25; implemented 2026-10-25)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §7.3 (MVP 3D), §11.3 massing, §13.2 "3D massing" row, §4.3 transactional enqueue

## Context

The owner's question of 2026-10-25 ("after the PDF upload, what generates floors and 3D") exposed
that the massing GLB is rebuilt only on sheet approval or by the Regenerate button, so a reviewer
drawing outlines sees no 3D until approval. What `main` has:

- `geometry.service.collect` already includes every non-removed unit with a current, calibrated
  boundary, drafts included, and writes `lifecycle_status` and `verification_status` into each
  unit node's `extras`; the admin viewer paints all units alike.
- The portal never sees drafts: `publishing/snapshot._massing` builds its own GLB from listed
  units at publish time.
- `geometry.build_massing` is a Procrastinate task on the `geometry` queue; the approval endpoint
  enqueues it in the request handler (Procrastinate defers through its own connector, not the
  request's SQLAlchemy session, so the defer is its own transaction). Procrastinate 3.10 supports `queueing_lock`: a
  second job with the same lock while one is still waiting raises `AlreadyEnqueued`.
- A massing build for a pilot-sized project takes well under a second; outlines are edited many
  times per minute while mapping.

## Decision

1. **Every change to an outline queues a rebuild**: boundary created, moved or redrawn, proposal
   item accepted (single or all), unit relabelled, removed, merged or split, sheet recalibrated,
   sheet approved (as before). One helper, `geometry.service.queue_massing(tenant_id,
   project_id)`, used by every endpoint.
2. **One waiting job per project.** The job is deferred with `queueing_lock = "massing:<project>"`;
   while a job waits, further edits do nothing (`AlreadyEnqueued` is swallowed), so a burst of
   edits costs one build after the burst, plus at most one running build. The request never fails
   because the queue is down; a warning is logged.
3. **Drafts are visible and look different.** The admin viewer paints units whose
   `lifecycle_status` is `draft` translucent (opacity 0.55) and names the status in the hover
   label; the massing page shows "N verified, M draft" and a legend. The portal GLB is unchanged
   (listed units only), the disclaimer stays.
4. **No model change**: the same `geometry_models` row kind `massing_generated` is replaced;
   `stats` gains `units_draft`.

## Options considered

- **O1 (chosen): queue on every edit with a queueing lock.** Pros: the model is never more than
  one burst behind, no timer, no new state. Cons: one background job per burst of edits.
- **O2: timer-based debounce in the API (asyncio task per project).** Rejected: state in a
  process that may have several replicas; lost on restart.
- **O3: build on demand only (Regenerate button).** Status quo; the owner wants the model to
  appear while mapping.
- **O4: separate draft model kind.** Rejected: the admin model already contains drafts; the
  portal builds its own GLB, so one model with styled drafts is enough.

## Consequences

**Easier.** The 3D view is a live mirror of the mapping; a wrong outline shows as a wrong solid
within seconds; drafts are told from verified units at a glance.

**Harder.** Reviewers must know that translucent means draft, and that the admin model is not
what buyers see. Worker load grows with mapping activity (one build per burst, sub-second).

**Operations.** The `geometry` queue on `worker-heavy` gets more jobs; the queueing lock keeps the
backlog at one per project.
A request that fails after the defer still costs one rebuild; the build is idempotent (it reads
the current outlines), so that rebuild is harmless.

**Revisit.** If a project with thousands of units makes builds slow, add a minimum interval per
project in the task itself.

**Out of scope here:** incremental GLB updates, draft styling in the portal (never shown), live
push to the admin page (it polls after Regenerate; a manual reload shows the new model).

## Action items

- [x] 1 `geometry/service.queue_massing` with the queueing lock; approval and every outline
      change in `api/admin_mapping.py` and the calibration endpoint in `api/admin_documents.py`
      call it; `stats.units_draft` in `collect`.
- [x] 2 `libs/viewer-3d`: translucent drafts, `lifecycle_status` in `MassingUnitInfo` and the
      hover label; admin massing page counts and legend.
- [x] 3 Tests: GLB extras carry the lifecycle status; `queue_massing` swallows `AlreadyEnqueued`
      and queue failures.
- [x] 4 Docs: plan §13.2 row and notes, README status.
