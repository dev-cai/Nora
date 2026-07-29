"""从环境变量或 .env 文件加载应用配置。"""

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AUTH_SECRET_KEY = "development-only-change-this-secret"


class Environment(StrEnum):
    """支持的运行环境。"""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogFormat(StrEnum):
    """支持的日志输出格式。"""

    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """应用配置；同名环境变量优先于 .env 文件。"""

    env: Environment = Environment.DEV
    debug: bool = False
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    database_url: str | None = None
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: float = 30.0
    auth_secret_key: str = Field(default=DEFAULT_AUTH_SECRET_KEY, min_length=32)
    auth_access_token_minutes: int = Field(default=30, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def reject_default_auth_secret_outside_development(self) -> Self:
        """避免 staging/prod 意外使用仓库内公开的开发密钥。"""

        if self.env is not Environment.DEV and self.auth_secret_key == DEFAULT_AUTH_SECRET_KEY:
            raise ValueError("AUTH_SECRET_KEY must be changed outside the dev environment")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
