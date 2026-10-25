# ADR-0001: Modular Python monolith plus workers, one container per deployable module

- **Status:** accepted
- **Date:** 2026-10-25
- **Plan reference:** §3.1, §12

## Context
The brief requires every deployable module in its own container but explicitly does not require
microservices. The domain (tenants, documents, mapping, inventory, sales, publishing, leads) shares
one data model and one transaction boundary (e.g. approving a mapping also enqueues jobs).

## Decision
One Python package `unitforma` with enforced module boundaries (import-linter) produces one image
that runs as `api`, `worker-light`, `worker-heavy`, `scheduler` and the one-shot `db-migrate`.
Frontends are separate Angular applications with their own images. Infrastructure uses official
images in separate containers.

## Alternatives considered
Service per business feature (rejected: distributed transactions, N schemas, more ops for a small
team); single container for API and worker (rejected: no independent scaling/limits/restarts).

## Consequences
Deploys are per module but versioned together for the backend image; schema compatibility rules
(§17.6) apply across API and worker tags during a rolling update.
