"""The API process must be able to enqueue jobs (regression: the Procrastinate app was never
opened in the API, so every upload stayed unprocessed with "could not enqueue")."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not (os.environ.get("UF_TEST_DATABASE_ADMIN_URL") and os.environ.get("UF_TEST_DATABASE_URL")),
    reason="needs the PostgreSQL test database",
)


def test_api_lifespan_opens_job_queue():
    from unitforma.jobs.app import app as jobs
    from unitforma.main import create_app

    with TestClient(create_app()) as client:
        job_id = client.portal.call(
            lambda: jobs.configure_task(name="housekeeping.ping", queue="default").defer_async(
                message="enqueue-check"
            )
        )
        assert isinstance(job_id, int) and job_id > 0
