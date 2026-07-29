"""Nora API 应用工厂和基础中间件。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from nora.domain.base.exceptions import NoraError
from nora.infrastructure.config import Settings, get_settings
from nora.infrastructure.logging import configure_logging, get_logger


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建可测试的 FastAPI 应用实例。"""

    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_logging(app_settings)
        yield

    app = FastAPI(title="Nora API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
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
        return JSONResponse(status_code=400, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        get_logger("nora.api").exception("Unhandled API exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error_code": "internal_error", "message": "Internal server error"},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app


__all__ = ("create_app",)
