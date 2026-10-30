"""Worker liveness for the container health check (BACKLOG 8, plan §17).

Procrastinate's worker writes a heartbeat row every 10 s (``update_heartbeat_interval``). The
same process also touches a file after each successful heartbeat, so the container's health
probe proves that *this* worker's loop runs and reaches PostgreSQL, without knowing its worker
id and without a database round trip per probe. ``unitforma healthcheck worker`` reads the
file's age.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

HEARTBEAT_FILE = Path(os.environ.get("UF_WORKER_HEARTBEAT_FILE", "/tmp/unitforma-worker.heartbeat"))  # noqa: S108 - per container
MAX_AGE_S = 45.0  # four missed heartbeats of 10 s plus a margin


def touch(path: Path = HEARTBEAT_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(time.time()), encoding="ascii")
    except OSError:  # a read-only /tmp must not stop the worker; the probe then reports it
        pass


def install(app: Any, path: Path = HEARTBEAT_FILE) -> None:
    """Wrap the job manager's ``register_worker`` and ``update_heartbeat`` so a successful call
    also touches ``path``. A failed database write raises before the touch, so the file ages."""
    jm = app.job_manager
    register, update = jm.register_worker, jm.update_heartbeat

    async def register_worker() -> int:
        worker_id = await register()
        touch(path)
        return worker_id

    async def update_heartbeat(worker_id: int) -> None:
        await update(worker_id)
        touch(path)

    jm.register_worker = register_worker
    jm.update_heartbeat = update_heartbeat


def is_alive(path: Path = HEARTBEAT_FILE, max_age_s: float = MAX_AGE_S) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) <= max_age_s
    except OSError:
        return False
