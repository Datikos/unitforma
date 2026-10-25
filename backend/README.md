# Unitforma backend

One Python package, four runtime roles (selected by the container command):

| Command | Role |
|---|---|
| `unitforma api` | FastAPI application (admin, portal, auth, internal APIs) |
| `unitforma worker --queues default,docs,mail,periodic` | Procrastinate worker |
| `unitforma scheduler` | Periodic job deferrer (single replica) |
| `unitforma migrate` | `alembic upgrade head` + Procrastinate schema, run as a one-shot container before `api`/`worker` |
| `unitforma bootstrap-admin <email>` | Flag an existing user (or Kratos identity) as platform administrator |
| `unitforma healthcheck live|ready` | Container health probes |

Local development without Docker:

```bash
uv sync --extra dev
export UF_DATABASE_URL=postgresql+asyncpg://app_rw:app_rw@localhost:5432/unitforma
export UF_DATABASE_ADMIN_URL=postgresql+psycopg://app_owner:app_owner@localhost:5432/unitforma
uv run unitforma migrate
uv run unitforma api
uv run pytest
```

API tests (including tenant isolation and the Phase 1 exit criteria) run against a migrated
PostgreSQL database when `UF_TEST_DATABASE_URL` / `UF_TEST_DATABASE_ADMIN_URL` are set; see
`.github/workflows/ci-backend.yml` for the role setup. After changing the API, regenerate the
frontend client: export the OpenAPI document (`python -c` snippet in the workflow) and run
`npm run api:generate` in `frontend/`.

Architecture, module boundaries and conventions: `docs/architecture/plan-v0.1.md` (§12).
