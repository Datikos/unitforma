"""BACKLOG 8 (plan §17): a worker container is healthy while its own Procrastinate heartbeat
reaches PostgreSQL; the probe reads a file the heartbeat touches, with no HTTP and no query."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from unitforma.jobs import health


class FakeJobManager:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.beats = 0

    async def register_worker(self) -> int:
        return 7

    async def update_heartbeat(self, worker_id: int) -> None:
        if self.fail:
            raise ConnectionError("database down")
        self.beats += 1


class FakeApp:
    def __init__(self, jm: FakeJobManager) -> None:
        self.job_manager = jm


def test_a_heartbeat_touches_the_file_and_the_probe_reads_its_age(tmp_path):
    path = tmp_path / "hb"
    app = FakeApp(FakeJobManager())
    health.install(app, path)
    assert not health.is_alive(path)  # nothing yet
    assert asyncio.run(app.job_manager.register_worker()) == 7
    assert health.is_alive(path)
    asyncio.run(app.job_manager.update_heartbeat(7))
    assert app.job_manager.beats == 1 and health.is_alive(path)
    old = time.time() - health.MAX_AGE_S - 5
    os.utime(path, (old, old))
    assert not health.is_alive(path)  # the loop stopped beating


def test_a_failed_database_heartbeat_does_not_touch_the_file(tmp_path):
    path = tmp_path / "hb"
    app = FakeApp(FakeJobManager(fail=True))
    health.install(app, path)
    with pytest.raises(ConnectionError):
        asyncio.run(app.job_manager.update_heartbeat(7))
    assert not path.exists()


def test_the_probe_command_answers_for_workers(tmp_path, monkeypatch):
    from unitforma import healthcheck

    path = tmp_path / "hb"
    monkeypatch.setattr(health, "HEARTBEAT_FILE", path)
    monkeypatch.setattr(health.is_alive, "__defaults__", (path, health.MAX_AGE_S))
    monkeypatch.setattr("sys.argv", ["healthcheck", "worker"])
    assert healthcheck.main() == 1
    health.touch(path)
    assert healthcheck.main() == 0
