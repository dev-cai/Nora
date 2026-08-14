import pytest
from app.domain.base.exceptions import (
    ApplicationError,
    DomainError,
    ErrorCode,
    InfrastructureError,
    NoraError,
)


def test_nora_error_serializes_stable_shape() -> None:
    error = NoraError("invalid input", error_code=ErrorCode.INVALID_JD_TEXT)

    assert error.to_dict() == {
        "error_code": ErrorCode.INVALID_JD_TEXT,
        "message": "invalid input",
    }


def test_nora_error_rejects_untyped_error_codes() -> None:
    with pytest.raises(TypeError, match="error_code must be an ErrorCode"):
        NoraError("invalid input", error_code="invalid_jd_text")  # type: ignore[arg-type]


def test_subclasses_have_stable_default_codes() -> None:
    assert DomainError("bad rule").error_code == ErrorCode.DOMAIN_ERROR
    assert ApplicationError("failed use case").error_code == ErrorCode.APPLICATION_ERROR
    assert InfrastructureError("database unavailable").error_code == ErrorCode.INFRASTRUCTURE_ERROR


def test_subclasses_extend_nora_error() -> None:
    assert issubclass(DomainError, NoraError)
    assert issubclass(ApplicationError, NoraError)
    assert issubclass(InfrastructureError, NoraError)
