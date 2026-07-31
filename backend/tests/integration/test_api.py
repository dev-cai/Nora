import json
from uuid import UUID

import pytest
from app.apps.api import create_app
from app.domain.base.exceptions import NoraError
from app.infrastructure.config import Settings
from app.infrastructure.logging import get_logger
from fastapi.testclient import TestClient


def test_health_and_ready_include_request_and_trace_ids() -> None:
    with TestClient(create_app(Settings())) as client:
        health = client.get(
            "/health",
            headers={"X-Request-ID": "req-health", "X-Trace-ID": "trace.health_1"},
        )
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert health.headers["X-Request-ID"] == "req-health"
    assert health.headers["X-Trace-ID"] == "trace.health_1"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    UUID(ready.headers["X-Request-ID"])
    UUID(ready.headers["X-Trace-ID"])


@pytest.mark.parametrize("header_name", ["X-Request-ID", "X-Trace-ID"])
@pytest.mark.parametrize("invalid_value", ["", "contains space", "../escape", b"\xff", "x" * 129])
def test_invalid_correlation_id_is_rejected(header_name: str, invalid_value: str | bytes) -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/ready", headers={header_name: invalid_value})

    assert response.status_code == 400
    assert response.json() == {
        "error_code": "invalid_correlation_id",
        "message": (
            f"{header_name} must be 1-128 characters using ASCII letters, digits, '.', '_' or '-'"
        ),
    }
    assert "X-Request-ID" not in response.headers
    assert "X-Trace-ID" not in response.headers


@pytest.mark.parametrize("header_name", ["X-Request-ID", "X-Trace-ID"])
def test_max_length_correlation_id_is_accepted(header_name: str) -> None:
    value = "x" * 128
    with TestClient(create_app(Settings())) as client:
        response = client.get("/ready", headers={header_name: value})

    assert response.status_code == 200
    assert response.headers[header_name] == value


def test_request_log_context_does_not_leak_between_requests(capsys) -> None:
    app = create_app(Settings())

    @app.get("/test-log-context")
    async def log_context() -> dict[str, str]:
        get_logger("test.trace").info("trace probe")
        return {"status": "logged"}

    with TestClient(app) as client:
        first = client.get(
            "/test-log-context",
            headers={"X-Request-ID": "req-first", "X-Trace-ID": "trace-first"},
        )
        second = client.get(
            "/test-log-context",
            headers={"X-Request-ID": "req-second", "X-Trace-ID": "trace-second"},
        )

    assert first.status_code == second.status_code == 200
    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and '"message": "trace probe"' in line
    ]
    assert [(record["request_id"], record["trace_id"]) for record in records] == [
        ("req-first", "trace-first"),
        ("req-second", "trace-second"),
    ]


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
        response = client.get(
            "/test-unknown-error",
            headers={"X-Request-ID": "req-error", "X-Trace-ID": "trace-error"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal_error",
        "message": "Internal server error",
    }
    assert response.headers["X-Request-ID"] == "req-error"
    assert response.headers["X-Trace-ID"] == "trace-error"
    assert "secret internal details" not in response.text
    captured = capsys.readouterr().out
    assert "Unhandled API exception" in captured
    assert '"request_id": "req-error"' in captured
    assert '"trace_id": "trace-error"' in captured
