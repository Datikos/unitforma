"""Who is calling: staff principal resolved from a Kratos browser session."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class StaffPrincipal:
    user_id: uuid.UUID
    kratos_identity_id: uuid.UUID
    kratos_session_id: str
    email: str
    email_verified: bool
    is_platform_admin: bool
    aal: str  # aal1 | aal2
