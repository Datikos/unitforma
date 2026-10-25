# ADR-0004: Procrastinate (PostgreSQL) as the job queue; no broker container in MVP

- **Status:** accepted (pending PoC V5)
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
