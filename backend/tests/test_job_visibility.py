"""ADR-0038: a job can start before the request that queued it commits. The jobs that act on a
row the request created wait for it (retry 2 s later) instead of skipping or failing."""

from __future__ import annotations

import uuid

import pytest

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import world  # noqa: F401 - module-scoped fixture, rebuilt here
from unitforma.jobs.visibility import WAIT_FOR_COMMIT, NotYetCommitted


def test_the_jobs_that_act_on_request_rows_wait_for_the_commit():
    from unitforma.jobs import tasks

    for task in (tasks.ingest_revision, tasks.import_attachments, tasks.ingest_ifc):
        assert task.retry_strategy is WAIT_FOR_COMMIT, task.name
    assert WAIT_FOR_COMMIT.max_attempts == 6 and WAIT_FOR_COMMIT.wait == 2


@phase4.pytestmark
def test_ingesting_an_uncommitted_revision_waits_and_leaves_it_alone(client, world):  # noqa: F811
    """A revision the job finds still `pending` is what a not-yet-committed `complete` looks
    like: the job raises NotYetCommitted (retried by its strategy) and changes nothing."""
    from unitforma.documents.jobs import process_revision

    base, pid, adm = world["base"], world["project"]["id"], world["adm"]
    doc = client.post(
        f"{base}/projects/{pid}/documents", headers=adm, json={"kind": "other", "title": "Race"}
    ).json()
    intent = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=adm,
        json={"file_name": "r.pdf", "content_type": "application/pdf", "byte_size": 10},
    ).json()
    rev_id = intent["revision"]["id"]
    assert intent["revision"]["processing_status"] == "pending"
    with pytest.raises(NotYetCommitted):
        client.portal.call(process_revision, uuid.UUID(world["tenant"]["id"]), uuid.UUID(rev_id))
    revs = client.get(f"{base}/documents/{doc['id']}/revisions", headers=adm).json()
    assert revs[0]["processing_status"] == "pending"
    # a revision that does not exist yet waits the same way
    with pytest.raises(NotYetCommitted):
        client.portal.call(process_revision, uuid.UUID(world["tenant"]["id"]), uuid.uuid4())
