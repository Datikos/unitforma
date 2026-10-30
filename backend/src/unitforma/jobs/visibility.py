"""Jobs that wait for the row their request created (ADR-0038 Decision 2b).

Procrastinate defers through its own psycopg connection, so a job can start before the request
that queued it commits. A job acting on such a row raises :class:`NotYetCommitted` when the row is
missing or still in its state before the request's change; :data:`WAIT_FOR_COMMIT` retries it
2 s later, up to 6 attempts, then the job fails and the periodic sweeps recover it.
"""

from __future__ import annotations

import procrastinate


class NotYetCommitted(Exception):  # noqa: N818 - a state, not an error the caller made
    """The row this job was queued for is not visible yet; try again shortly."""


WAIT_FOR_COMMIT = procrastinate.RetryStrategy(max_attempts=6, wait=2)
