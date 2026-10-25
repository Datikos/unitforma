import os


def test_secret_file_is_loaded(tmp_path, monkeypatch):
    from unitforma.core.settings import get_settings

    secret = tmp_path / "ask_token"
    secret.write_text("s3cret\n")
    monkeypatch.delenv("UF_INTERNAL_ASK_TOKEN", raising=False)
    monkeypatch.setenv("UF_INTERNAL_ASK_TOKEN_FILE", str(secret))
    get_settings.cache_clear()
    assert get_settings().internal_ask_token == "s3cret"  # noqa: S105
    get_settings.cache_clear()
    os.environ.pop("UF_INTERNAL_ASK_TOKEN", None)


def test_password_injection():
    from unitforma.core.settings import _with_password

    assert (
        _with_password("postgresql+asyncpg://app_rw@postgres:5432/unitforma", "p@ss:word")
        == "postgresql+asyncpg://app_rw:p%40ss%3Aword@postgres:5432/unitforma"
    )
