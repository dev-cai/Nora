"""Nora API 应用工厂和基础中间件。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from structlog.contextvars import bind_contextvars, clear_contextvars

from nora.apps.api.routes.auth import router as auth_router
from nora.domain.base.exceptions import NoraError
from nora.infrastructure.config import Settings, get_settings
from nora.infrastructure.database import create_database_engine, create_session_factory
from nora.infrastructure.logging import configure_logging, get_logger


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
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(NoraError)
    async def nora_error_handler(_request: Request, exc: NoraError) -> JSONResponse:
        status_code = {
            "authentication_failed": 401,
            "username_conflict": 409,
            "email_conflict": 409,
            "database_unavailable": 503,
            "identity_persistence_failed": 503,
        }.get(exc.error_code, 400)
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        return JSONResponse(status_code=status_code, content=exc.to_dict(), headers=headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        get_logger("nora.api").exception("Unhandled API exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error_code": "internal_error", "message": "Internal server error"},
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
