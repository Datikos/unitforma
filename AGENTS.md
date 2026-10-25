# Instructions for AI coding assistants and contributors

Read `docs/architecture/plan-v0.1.md` before changing structure. Key rules:

1. **Module boundaries.** Backend code lives in `backend/src/unitforma/<module>/`; `core` never
   imports feature modules (enforced by import-linter). API routers only call module services.
2. **Tenant isolation is mandatory.** Every tenant-owned table has `tenant_id`, RLS policies from
   `backend/migrations/rls.py`, and queries run inside `tenant_session(...)`. Never bypass RLS to
   "make a test pass".
3. **Unit identity.** Never delete or re-key `units` rows while their project exists; use lineage
   events. The one exception is the tenant admin's permanent project delete (ADR-0012), which removes
   the whole project. Prices and areas are `numeric`, nullable means unknown — never default to 0.
4. **Migrations** are backward compatible with the previous release (expand/contract). Run
   `uv run python -m alembic revision --autogenerate` only after reviewing the generated SQL.
5. **Docker.** Each deployable module has its own Dockerfile; Compose files live in
   `deploy/compose`. Validate with `docker compose -f compose.yaml -f compose.prod.yaml --env-file .env.example config`.
6. **Secrets** are files under `deploy/compose/secrets/` (git-ignored) mounted at `/run/secrets`.
   Never commit real values, never put secrets in images or `.env`.
7. **Checks before a commit:** `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest`;
   `cd frontend && npx ng lint && npx ng test --watch=false && npx ng build admin && npx ng build portal`.
8. **Facts about third-party software** go in the plan with a source; mark anything unverified.
9. Do not add licence-incompatible dependencies to application images (no AGPL libraries such as
   PyMuPDF); AGPL is acceptable only for unmodified standalone services (Garage, Grafana).
10. Commit messages: imperative subject, body explaining why. Reference plan sections (e.g. "§8.3").
