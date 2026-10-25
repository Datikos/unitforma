from __future__ import annotations

import os

import pytest

os.environ.setdefault("UF_ENVIRONMENT", "test")
os.environ.setdefault("UF_LOG_JSON", "false")


@pytest.fixture
def settings():
    from unitforma.core.settings import get_settings

    get_settings.cache_clear()
    return get_settings()
