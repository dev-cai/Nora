import asyncio
import json
from types import TracebackType
from uuid import UUID

import pytest
from app.apps.api import create_app
from app.domain.base.exceptions import ErrorCode, NoraError
from app.infrastructure.config import Settings
from app.infrastructure.logging import get_logger
from fastapi.testclient import TestClient


class _FakeConnection:
    def __init__(
        self, *, enter_error: Exception | None = None, query_error: Exception | None = None
    ):
        self.enter_error = enter_error
        self.query_error = query_error
        self.block_query = False

    async def __aenter__(self) -> "_FakeConnection":
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def exec_driver_sql(self, statement: str) -> None:
        assert statement == "SELECT 1"
        if self.block_query:
            await asyncio.Event().wait()
        if self.query_error is not None:
            raise self.query_error


class _FakeEngine:
    def __init__(self, connection: _FakeConnection):
        self.connection = connection
        self.connect_calls = 0
        self.disposed = False

    def connect(self) -> _FakeConnection:
        self.connect_calls += 1
        return self.connection

    async def dispose(self) -> None:
        self.disposed = True


def _client_with_engine(monkeypatch: pytest.MonkeyPatch, engine: _FakeEngine) -> TestClient:
    monkeypatch.setattr("app.apps.api.app.create_database_engine", lambda _settings: engine)
    return TestClient(create_app(Settings(database_url="postgresql+asyncpg://nora:nora@db/nora")))


def test_live_returns_request_id_and_ignores_trace_header() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get(
            "/live",
            headers={"X-Request-ID": "req-live", "X-Trace-ID": "contains spaces"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["X-Request-ID"] == "req-live"
    assert "X-Trace-ID" not in response.headers


def test_missing_request_id_is_generated() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/live")

    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])


@pytest.mark.parametrize("invalid_value", ["", "contains space", "../escape", b"\xff", "x" * 129])
def test_invalid_request_id_is_rejected_with_generated_request_id(
    invalid_value: str | bytes,
) -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/live", headers={"X-Request-ID": invalid_value})

    assert response.status_code == 400
    assert response.json() == {
        "error_code": "invalid_correlation_id",
        "error_category": "invalid_input",
        "message": (
            "X-Request-ID must be 1-128 characters using ASCII letters, digits, '.', '_' or '-'"
        ),
    }
    UUID(response.headers["X-Request-ID"])
    assert "X-Trace-ID" not in response.headers


def test_max_length_request_id_is_accepted() -> None:
    value = "x" * 128
    with TestClient(create_app(Settings())) as client:
        response = client.get("/live", headers={"X-Request-ID": value})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == value


def test_request_log_context_does_not_leak_between_requests(capsys) -> None:
    app = create_app(Settings())

    @app.get("/test-log-context")
    async def log_context() -> dict[str, str]:
        get_logger("test.request").info("request probe")
        return {"status": "logged"}

    with TestClient(app) as client:
        first = client.get("/test-log-context", headers={"X-Request-ID": "req-first"})
        second = client.get("/test-log-context", headers={"X-Request-ID": "req-second"})

    assert first.status_code == second.status_code == 200
    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and '"message": "request probe"' in line
    ]
    assert [record["request_id"] for record in records] == ["req-first", "req-second"]
    assert all("trace_id" not in record for record in records)


def test_live_does_not_inspect_failed_database_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine(_FakeConnection(enter_error=RuntimeError("database unavailable")))
    with _client_with_engine(monkeypatch, engine) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert engine.connect_calls == 0
    assert engine.disposed is True


def test_ready_checks_postgresql(database_url: str) -> None:
    with TestClient(create_app(Settings(database_url=database_url))) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_is_unavailable_without_database_configuration() -> None:
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    UUID(response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    "connection",
    [
        _FakeConnection(enter_error=RuntimeError("connection failed")),
        _FakeConnection(query_error=RuntimeError("query failed")),
    ],
    ids=["connection-error", "query-error"],
)
def test_ready_is_unavailable_on_database_failure(
    monkeypatch: pytest.MonkeyPatch, connection: _FakeConnection
) -> None:
    engine = _FakeEngine(connection)
    with _client_with_engine(monkeypatch, engine) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert engine.connect_calls == 1


def test_ready_is_unavailable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection()
    connection.block_query = True
    engine = _FakeEngine(connection)
    monkeypatch.setattr("app.apps.api.app._READINESS_TIMEOUT_SECONDS", 0.01)

    with _client_with_engine(monkeypatch, engine) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}


def test_health_route_is_retired() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/health")

    assert response.status_code == 404


def test_nora_error_maps_to_stable_response() -> None:
    app = create_app(Settings())

    @app.get("/test-nora-error")
    async def raise_nora_error() -> None:
        raise NoraError("bad request", error_code=ErrorCode.INVALID_JD_TEXT)

    with TestClient(app) as client:
        response = client.get("/test-nora-error")

    assert response.status_code == 400
    assert response.json() == {
        "error_code": "invalid_jd_text",
        "error_category": "invalid_input",
        "message": "bad request",
    }


def test_request_validation_uses_stable_problem_shape() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.post("/auth/register", json={"username": "missing-fields"})

    assert response.status_code == 503
    assert response.json() == {
        "error_code": "database_unavailable",
        "error_category": "service_unavailable",
        "message": "Database is unavailable",
    }


def test_unknown_error_is_sanitized_and_logged(capsys) -> None:
    app = create_app(Settings())

    @app.get("/test-unknown-error")
    async def raise_unknown_error() -> None:
        raise RuntimeError("secret internal details")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/test-unknown-error",
            headers={"X-Request-ID": "req-error", "X-Trace-ID": "ignored-trace"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal_error",
        "error_category": "internal",
        "message": "Internal server error",
    }
    assert response.headers["X-Request-ID"] == "req-error"
    assert "X-Trace-ID" not in response.headers
    assert "secret internal details" not in response.text
    captured = capsys.readouterr().out
    assert "Unhandled API exception" in captured
    assert '"request_id": "req-error"' in captured
    assert '"trace_id"' not in captured
