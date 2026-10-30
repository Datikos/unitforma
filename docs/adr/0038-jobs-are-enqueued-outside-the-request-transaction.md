# ADR-0038: Jobs are enqueued outside the request transaction; a job waits for the row it was queued for

- **Status:** accepted (2026-10-30; implemented 2026-10-30); amends ADR-0004 ("Jobs are enqueued in the same transaction as the business change")
- **Date:** 2026-10-30
- **Deciders:** David Sakhelashvili (platform owner); BACKLOG 11 asked to "decide whether to keep the pattern or enqueue through the request connection", and "finish 11" on 2026-10-30 left the pick to this ADR, which he can overrule
- **Plan reference:** §4.3 (task queue), §12.3 (background jobs), PoC V5, ADR-0004, ADR-0012 Decision 5, ADR-0016 Decision 8

## Context

ADR-0004 says jobs are enqueued "in the same transaction as the business change". The code never
did that:

- The API talks to PostgreSQL through SQLAlchemy over **asyncpg** (`core/db.py`). Procrastinate's
  async connector is a **psycopg 3** pool of its own (`jobs/app.py` `PsycopgConnector`), so
  `configure_task(...).defer_async(...)` inserts the job row in a separate transaction that commits
  at once, before the request's own transaction does.
- Two consequences follow, and the code already met them case by case. A job can start before the
  request commits and not see its row yet; a request can fail after deferring and leave a job for a
  change that never happened.
- What exists against them: `storage.delete_prefix` refuses to run while its guard row still exists
  and retries 5 times 30 s apart (ADR-0012 Decision 5); the massing, relink and floor re-suggestion
  jobs read the current state and are idempotent; `documents.requeue_stuck` re-queues a revision left
  `queued` for 15 minutes (ADR-0016 Decision 8); a permit refresh closes an import left `importing`
  for 20 minutes.
- What does not: `documents.ingest_revision` returns `skipped` when it sees the revision still
  `pending` (the request set `queued` but has not committed); `regulatory.import_attachments` and
  `geometry.ingest_ifc` raise `NoResultFound` on a row they cannot see yet, use their one immediate
  retry and fail. The work is then picked up only by the 15- or 20-minute sweeps.

## Decision

1. **Keep enqueueing through Procrastinate's own connection.** ADR-0004's sentence is amended: the
   deferral is not part of the request transaction, and every job is written for that.
2. **Every job obeys one of two rules.** (a) It reads the current state and is idempotent, so running
   early, twice or for a rolled-back change does no harm: massing builds, the IFC relink, floor
   re-suggestions, the setup solver, the periodic sweeps. (b) It acts on a row the request creates or
   moves into a state, and **waits for it**: when the row is missing, or still in the state before
   the request's change, it raises `jobs.visibility.NotYetCommitted`, and the task's retry strategy
   tries again 2 s later, up to 6 times (12 s). After that the job fails visibly and the existing
   sweep recovers it, as for a lost worker.
3. **The rule (b) jobs are `documents.ingest_revision`** (revision `pending` → wait),
   **`regulatory.import_attachments`** (import row missing → wait), **`geometry.ingest_ifc`**
   (revision missing → wait) and `storage.delete_prefix` (unchanged: its guard is the same rule, the
   other way round).
4. **A new job states its rule** in its docstring; the review checklist of ADR-0015 ("every new tool
   calls a service") gains "every new job is idempotent or waits for its row".

## Options considered

- **A (chosen): separate connection, jobs written for it.** Pros: no driver change, nothing new to
  run; the fixes are three small guards. Cons: a rule to hold on every new job; a job queued by a
  request that failed still runs once (and finds nothing to do).
- **B: enqueue through the request's connection.** Procrastinate's async connectors cannot borrow an
  asyncpg connection; this needs the API moved to SQLAlchemy over psycopg 3 and a custom connector
  bound to the session's connection, neither of which Procrastinate ships: the installed 3.10.0
  has contrib connectors for `aiopg`, `django`, `psycopg2` and `sqlalchemy`, and the SQLAlchemy one
  wraps a synchronous psycopg2 engine (checked in `procrastinate/contrib/` on 2026-10-30). Rejected:
  a driver change across every query for a race the guards close.
- **C: an outbox table written in the request, relayed to the queue by a periodic job.** Pros: truly
  transactional. Cons: a table, a relay, and seconds of latency on every upload; the sweeps already
  play the relay's part for the rare lost job.

## Consequences

**Easier.** An upload is processed within seconds even when the worker is faster than the commit;
the docs stop claiming a guarantee the code does not give.

**Harder.** One more rule per new job. A job that waits ties up a worker slot for up to 12 s in the
worst case (the commit normally lands within milliseconds).

**Revisit.** If the API ever moves to psycopg 3, Option B becomes cheap; measure how often
`NotYetCommitted` is raised (it is logged) before deciding.

**Out of scope here:** the rest of PoC V5. Graceful shutdown (`stop_grace_period: 5m`, ADR-0016
Decision 8), concurrency per worker (`--concurrency 4` and `1`) and periodic tasks (retention,
`documents.requeue_stuck`) have run on the dev stack since 2026-10-25; no measurement was written down,
so V5 stays open in ADR-0004 until a load test of Phase 7 records one.

## Action items

- [x] 1 `jobs/visibility.py` with `NotYetCommitted` and the retry strategy; `ingest_revision`,
      `import_attachments`, `ingest_ifc` use it; the three bodies raise it on a row they cannot see.
- [x] 2 Tests: the ingestion of a `pending` revision raises `NotYetCommitted` and leaves the row
      untouched; the strategy retries it and nothing else changes.
- [x] 3 Docs: ADR-0004 status amended; plan §4.3 table and PoC V5 line; BACKLOG row 11 removed.
