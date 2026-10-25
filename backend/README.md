# Unitforma backend

One Python package, four runtime roles (selected by the container command):

| Command | Role |
|---|---|
| `unitforma api` | FastAPI application (admin, portal, auth, internal APIs) |
| `unitforma worker --queues default,docs,mail,periodic` | Procrastinate worker |
| `unitforma scheduler` | Periodic job deferrer (single replica) |
| `unitforma migrate` | `alembic upgrade head`, run as a one-shot container before `api`/`worker` |
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

Architecture, module boundaries and conventions: `docs/architecture/plan-v0.1.md` (§12).
