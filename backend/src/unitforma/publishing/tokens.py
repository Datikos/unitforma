"""Signed preview tokens: HMAC, bound to one publication and one staff user, 1 h (plan §9.3)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

from unitforma.core.settings import get_settings

PREVIEW_TTL_SECONDS = 3600


def _key() -> bytes:
    # derived key: the app session secret is never used directly for a second purpose
    return hashlib.sha256(b"unitforma-preview:" + get_settings().app_session_key.encode()).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(publication_id: uuid.UUID, user_id: uuid.UUID, ttl: int = PREVIEW_TTL_SECONDS) -> str:
    body = _b64(
        json.dumps(
            {"p": str(publication_id), "u": str(user_id), "e": int(time.time()) + ttl},
            separators=(",", ":"),
        ).encode()
    )
    sig = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str | None) -> uuid.UUID | None:
    """Publication id of a valid, unexpired token; ``None`` otherwise."""
    if not token or token.count(".") != 1 or len(token) > 512:
        return None
    body, sig = token.split(".")
    expected = _b64(hmac.new(_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(body))
        if int(data["e"]) < time.time():
            return None
        return uuid.UUID(data["p"])
    except (ValueError, KeyError, TypeError):
        return None
