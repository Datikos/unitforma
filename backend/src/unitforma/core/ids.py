"""Time-ordered UUIDs (version 7) for all primary keys."""

from __future__ import annotations

import uuid

try:  # uuid_utils is a fast Rust implementation
    import uuid_utils

    def new_id() -> uuid.UUID:
        return uuid.UUID(str(uuid_utils.uuid7()))

except ImportError:  # pragma: no cover - fallback for minimal environments

    def new_id() -> uuid.UUID:
        return uuid.uuid4()
