"""Nora 领域异常及稳定错误码。"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """系统边界使用的稳定错误码。"""

    NORA_ERROR = "nora_error"
    DOMAIN_ERROR = "domain_error"
    APPLICATION_ERROR = "application_error"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class NoraError(Exception):
    """所有可预期 Nora 错误的基类。"""

    default_error_code = ErrorCode.NORA_ERROR

    def __init__(self, message: str, error_code: str | ErrorCode | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = str(error_code or self.default_error_code)

    def to_dict(self) -> dict[str, Any]:
        """返回可直接用于 API 错误响应的稳定结构。"""

        return {"error_code": self.error_code, "message": self.message}


class DomainError(NoraError):
    """领域规则或领域状态不满足时抛出的错误。"""

    default_error_code = ErrorCode.DOMAIN_ERROR


class ApplicationError(NoraError):
    """应用用例无法完成时抛出的错误。"""

    default_error_code = ErrorCode.APPLICATION_ERROR


class InfrastructureError(NoraError):
    """基础设施适配器失败时抛出的错误。"""

    default_error_code = ErrorCode.INFRASTRUCTURE_ERROR
