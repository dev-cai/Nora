import json
from io import StringIO

from app.infrastructure.config import LogFormat, Settings
from app.infrastructure.logging import (
    BUSINESS_OPERATION_METRIC_NAME,
    HTTP_REQUEST_COUNT_METRIC_NAME,
    HTTP_REQUEST_DURATION_METRIC_NAME,
    SECURITY_METRIC_NAME,
    BusinessOperation,
    SecurityReason,
    SecurityResult,
    SecuritySignal,
    bind_log_context,
    business_operation_for_route,
    clear_log_context,
    configure_logging,
    get_logger,
    log_business_operation_metric,
    log_http_request_metrics,
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
    get_logger("test").info(
        "credentials",
        token="secret-value",
        auth_secret_key="another-secret",
        signed_url="https://storage.invalid/private?signature=secret",
        prompt="private prompt",
        resume_text="private resume",
        jd_text="private job description",
        pdf_text="private pdf",
        request_id="req-safe",
    )

    record = json.loads(stream.getvalue())
    for key in (
        "token",
        "auth_secret_key",
        "signed_url",
        "prompt",
        "resume_text",
        "jd_text",
        "pdf_text",
    ):
        assert record[key] == "[REDACTED]"
    assert record["request_id"] == "req-safe"
    assert "private" not in stream.getvalue()
    assert "signature=secret" not in stream.getvalue()


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


def test_http_request_metrics_are_countable_and_use_static_dimensions() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON), stream=stream)

    log_http_request_metrics(
        method="post",
        route="/reports/{report_id}/decision",
        status_code=409,
        duration_seconds=0.01234567,
        request_id="req-http",
    )

    count, duration = (json.loads(line) for line in stream.getvalue().splitlines())
    assert count["metric_name"] == HTTP_REQUEST_COUNT_METRIC_NAME
    assert count["metric_value"] == 1
    assert count["http_method"] == "POST"
    assert count["http_route"] == "/reports/{report_id}/decision"
    assert count["status_class"] == "4xx"
    assert count["result"] == "client_error"
    assert count["request_id"] == "req-http"
    assert duration["metric_name"] == HTTP_REQUEST_DURATION_METRIC_NAME
    assert duration["metric_value"] == 0.012346
    assert not {"user_id", "report_id", "url", "body", "trace_id"} & count.keys()


def test_business_operation_metric_uses_only_bounded_operation_and_result() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON), stream=stream)

    log_business_operation_metric(
        BusinessOperation.PDF_GENERATION,
        status_code=201,
        request_id="req-pdf",
    )

    record = json.loads(stream.getvalue())
    assert record["metric_name"] == BUSINESS_OPERATION_METRIC_NAME
    assert record["metric_value"] == 1
    assert record["business_operation"] == "pdf_generation"
    assert record["result"] == "succeeded"
    assert record["request_id"] == "req-pdf"
    assert not {"user_id", "variant_id", "artifact_id", "url", "body", "trace_id"} & record.keys()


def test_business_operation_routes_are_fixed_and_unknown_routes_are_ignored() -> None:
    assert business_operation_for_route("analyze_decision_case") is BusinessOperation.ANALYSIS
    assert (
        business_operation_for_route("generate_decision_report")
        is BusinessOperation.REPORT_GENERATION
    )
    assert business_operation_for_route("upload_artifact") is BusinessOperation.ARTIFACT
    assert business_operation_for_route("delete_artifact") is BusinessOperation.ARTIFACT
    assert business_operation_for_route("generate_resume_pdf") is BusinessOperation.PDF_GENERATION
    assert (
        business_operation_for_route("create_application_record")
        is BusinessOperation.APPLICATION_RECORD
    )
    assert (
        business_operation_for_route("transition_application_record")
        is BusinessOperation.APPLICATION_RECORD
    )
    assert business_operation_for_route("get_decision_report") is None
    assert business_operation_for_route(None) is None
