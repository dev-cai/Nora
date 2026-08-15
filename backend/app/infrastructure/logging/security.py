"""Low-cardinality authentication signals for log-derived security metrics."""

from enum import StrEnum

from .configure import get_logger

SECURITY_METRIC_NAME = "nora_security_events_total"


class SecuritySignal(StrEnum):
    LOGIN = "authentication_login"
    AUTHENTICATION_REJECTED = "authentication_rejected"
    RATE_LIMITED = "authentication_rate_limited"
    ORIGIN_REJECTED = "origin_rejected"
    OWNER_BOOTSTRAP = "owner_bootstrap"
    OWNER_RECOVERY = "owner_recovery"
    KEY_RING_LOADED = "authentication_key_ring_loaded"
    TRUSTED_PROXY_CONFIGURED = "trusted_proxy_configured"


class SecurityResult(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    CREATED = "created"
    REPLAYED = "replayed"
    ALREADY_PROVISIONED = "already_provisioned"
    RECOVERED = "recovered"


class SecurityReason(StrEnum):
    CREDENTIALS = "credentials"
    TOKEN = "token"
    COARSE_LIMIT = "coarse_limit"
    LOGIN_LIMIT = "login_limit"
    ORIGIN = "origin"


def log_security_signal(
    signal: SecuritySignal,
    result: SecurityResult,
    *,
    reason: SecurityReason | None = None,
    request_id: str | None = None,
    retry_after: int | None = None,
    trusted_proxy: bool | None = None,
    session_version: int | None = None,
    key_count: int | None = None,
    key_id: str | None = None,
) -> None:
    """Emit one countable event without accepting identity or credential fields."""

    fields: dict[str, str | int | bool] = {
        "metric_name": SECURITY_METRIC_NAME,
        "metric_value": 1,
        "security_signal": signal.value,
        "result": result.value,
    }
    if reason is not None:
        fields["reason"] = reason.value
    if request_id is not None:
        fields["request_id"] = request_id
    if retry_after is not None:
        fields["retry_after"] = max(1, int(retry_after))
    if trusted_proxy is not None:
        fields["trusted_proxy"] = trusted_proxy
    if session_version is not None:
        fields["session_version"] = max(1, int(session_version))
    if key_count is not None:
        fields["key_count"] = max(1, int(key_count))
    if key_id is not None:
        fields["key_id"] = key_id
    get_logger("nora.security").info(signal.value, **fields)


__all__ = (
    "SECURITY_METRIC_NAME",
    "SecurityReason",
    "SecurityResult",
    "SecuritySignal",
    "log_security_signal",
)
