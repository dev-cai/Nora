from app.apps.api import create_app
from app.domain.base.exceptions import NoraError
from app.infrastructure.config import Settings
from fastapi.testclient import TestClient


def test_health_and_ready_include_request_id() -> None:
    with TestClient(create_app(Settings())) as client:
        health = client.get("/health", headers={"X-Request-ID": "req-health"})
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert health.headers["X-Request-ID"] == "req-health"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert ready.headers["X-Request-ID"]


def test_health_is_degraded_when_database_is_unavailable() -> None:
    settings = Settings(database_url="postgresql+asyncpg://nora:nora@127.0.0.1:1/nora")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_nora_error_maps_to_stable_response() -> None:
    app = create_app(Settings())

    @app.get("/test-nora-error")
    async def raise_nora_error() -> None:
        raise NoraError("bad request", error_code="bad_request")

    with TestClient(app) as client:
        response = client.get("/test-nora-error")

    assert response.status_code == 400
    assert response.json() == {"error_code": "bad_request", "message": "bad request"}


def test_unknown_error_is_sanitized_and_logged(capsys) -> None:
    app = create_app(Settings())

    @app.get("/test-unknown-error")
    async def raise_unknown_error() -> None:
        raise RuntimeError("secret internal details")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-unknown-error")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal_error",
        "message": "Internal server error",
    }
    assert "secret internal details" not in response.text
    captured = capsys.readouterr().out
    assert "Unhandled API exception" in captured
