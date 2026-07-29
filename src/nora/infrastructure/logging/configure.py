"""使用 structlog 配置 JSON/console 日志输出。"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.types import EventDict, Processor

from nora.infrastructure.config import LogFormat, Settings, get_settings

_SENSITIVE_KEYS = frozenset(
    {"api_key", "auth_secret_key", "authorization", "cookie", "password", "secret", "token"}
)


def bind_log_context(**values: Any) -> None:
    """绑定当前异步上下文中的请求字段。"""

    bind_contextvars(**values)


def clear_log_context() -> None:
    """清理当前异步上下文中的请求字段。"""

    clear_contextvars()


def redact_sensitive_fields(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> MutableMapping[str, Any]:
    """对常见凭据字段脱敏，保留扩展该集合的单一入口。"""

    for key in tuple(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def add_message_field(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> MutableMapping[str, Any]:
    """将 structlog 的 event 字段统一命名为对外契约 message。"""

    event = event_dict.pop("event", None)
    if event is not None:
        event_dict["message"] = event
    return event_dict


def configure_logging(settings: Settings | None = None, stream: TextIO | None = None) -> None:
    """按配置初始化 structlog 和标准库日志。"""

    settings = settings or get_settings()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported log level: {settings.log_level}")

    logging.basicConfig(level=level, format="%(message)s", stream=stream or sys.stdout, force=True)
    renderer: Processor
    if settings.log_format is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.add_log_level,
            redact_sensitive_fields,
            add_message_field,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """获取带可选名称的结构化 logger。"""

    return structlog.get_logger(name)


__all__ = (
    "bind_log_context",
    "clear_log_context",
    "configure_logging",
    "get_logger",
)
