from __future__ import annotations

import os

import pytest

os.environ.setdefault("UF_ENVIRONMENT", "test")
os.environ.setdefault("UF_LOG_JSON", "false")
# API tests run against the migrated test database when one is configured
if os.environ.get("UF_TEST_DATABASE_URL"):
    os.environ.setdefault("UF_DATABASE_URL", os.environ["UF_TEST_DATABASE_URL"])
if os.environ.get("UF_TEST_DATABASE_ADMIN_URL"):
    os.environ.setdefault("UF_DATABASE_ADMIN_URL", os.environ["UF_TEST_DATABASE_ADMIN_URL"])


@pytest.fixture
def settings():
    from unitforma.core.settings import get_settings

    get_settings.cache_clear()
    return get_settings()
