"""API problem response and centralized HTTP error mapping."""

from types import MappingProxyType
from typing import Any, Final, Mapping

from pydantic import BaseModel

from app.domain.base.exceptions import (
    ERROR_CATEGORY_BY_CODE,
    ErrorCategory,
    ErrorCode,
    NoraError,
)


class ApiProblem(BaseModel):
    """The only public JSON error response shape."""

    error_code: ErrorCode
    error_category: ErrorCategory
    message: str


HTTP_STATUS_BY_CATEGORY: Final[Mapping[ErrorCategory, int]] = MappingProxyType(
    {
        ErrorCategory.INVALID_INPUT: 400,
        ErrorCategory.AUTHENTICATION: 401,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.PAYLOAD_TOO_LARGE: 413,
        ErrorCategory.UNSUPPORTED_MEDIA_TYPE: 415,
        ErrorCategory.REQUEST_VALIDATION: 422,
        ErrorCategory.UPSTREAM_FAILURE: 502,
        ErrorCategory.SERVICE_UNAVAILABLE: 503,
        ErrorCategory.UPSTREAM_TIMEOUT: 504,
        ErrorCategory.INTERNAL: 500,
    }
)

_DESCRIPTION_BY_CATEGORY: Final[Mapping[ErrorCategory, str]] = MappingProxyType(
    {
        ErrorCategory.INVALID_INPUT: "Invalid input",
        ErrorCategory.AUTHENTICATION: "Authentication required or failed",
        ErrorCategory.NOT_FOUND: "Resource not found",
        ErrorCategory.CONFLICT: "Resource conflict",
        ErrorCategory.PAYLOAD_TOO_LARGE: "Payload too large",
        ErrorCategory.UNSUPPORTED_MEDIA_TYPE: "Unsupported media type",
        ErrorCategory.REQUEST_VALIDATION: "Request validation failed",
        ErrorCategory.UPSTREAM_FAILURE: "Upstream service failed",
        ErrorCategory.SERVICE_UNAVAILABLE: "Service unavailable",
        ErrorCategory.UPSTREAM_TIMEOUT: "Upstream service timed out",
        ErrorCategory.INTERNAL: "Internal server error",
    }
)

COMMON_ERROR_CATEGORIES: Final[tuple[ErrorCategory, ...]] = (
    ErrorCategory.INVALID_INPUT,
    ErrorCategory.AUTHENTICATION,
    ErrorCategory.NOT_FOUND,
    ErrorCategory.CONFLICT,
    ErrorCategory.REQUEST_VALIDATION,
    ErrorCategory.SERVICE_UNAVAILABLE,
    ErrorCategory.INTERNAL,
)


def problem_from_error(error: NoraError) -> ApiProblem:
    """Build a public problem while failing internal sentinels closed."""

    category = ERROR_CATEGORY_BY_CODE[error.error_code]
    if category is ErrorCategory.INTERNAL:
        return internal_problem()
    return ApiProblem(
        error_code=error.error_code,
        error_category=category,
        message=error.message,
    )


def internal_problem() -> ApiProblem:
    return ApiProblem(
        error_code=ErrorCode.INTERNAL_ERROR,
        error_category=ErrorCategory.INTERNAL,
        message="Internal server error",
    )


def database_problem() -> ApiProblem:
    return ApiProblem(
        error_code=ErrorCode.DATABASE_UNAVAILABLE,
        error_category=ErrorCategory.SERVICE_UNAVAILABLE,
        message="Database is unavailable",
    )


def validation_problem() -> ApiProblem:
    return ApiProblem(
        error_code=ErrorCode.VALIDATION_ERROR,
        error_category=ErrorCategory.REQUEST_VALIDATION,
        message="Request validation failed",
    )


def problem_responses(
    *extra_categories: ErrorCategory,
    categories: tuple[ErrorCategory, ...] = COMMON_ERROR_CATEGORIES,
) -> dict[int | str, dict[str, Any]]:
    """Return deduplicated OpenAPI response declarations for a router."""

    selected = dict.fromkeys((*categories, *extra_categories))
    return {
        HTTP_STATUS_BY_CATEGORY[category]: {
            "model": ApiProblem,
            "description": _DESCRIPTION_BY_CATEGORY[category],
        }
        for category in selected
    }


__all__ = (
    "ApiProblem",
    "COMMON_ERROR_CATEGORIES",
    "HTTP_STATUS_BY_CATEGORY",
    "database_problem",
    "internal_problem",
    "problem_from_error",
    "problem_responses",
    "validation_problem",
)
