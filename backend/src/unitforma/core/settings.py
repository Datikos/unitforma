"""Application settings.

Values come from environment variables prefixed with ``UF_``. Any setting can also be
provided through a file (Docker secrets) by setting ``UF_<NAME>_FILE`` to the file path;
the file content is read and stripped. This keeps secrets out of ``.env`` and images.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRETS_DIR = Path(os.environ.get("UF_SECRETS_DIR", "/run/secrets"))


def _load_file_secrets(prefix: str = "UF_") -> None:
    """Resolve ``UF_X_FILE`` variables into ``UF_X`` before settings are parsed."""
    for key, path in list(os.environ.items()):
        if key.startswith(prefix) and key.endswith("_FILE"):
            target = key[: -len("_FILE")]
            if target not in os.environ and Path(path).is_file():
                os.environ[target] = Path(path).read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UF_", extra="ignore")

    environment: str = Field(default="development", description="development|test|production")
    log_level: str = "INFO"
    log_json: bool = True

    # Public hosts (used for routing decisions and cookie policy)
    platform_domain: str = "unitforma.com"
    admin_host: str = "app.unitforma.com"
    portals_cname_target: str = "portals.unitforma.com"

    # Databases
    database_url: str = "postgresql+asyncpg://app_rw:app_rw@localhost:5432/unitforma"
    database_password: str | None = Field(
        default=None, description="Injected into database_url if set"
    )
    database_admin_url: str = "postgresql+psycopg://app_owner:app_owner@localhost:5432/unitforma"
    database_admin_password: str | None = None
    database_pool_size: int = 10

    # Kratos (internal network URLs)
    kratos_public_url: str = "http://kratos:4433"
    kratos_admin_url: str = "http://kratos:4434"

    # Object storage (S3 API)
    s3_endpoint_url: str = "http://storage:3900"
    s3_region: str = "garage"
    s3_bucket: str = "unitforma"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_public_url: str | None = Field(
        default=None, description="Browser-facing S3 endpoint for presigned URLs"
    )
    storage_backend: str = Field(default="s3", description="s3 | local")
    storage_local_root: str = "/tmp/unitforma-storage"  # noqa: S108 - dev/test only
    storage_public_base: str = ""

    # Internal endpoint protection (Caddy on-demand TLS ask endpoint)
    internal_ask_token: str = ""

    # Scheme of public portal URLs (dev Caddy serves https with its local CA as well)
    public_scheme: str = "https"
    # Seconds a portal host → publication lookup is cached per process (unpublish latency)
    portal_cache_seconds: float = 5.0
    # The portal embeds the OpenStreetMap map around a project's position (ADR-0016 Decision 5).
    # False shows the address and a link to OpenStreetMap only: the switch for the day the OSMF
    # tile policy's "access may be withdrawn" applies (ADR-0016 E4), without a deploy.
    portal_map_embed: bool = True
    # retention sweep (ADR-0021); false counts and logs without deleting
    retention_enabled: bool = True
    retention_pending_upload_hours: int = 24
    retention_invitation_days: int = 30
    retention_token_days: int = 90
    retention_render_input_days: int = 30
    retention_orphan_days: int = 7
    retention_retired_asset_days: int = 30
    retention_job_days: int = 7
    retention_failed_job_days: int = 30

    # Buyer sessions
    app_session_key: str = Field(default="dev-only-change-me", min_length=16)
    app_session_ttl_days: int = 30

    # Regulatory sources (ADR-0007): project bootstrap from a tas.ge building permit
    regulatory_tasge_enabled: bool = True

    # MCP server for staff assistants at /mcp on the admin host (ADR-0015); false leaves /mcp 404
    mcp_enabled: bool = True

    # AI-generated 3D plan renders (ADR-0017 Decision 4). ``none`` hides the feature; the key is a
    # file secret (UF_AI_IMAGE_API_KEY_FILE=/run/secrets/ai_image_api_key).
    ai_image_provider: str = Field(default="none", description="none | gemini")
    ai_image_api_key: str = ""
    ai_image_model: str = "gemini-nano-banana-2.1"
    ai_image_endpoint: str = "https://generativelanguage.googleapis.com/v1beta/interactions"
    ai_image_daily_limit: int = Field(
        default=40, description="Render requests per tenant per UTC day"
    )
    # Shown next to the button, never used for billing: $0.0336 per 1K image on the Gemini pricing
    # page dated 2026-10-22 (plan §21). Null hides the figure.
    ai_image_cost_per_image_usd: float | None = 0.0336

    @model_validator(mode="after")
    def _inject_passwords(self) -> Settings:
        """Allow passwords to arrive separately (Docker secrets) and be merged into the URLs."""
        if self.database_password:
            self.database_url = _with_password(self.database_url, self.database_password)
        if self.database_admin_password:
            self.database_admin_url = _with_password(
                self.database_admin_url, self.database_admin_password
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def _with_password(url: str, password: str) -> str:
    parts = urlsplit(url)
    user = parts.username or ""
    hostport = parts.hostname or ""
    if parts.port:
        hostport += f":{parts.port}"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{hostport}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_file_secrets()
    return Settings()
