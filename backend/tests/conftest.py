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


@pytest.fixture(scope="module")
def kratos():
    """Fake Kratos per test module; modules that need their own define a fixture of this name."""
    from tests.fake_kratos import FakeKratos

    return FakeKratos()


@pytest.fixture(scope="module")
def client(kratos, tmp_path_factory):
    """The API app on local storage with the fake Kratos, one per test module."""
    from fastapi.testclient import TestClient

    os.environ["UF_STORAGE_BACKEND"] = "local"
    os.environ["UF_STORAGE_LOCAL_ROOT"] = str(tmp_path_factory.mktemp("storage"))
    from unitforma.core.settings import get_settings
    from unitforma.identity.deps import clear_whoami_cache, get_kratos
    from unitforma.main import create_app
    from unitforma.storage.service import reset_storage

    get_settings.cache_clear()
    reset_storage()
    clear_whoami_cache()
    app = create_app()
    app.dependency_overrides[get_kratos] = lambda: kratos
    with TestClient(app, headers={"X-Requested-With": "unitforma"}) as c:
        yield c
    get_settings.cache_clear()
    reset_storage()
