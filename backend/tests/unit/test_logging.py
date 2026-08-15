import json
from io import StringIO

from app.infrastructure.config import LogFormat, Settings
from app.infrastructure.logging import (
    SECURITY_METRIC_NAME,
    SecurityReason,
    SecurityResult,
    SecuritySignal,
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
    log_security_signal,
)


def test_json_log_contains_timestamp_level_message_and_context() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON), stream=stream)
    bind_log_context(request_id="req-123")
    try:
        get_logger("test").info("request completed", user_id="u-1")
    finally:
        clear_log_context()

    record = json.loads(stream.getvalue())
    assert record["timestamp"]
    assert record["level"] == "info"
    assert record["message"] == "request completed"
    assert record["request_id"] == "req-123"
    assert "trace_id" not in record


def test_cleared_log_context_does_not_leak_to_next_operation() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON), stream=stream)

    bind_log_context(request_id="req-first")
    get_logger("test").info("first operation")
    clear_log_context()
    bind_log_context(request_id="req-second")
    try:
        get_logger("test").info("second operation")
    finally:
        clear_log_context()

    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["request_id"] == "req-first"
    assert "trace_id" not in first
    assert second["request_id"] == "req-second"
    assert "trace_id" not in second


def test_log_level_filters_debug_and_info() -> None:
    stream = StringIO()
    configure_logging(Settings(log_level="WARNING"), stream=stream)
    logger = get_logger("test")

    logger.debug("hidden debug")
    logger.info("hidden info")
    logger.warning("visible warning")

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "visible warning"


def test_sensitive_fields_are_redacted() -> None:
    stream = StringIO()
    configure_logging(Settings(), stream=stream)
    get_logger("test").info("credentials", token="secret-value", auth_secret_key="another-secret")

    record = json.loads(stream.getvalue())
    assert record["token"] == "[REDACTED]"
    assert record["auth_secret_key"] == "[REDACTED]"


def test_security_signal_is_countable_and_uses_only_bounded_dimensions() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON), stream=stream)

    log_security_signal(
        SecuritySignal.RATE_LIMITED,
        SecurityResult.REJECTED,
        reason=SecurityReason.COARSE_LIMIT,
        request_id="req-security",
        retry_after=42,
        trusted_proxy=False,
    )

    record = json.loads(stream.getvalue())
    assert record["metric_name"] == SECURITY_METRIC_NAME
    assert record["metric_value"] == 1
    assert record["security_signal"] == "authentication_rate_limited"
    assert record["result"] == "rejected"
    assert record["reason"] == "coarse_limit"
    assert record["request_id"] == "req-security"
    assert record["retry_after"] == 42
    assert record["trusted_proxy"] is False
    assert not {"username", "email", "password", "token", "secret"} & record.keys()
