"""Nora API 应用工厂和基础中间件。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.apps.api.errors import (
    HTTP_STATUS_BY_CATEGORY,
    ApiProblem,
    database_problem,
    internal_problem,
    problem_from_error,
    problem_responses,
    validation_problem,
)
from app.apps.api.routes.application_records import router as application_records_router
from app.apps.api.routes.artifacts import router as artifacts_router
from app.apps.api.routes.auth import router as auth_router
from app.apps.api.routes.companies import router as companies_router
from app.apps.api.routes.decisions import decision_router, report_router
from app.apps.api.routes.interviews import (
    application_router as application_interviews_router,
)
from app.apps.api.routes.interviews import (
    router as interviews_router,
)
from app.apps.api.routes.job_inputs import router as job_inputs_router
from app.apps.api.routes.job_postings import router as job_postings_router
from app.apps.api.routes.job_requirements import router as job_requirements_router
from app.apps.api.routes.knowledge import router as knowledge_router
from app.apps.api.routes.message_drafts import router as message_drafts_router
from app.apps.api.routes.profile import router as profile_router
from app.apps.api.routes.resume_pdfs import router as resume_pdfs_router
from app.apps.api.routes.resume_variants import template_router, variant_router
from app.apps.api.routes.resumes import router as resumes_router
from app.apps.api.security import (
    enforce_coarse_authentication_limit,
    production_registration_response,
    resolve_client_identifier,
    validate_origin,
)
from app.domain.base.exceptions import ErrorCategory, ErrorCode, NoraError
from app.infrastructure.config import Environment, Settings, get_settings
from app.infrastructure.database import create_database_engine, create_session_factory
from app.infrastructure.logging import (
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
from app.infrastructure.object_storage import create_minio_storage

_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_READINESS_TIMEOUT_SECONDS = 2.0


def _resolve_request_id(request: Request) -> str:
    value = request.headers.get("X-Request-ID")
    if value is None:
        return str(uuid4())
    if _CORRELATION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError
    return value


def _record_request_metrics(
    request: Request,
    *,
    request_id: str,
    status_code: int,
    started_at: float,
) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    route_name = getattr(route, "name", None)
    if not isinstance(route_path, str):
        route_path = "_unmatched"
    if not isinstance(route_name, str):
        route_name = None

    log_http_request_metrics(
        method=request.method,
        route=route_path,
        status_code=status_code,
        duration_seconds=perf_counter() - started_at,
        request_id=request_id,
    )
    operation = business_operation_for_route(route_name)
    if operation is not None:
        log_business_operation_metric(
            operation,
            status_code=status_code,
            request_id=request_id,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建可测试的 FastAPI 应用实例。"""

    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(app_settings)
        _app.state.database_engine = None
        _app.state.session_factory = None
        _app.state.settings = app_settings
        if app_settings.env is Environment.PROD:
            log_security_signal(
                SecuritySignal.KEY_RING_LOADED,
                SecurityResult.SUCCEEDED,
                key_count=len(app_settings.jwt_key_ring),
                key_id=app_settings.auth_active_kid,
            )
            log_security_signal(
                SecuritySignal.TRUSTED_PROXY_CONFIGURED,
                SecurityResult.SUCCEEDED,
                trusted_proxy=True,
            )
        if app_settings.database_url:
            _app.state.database_engine = create_database_engine(app_settings)
            _app.state.session_factory = create_session_factory(_app.state.database_engine)
        try:
            yield
        finally:
            if _app.state.database_engine is not None:
                await _app.state.database_engine.dispose()

    app = FastAPI(title="Nora API", lifespan=lifespan)
    common_responses = problem_responses()
    app.include_router(auth_router, responses=problem_responses(ErrorCategory.RATE_LIMITED))
    app.include_router(artifacts_router, responses=common_responses)
    app.include_router(knowledge_router, responses=common_responses)
    app.include_router(application_records_router, responses=common_responses)
    app.include_router(application_interviews_router, responses=common_responses)
    app.include_router(companies_router, responses=common_responses)
    app.include_router(decision_router, responses=common_responses)
    app.include_router(report_router, responses=common_responses)
    app.include_router(
        job_inputs_router,
        responses=problem_responses(
            ErrorCategory.UPSTREAM_FAILURE,
            ErrorCategory.UPSTREAM_TIMEOUT,
        ),
    )
    app.include_router(job_postings_router, responses=common_responses)
    app.include_router(job_requirements_router, responses=common_responses)
    app.include_router(interviews_router, responses=common_responses)
    app.include_router(message_drafts_router, responses=common_responses)
    app.include_router(profile_router, responses=common_responses)
    app.include_router(resumes_router, responses=common_responses)
    app.include_router(resume_pdfs_router, responses=common_responses)
    app.include_router(template_router, responses=common_responses)
    app.include_router(variant_router, responses=common_responses)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            [app_settings.public_origin]
            if app_settings.env is Environment.PROD and app_settings.public_origin
            else ["*"]
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started_at = perf_counter()
        response: Response
        try:
            request_id = _resolve_request_id(request)
        except ValueError:
            request_id = str(uuid4())
            response = JSONResponse(
                status_code=400,
                content=ApiProblem(
                    error_code=ErrorCode.INVALID_CORRELATION_ID,
                    error_category=ErrorCategory.INVALID_INPUT,
                    message=(
                        "X-Request-ID must be 1-128 characters using ASCII letters, "
                        "digits, '.', '_' or '-'"
                    ),
                ).model_dump(mode="json"),
                headers={"X-Request-ID": request_id},
            )
            _record_request_metrics(
                request,
                request_id=request_id,
                status_code=response.status_code,
                started_at=started_at,
            )
            return response

        request.state.request_id = request_id
        client_identifier, trusted_proxy = resolve_client_identifier(request, app_settings)
        request.state.client_identifier = client_identifier
        request.state.trusted_proxy = trusted_proxy
        bind_log_context(request_id=request_id)
        try:
            coarse_response = await enforce_coarse_authentication_limit(request, app_settings)
            if coarse_response is not None:
                response = coarse_response
            else:
                origin_response = validate_origin(request, app_settings)
                if origin_response is not None:
                    response = origin_response
                else:
                    register_response = production_registration_response(request, app_settings)
                    if register_response is not None:
                        response = register_response
                    else:
                        response = await call_next(request)
        except Exception:
            _record_request_metrics(
                request,
                request_id=request_id,
                status_code=500,
                started_at=started_at,
            )
            raise
        finally:
            clear_log_context()
        response.headers["X-Request-ID"] = request_id
        _record_request_metrics(
            request,
            request_id=request_id,
            status_code=response.status_code,
            started_at=started_at,
        )
        return response

    @app.exception_handler(NoraError)
    async def nora_error_handler(request: Request, exc: NoraError) -> JSONResponse:
        problem = problem_from_error(exc)
        status_code = HTTP_STATUS_BY_CATEGORY[problem.error_category]
        if problem.error_category is ErrorCategory.INTERNAL:
            get_logger("nora.api").error(
                "Internal Nora error reached API boundary",
                error_code=exc.error_code,
                request_id=getattr(request.state, "request_id", None),
            )
        elif problem.error_category is ErrorCategory.AUTHENTICATION:
            log_security_signal(
                SecuritySignal.AUTHENTICATION_REJECTED,
                SecurityResult.REJECTED,
                reason=(
                    SecurityReason.CREDENTIALS
                    if request.url.path == "/auth/login"
                    else SecurityReason.TOKEN
                ),
                request_id=getattr(request.state, "request_id", None),
                trusted_proxy=getattr(request.state, "trusted_proxy", False),
            )
        elif problem.error_category is ErrorCategory.RATE_LIMITED:
            log_security_signal(
                SecuritySignal.RATE_LIMITED,
                SecurityResult.REJECTED,
                reason=SecurityReason.LOGIN_LIMIT,
                request_id=getattr(request.state, "request_id", None),
                retry_after=getattr(exc, "retry_after", None),
                trusted_proxy=getattr(request.state, "trusted_proxy", False),
            )
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if problem.error_category is ErrorCategory.AUTHENTICATION
            else None
        )
        if problem.error_category is ErrorCategory.RATE_LIMITED:
            headers = {"Retry-After": str(getattr(exc, "retry_after", 1))}
        return JSONResponse(
            status_code=status_code,
            content=problem.model_dump(mode="json"),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        problem = validation_problem()
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CATEGORY[problem.error_category],
            content=problem.model_dump(mode="json"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        get_logger("nora.api").error(
            "Database operation unavailable",
            error_type=type(exc).__name__,
            request_id=getattr(request.state, "request_id", None),
        )
        problem = database_problem()
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CATEGORY[problem.error_category],
            content=problem.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        bind_log_context(request_id=request_id)
        try:
            get_logger("nora.api").exception("Unhandled API exception", exc_info=exc)
        finally:
            clear_log_context()
        problem = internal_problem()
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CATEGORY[problem.error_category],
            content=problem.model_dump(mode="json"),
            headers={"X-Request-ID": request_id},
        )

    @app.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        if app.state.database_engine is not None:
            try:
                async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
                    async with app.state.database_engine.connect() as connection:
                        await connection.exec_driver_sql("SELECT 1")
                        if app_settings.env is Environment.PROD:
                            owner_state = (
                                await connection.execute(
                                    text(
                                        "SELECT "
                                        "(SELECT count(*) FROM users) AS total, "
                                        "(SELECT count(*) FROM users WHERE is_active) AS active, "
                                        "(SELECT count(*) FROM beta_owner b JOIN users u "
                                        "ON u.id = b.user_id WHERE b.slot = 1 "
                                        "AND u.is_active) AS tracked"
                                    )
                                )
                            ).one()
                            if (
                                owner_state.total != 1
                                or owner_state.active != 1
                                or owner_state.tracked != 1
                            ):
                                raise RuntimeError("beta owner state is not ready")
            except Exception:
                pass
            else:
                if app_settings.env is Environment.PROD:
                    storage = create_minio_storage(
                        endpoint=app_settings.artifact_storage_endpoint,
                        access_key=app_settings.artifact_storage_access_key,
                        secret_key=app_settings.artifact_storage_secret_key,
                        bucket=app_settings.artifact_storage_bucket,
                        secure=app_settings.artifact_storage_secure,
                    )
                    try:
                        async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
                            storage_ready = await storage.ready()
                    except Exception:
                        storage_ready = False
                    if not storage_ready:
                        return JSONResponse(
                            status_code=503,
                            content={
                                "status": "not_ready",
                                "artifact_storage": "unavailable",
                            },
                        )
                return JSONResponse(status_code=200, content={"status": "ready"})

        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )

    return app


__all__ = ("create_app",)
