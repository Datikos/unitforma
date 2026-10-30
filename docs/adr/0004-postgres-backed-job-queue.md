# ADR-0004: Procrastinate (PostgreSQL) as the job queue; no broker container in MVP

- **Status:** accepted (pending the rest of PoC V5); the sentence "Jobs are enqueued in the same transaction as the business change" is superseded by ADR-0038 on 2026-10-30: the deferral uses Procrastinate's own connection, and every job is idempotent or waits for its row
- **Date:** 2026-10-25
- **Plan reference:** §4.3, §12.3

## Decision
Background jobs use Procrastinate with PostgreSQL as the broker. Jobs are enqueued in the same
transaction as the business change. Workers subscribe to queue sets (`worker-light`, `worker-heavy`).

## Alternatives considered
Celery + Valkey/RabbitMQ (mature, extra stateful container, no transactional enqueue); Dramatiq; arq
(maintenance mode).

## Consequences
One fewer stateful service and one backup; the `jobs` module isolates the queue API so a broker
switch is possible if throughput demands it.
