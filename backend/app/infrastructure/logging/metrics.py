"""Low-cardinality log-derived request and business metrics."""

from __future__ import annotations

from enum import StrEnum

from .configure import get_logger

HTTP_REQUEST_COUNT_METRIC_NAME = "nora_http_requests_total"
HTTP_REQUEST_DURATION_METRIC_NAME = "nora_http_request_duration_seconds"
BUSINESS_OPERATION_METRIC_NAME = "nora_business_operations_total"

_KNOWN_HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})


class MetricResult(StrEnum):
    SUCCEEDED = "succeeded"
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"


class BusinessOperation(StrEnum):
    ANALYSIS = "analysis"
    REPORT_GENERATION = "report_generation"
    ARTIFACT = "artifact"
    PDF_GENERATION = "pdf_generation"
    APPLICATION_RECORD = "application_record"


_BUSINESS_OPERATIONS_BY_ROUTE = {
    "analyze_decision_case": BusinessOperation.ANALYSIS,
    "generate_decision_report": BusinessOperation.REPORT_GENERATION,
    "upload_artifact": BusinessOperation.ARTIFACT,
    "delete_artifact": BusinessOperation.ARTIFACT,
    "generate_resume_pdf": BusinessOperation.PDF_GENERATION,
    "create_application_record": BusinessOperation.APPLICATION_RECORD,
    "transition_application_record": BusinessOperation.APPLICATION_RECORD,
}


def business_operation_for_route(route_name: str | None) -> BusinessOperation | None:
    """Map a static FastAPI route name to a bounded business operation."""

    if route_name is None:
        return None
    return _BUSINESS_OPERATIONS_BY_ROUTE.get(route_name)


def _metric_result(status_code: int) -> MetricResult:
    if status_code < 400:
        return MetricResult.SUCCEEDED
    if status_code < 500:
        return MetricResult.CLIENT_ERROR
    return MetricResult.SERVER_ERROR


def _status_class(status_code: int) -> str:
    if 100 <= status_code <= 599:
        return f"{status_code // 100}xx"
    return "other"


def _http_method(method: str) -> str:
    normalized = method.upper()
    return normalized if normalized in _KNOWN_HTTP_METHODS else "OTHER"


def log_http_request_metrics(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
    request_id: str,
) -> None:
    """Emit one count and one duration sample for a completed HTTP request."""

    dimensions = {
        "http_method": _http_method(method),
        "http_route": route,
        "status_class": _status_class(status_code),
        "result": _metric_result(status_code).value,
        "request_id": request_id,
    }
    logger = get_logger("nora.metrics")
    logger.info(
        "http_request_count",
        metric_name=HTTP_REQUEST_COUNT_METRIC_NAME,
        metric_value=1,
        **dimensions,
    )
    logger.info(
        "http_request_duration",
        metric_name=HTTP_REQUEST_DURATION_METRIC_NAME,
        metric_value=round(max(0.0, duration_seconds), 6),
        **dimensions,
    )


def log_business_operation_metric(
    operation: BusinessOperation,
    *,
    status_code: int,
    request_id: str,
) -> None:
    """Emit one bounded business-operation result without business identifiers."""

    get_logger("nora.metrics").info(
        "business_operation",
        metric_name=BUSINESS_OPERATION_METRIC_NAME,
        metric_value=1,
        business_operation=operation.value,
        result=_metric_result(status_code).value,
        request_id=request_id,
    )


__all__ = (
    "BUSINESS_OPERATION_METRIC_NAME",
    "HTTP_REQUEST_COUNT_METRIC_NAME",
    "HTTP_REQUEST_DURATION_METRIC_NAME",
    "BusinessOperation",
    "MetricResult",
    "business_operation_for_route",
    "log_business_operation_metric",
    "log_http_request_metrics",
)
