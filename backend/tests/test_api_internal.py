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
