"""Request security boundary for Origin, trusted ingress and coarse authentication limits."""

from datetime import datetime, timezone
from ipaddress import ip_address, ip_network

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.apps.api.errors import ApiProblem, database_problem
from app.domain.base.exceptions import ErrorCategory, ErrorCode
from app.infrastructure.auth import AuthenticationDigester
from app.infrastructure.config import Environment, Settings
from app.infrastructure.database import SqlAlchemyAuthenticationRateLimitRepository
from app.infrastructure.logging import get_logger

AUTHENTICATION_PATHS = frozenset({"/auth/login", "/auth/register"})
CORS_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "OPTIONS"})
CORS_HEADERS = frozenset(
    {"authorization", "content-type", "idempotency-key", "x-request-id"}
)


def resolve_client_identifier(request: Request, settings: Settings) -> tuple[str, bool]:
    """Use one ingress-overwritten address only when the direct peer is trusted."""

    direct = request.client.host if request.client is not None else "unknown"
    if settings.env is not Environment.PROD or settings.trusted_proxy_cidr is None:
        return direct, False
    try:
        peer = ip_address(direct)
        trusted = peer in ip_network(settings.trusted_proxy_cidr, strict=False)
    except ValueError:
        return direct, False
    forwarded_values = request.headers.getlist("x-forwarded-for")
    proto_values = request.headers.getlist("x-forwarded-proto")
    if not trusted or len(forwarded_values) != 1 or len(proto_values) != 1:
        return direct, False
    forwarded = forwarded_values[0]
    if "," in forwarded or proto_values[0].lower() != "https":
        return direct, False
    try:
        return str(ip_address(forwarded)), True
    except ValueError:
        return direct, False


def validate_origin(request: Request, settings: Settings) -> JSONResponse | None:
    """Reject disallowed actual requests and preflight before routing or body parsing."""

    if settings.env is not Environment.PROD:
        return None
    origin = request.headers.get("origin")
    if origin is None:
        return None
    if origin != settings.public_origin:
        _log_origin_rejection(request)
        return _problem_response(
            ErrorCode.ORIGIN_NOT_ALLOWED,
            ErrorCategory.FORBIDDEN,
            "Request origin is not allowed",
            403,
        )
    if request.method != "OPTIONS":
        return None
    requested_method = request.headers.get("access-control-request-method", "").upper()
    requested_headers = {
        value.strip().lower()
        for value in request.headers.get("access-control-request-headers", "").split(",")
        if value.strip()
    }
    if requested_method not in CORS_METHODS or not requested_headers <= CORS_HEADERS:
        _log_origin_rejection(request)
        return _problem_response(
            ErrorCode.ORIGIN_NOT_ALLOWED,
            ErrorCategory.FORBIDDEN,
            "CORS preflight is not allowed",
            403,
        )
    return None


async def enforce_coarse_authentication_limit(
    request: Request, settings: Settings
) -> JSONResponse | None:
    """Consume the PostgreSQL one-minute bucket before auth request body handling."""

    if request.method != "POST" or request.url.path not in AUTHENTICATION_PATHS:
        return None
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return JSONResponse(status_code=503, content=database_problem().model_dump(mode="json"))
    digest = AuthenticationDigester(settings.auth_rate_limit_secret).digest(
        "coarse-client", request.state.client_identifier
    )
    try:
        async with factory() as session:
            decision = await SqlAlchemyAuthenticationRateLimitRepository(session).consume_coarse(
                digest, datetime.now(timezone.utc)
            )
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content=database_problem().model_dump(mode="json"))
    if decision.allowed:
        return None
    get_logger("nora.security").info(
        "authentication_rate_limited",
        result="rejected",
        request_id=getattr(request.state, "request_id", None),
        retry_after=decision.retry_after,
        trusted_proxy=getattr(request.state, "trusted_proxy", False),
    )
    return _problem_response(
        ErrorCode.AUTHENTICATION_RATE_LIMITED,
        ErrorCategory.RATE_LIMITED,
        "Authentication rate limit exceeded",
        429,
        retry_after=decision.retry_after,
    )


def production_registration_response(request: Request, settings: Settings) -> JSONResponse | None:
    """Hide public registration in production without parsing or hashing credentials."""

    if (
        settings.env is Environment.PROD
        and request.method == "POST"
        and request.url.path == "/auth/register"
    ):
        return _problem_response(
            ErrorCode.ENTITY_NOT_FOUND,
            ErrorCategory.NOT_FOUND,
            "Entity not found",
            404,
        )
    return None


def _problem_response(
    code: ErrorCode,
    category: ErrorCategory,
    message: str,
    status_code: int,
    *,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(
        status_code=status_code,
        content=ApiProblem(
            error_code=code, error_category=category, message=message
        ).model_dump(mode="json"),
        headers=headers,
    )


def _log_origin_rejection(request: Request) -> None:
    get_logger("nora.security").info(
        "origin_rejected",
        result="rejected",
        request_id=getattr(request.state, "request_id", None),
        trusted_proxy=getattr(request.state, "trusted_proxy", False),
    )
