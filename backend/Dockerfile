# syntax=docker/dockerfile:1.7
# One image, several roles. The container command selects the role:
#   api | worker --queues … | scheduler | migrate | healthcheck live|ready
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

FROM base AS builder
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Heavy worker: adds IfcOpenShell (LGPL-3.0, imported unmodified) for IFC ingestion (ADR-0006 C2).
# Kept out of the api/light-worker image: ~120 MB and a native geometry kernel.
FROM builder AS builder-ifc
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra ifc

FROM base AS runtime
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app src ./src
# Mount point of the dev `local_storage` volume. Docker copies this ownership into a named volume
# only when the volume is first created; the process runs as `app`, so root-owned would be unwritable.
RUN mkdir -p /data/storage && chown app:app /data/storage
USER app
EXPOSE 8000
ENV PYTHONPATH=/app/src
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-m", "unitforma.healthcheck", "live"]
ENTRYPOINT ["unitforma"]
CMD ["api"]

# Same image, same roles, plus the IFC extra: used by worker-heavy only.
FROM runtime AS runtime-ifc
COPY --from=builder-ifc /opt/venv /opt/venv
