from fastapi.testclient import TestClient

from unitforma.main import create_app


def test_live_endpoint():
    with TestClient(create_app()) as client:
        r = client.get("/internal/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_problem_json_on_validation_error():
    with TestClient(create_app()) as client:
        r = client.get("/internal/domains/ask")  # missing ?domain=
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/problem+json")


def test_ask_accepts_the_shared_secret_as_query_or_header(monkeypatch):
    """Caddy's on-demand TLS `ask` is a plain GET, so the token may travel as ?token=; other
    internal callers keep the header. A wrong or missing token is refused before any lookup."""
    from unitforma.core.settings import get_settings

    monkeypatch.setenv("UF_INTERNAL_ASK_TOKEN", "s3cret")
    get_settings.cache_clear()
    try:
        host = get_settings().admin_host  # a platform host: allowed without a database lookup
        with TestClient(create_app()) as client:
            ask = f"/internal/domains/ask?domain={host}"
            assert client.get(ask).status_code == 403
            assert client.get(f"{ask}&token=wrong").status_code == 403
            assert client.get(f"{ask}&token=s3cret").status_code == 200
            r = client.get(
                f"/internal/domains/ask?domain={host}", headers={"X-Unitforma-Internal": "s3cret"}
            )
            assert r.status_code == 200
            assert r.json() == {"allowed": True}
    finally:
        get_settings.cache_clear()
