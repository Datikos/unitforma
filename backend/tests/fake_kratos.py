"""In-memory stand-in for the Kratos client: cookie value → identity."""

from __future__ import annotations

import uuid
from typing import Any


class FakeKratos:
    def __init__(self) -> None:
        self.identities: dict[str, dict[str, Any]] = {}

    def add(self, name: str, email: str, *, verified: bool = True, aal: str = "aal1") -> str:
        identity_id = str(uuid.uuid4())
        self.identities[name] = {
            "id": f"sess-{name}",
            "active": True,
            "authenticator_assurance_level": aal,
            "identity": {
                "id": identity_id,
                "traits": {"email": email, "name": name},
                "verifiable_addresses": [{"value": email, "verified": verified, "via": "email"}],
            },
        }
        return identity_id

    async def whoami_from_cookie(self, cookie_header: str) -> dict[str, Any] | None:
        for part in cookie_header.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "ory_kratos_session":
                return self.identities.get(v)
        return None

    async def admin_ready(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def cookie(name: str) -> dict[str, str]:
    return {"Cookie": f"ory_kratos_session={name}"}
