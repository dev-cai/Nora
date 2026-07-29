import json
from io import StringIO

from nora.infrastructure.config import LogFormat, Settings
from nora.infrastructure.logging import (
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
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
