"""Nora API 应用工厂和基础中间件。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.apps.api.routes.auth import router as auth_router
from app.apps.api.routes.job_postings import router as job_postings_router
from app.apps.api.routes.profile import router as profile_router
from app.apps.api.routes.resumes import router as resumes_router
from app.domain.base.exceptions import NoraError
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import create_database_engine, create_session_factory
from app.infrastructure.logging import (
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
)

_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _resolve_correlation_id(request: Request, header_name: str) -> str:
    value = request.headers.get(header_name)
    if value is None:
        return str(uuid4())
    if _CORRELATION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(header_name)
    return value


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建可测试的 FastAPI 应用实例。"""

    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(app_settings)
        _app.state.database_engine = None
        _app.state.session_factory = None
        _app.state.settings = app_settings
        if app_settings.database_url:
            _app.state.database_engine = create_database_engine(app_settings)
            _app.state.session_factory = create_session_factory(_app.state.database_engine)
        try:
            yield
        finally:
            if _app.state.database_engine is not None:
                await _app.state.database_engine.dispose()

    app = FastAPI(title="Nora API", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(job_postings_router)
    app.include_router(profile_router)
    app.include_router(resumes_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            request_id = _resolve_correlation_id(request, "X-Request-ID")
            trace_id = _resolve_correlation_id(request, "X-Trace-ID")
        except ValueError as exc:
            header_name = str(exc)
            return JSONResponse(
                status_code=400,
                content={
                    "error_code": "invalid_correlation_id",
                    "message": (
                        f"{header_name} must be 1-128 characters using ASCII letters, "
                        "digits, '.', '_' or '-'"
                    ),
                },
            )

        request.state.request_id = request_id
        request.state.trace_id = trace_id
        bind_log_context(request_id=request_id, trace_id=trace_id)
        try:
            response = await call_next(request)
        finally:
            clear_log_context()
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response

    @app.exception_handler(NoraError)
    async def nora_error_handler(_request: Request, exc: NoraError) -> JSONResponse:
        status_code = {
            "authentication_failed": 401,
            "username_conflict": 409,
            "email_conflict": 409,
            "idempotency_conflict": 409,
            "entity_not_found": 404,
            "database_unavailable": 503,
            "identity_persistence_failed": 503,
            "job_posting_persistence_failed": 503,
            "profile_version_conflict": 409,
            "resume_version_conflict": 409,
        }.get(exc.error_code, 400)
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        return JSONResponse(status_code=status_code, content=exc.to_dict(), headers=headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        bind_log_context(request_id=request_id, trace_id=trace_id)
        try:
            get_logger("nora.api").exception("Unhandled API exception", exc_info=exc)
        finally:
            clear_log_context()
        return JSONResponse(
            status_code=500,
            content={"error_code": "internal_error", "message": "Internal server error"},
            headers={"X-Request-ID": request_id, "X-Trace-ID": trace_id},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        if app.state.database_engine is not None:
            try:
                async with app.state.database_engine.connect() as connection:
                    await connection.exec_driver_sql("SELECT 1")
            except Exception:
                return {"status": "degraded", "database": "unavailable"}
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app


__all__ = ("create_app",)
