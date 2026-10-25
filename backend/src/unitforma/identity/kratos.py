"""Thin client for the Ory Kratos public and admin APIs used by the application.

Only the calls the architecture relies on are wrapped here (plan §8). The admin API is
reachable solely on the internal Docker network.
"""

from __future__ import annotations

from typing import Any

import httpx

from unitforma.core.settings import Settings, get_settings


class KratosError(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"kratos responded {status}")
        self.status = status
        self.body = body


class KratosClient:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        s = settings or get_settings()
        self.public_url = s.kratos_public_url.rstrip("/")
        self.admin_url = s.kratos_admin_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- health -------------------------------------------------------------
    async def admin_ready(self) -> bool:
        try:
            r = await self._client.get(f"{self.admin_url}/admin/health/ready")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    # --- sessions -----------------------------------------------------------
    async def whoami_from_cookie(self, cookie_header: str) -> dict[str, Any] | None:
        """Validate a staff browser session by forwarding the Kratos cookie."""
        r = await self._client.get(
            f"{self.public_url}/sessions/whoami", headers={"Cookie": cookie_header}
        )
        if r.status_code == 401:
            return None
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        return r.json()

    async def whoami_from_token(self, session_token: str) -> dict[str, Any] | None:
        r = await self._client.get(
            f"{self.public_url}/sessions/whoami", headers={"X-Session-Token": session_token}
        )
        if r.status_code == 401:
            return None
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        return r.json()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        r = await self._client.get(f"{self.admin_url}/admin/sessions/{session_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        return r.json()

    async def revoke_session(self, session_id: str) -> None:
        r = await self._client.delete(f"{self.admin_url}/admin/sessions/{session_id}")
        if r.status_code not in (204, 404):
            raise KratosError(r.status_code, r.text)

    async def revoke_all_sessions(self, identity_id: str) -> None:
        r = await self._client.delete(f"{self.admin_url}/admin/identities/{identity_id}/sessions")
        if r.status_code not in (204, 404):
            raise KratosError(r.status_code, r.text)

    # --- identities ---------------------------------------------------------
    async def find_identity_by_email(self, email: str) -> dict[str, Any] | None:
        """Existence check used by the buyer BFF (plan §8.3, PoC V1)."""
        r = await self._client.get(
            f"{self.admin_url}/admin/identities", params={"credentials_identifier": email}
        )
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        items = r.json()
        return items[0] if items else None

    # --- native (API) flows, driven server-side for buyers -----------------
    async def create_native_flow(self, kind: str) -> dict[str, Any]:
        assert kind in ("login", "registration", "settings", "verification")
        r = await self._client.get(f"{self.public_url}/self-service/{kind}/api")
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        return r.json()

    async def submit_native_flow(
        self, kind: str, flow_id: str, body: dict[str, Any], session_token: str | None = None
    ) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if session_token:
            headers["X-Session-Token"] = session_token
        return await self._client.post(
            f"{self.public_url}/self-service/{kind}",
            params={"flow": flow_id},
            json=body,
            headers=headers,
        )

    async def logout_native(self, session_token: str) -> None:
        r = await self._client.request(
            "DELETE",
            f"{self.public_url}/self-service/logout/api",
            json={"session_token": session_token},
        )
        if r.status_code not in (204, 401):
            raise KratosError(r.status_code, r.text)

    # --- courier ------------------------------------------------------------
    async def abandoned_messages(self) -> list[dict[str, Any]]:
        r = await self._client.get(
            f"{self.admin_url}/admin/courier/messages", params={"status": "abandoned"}
        )
        if r.status_code != 200:
            raise KratosError(r.status_code, r.text)
        return r.json()
