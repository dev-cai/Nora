"""从环境变量或 .env 文件加载应用配置。"""

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DEFAULT_AUTH_SECRET_KEY = "development-only-change-this-secret"


def require_postgresql_database_url(value: str) -> str:
    """只接受 Nora 运行时支持的 PostgreSQL 异步连接。"""

    try:
        driver_name = make_url(value).drivername
    except Exception as exc:
        raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from exc
    if driver_name != "postgresql+asyncpg":
        raise ValueError("DATABASE_URL must use postgresql+asyncpg")
    return value


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
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""
    baidu_ocr_endpoint: str = "accurate_basic"
    artifact_storage_endpoint: str = "storage:9000"
    artifact_storage_access_key: str = "nora-app"
    artifact_storage_secret_key: str = Field(default="development-artifact-secret", min_length=16)
    artifact_storage_bucket: str = "nora-artifacts"
    artifact_storage_secure: bool = False
    artifact_max_size_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    artifact_allowed_content_types: str = (
        "image/png,image/jpeg,application/pdf,text/plain,text/html"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_environment_contracts(self) -> Self:
        """验证数据库驱动和非开发环境的认证密钥。"""

        if self.database_url is not None:
            require_postgresql_database_url(self.database_url)

        if self.env is not Environment.DEV and self.auth_secret_key == DEFAULT_AUTH_SECRET_KEY:
            raise ValueError("AUTH_SECRET_KEY must be changed outside the dev environment")
        if "://" in self.artifact_storage_endpoint or "/" in self.artifact_storage_endpoint:
            raise ValueError("ARTIFACT_STORAGE_ENDPOINT must be host:port without scheme or path")
        bucket = self.artifact_storage_bucket
        if not (3 <= len(bucket) <= 63) or bucket.lower() != bucket or ".." in bucket:
            raise ValueError(
                "ARTIFACT_STORAGE_BUCKET must be a valid lowercase private bucket name"
            )
        if not self.allowed_artifact_content_types:
            raise ValueError("ARTIFACT_ALLOWED_CONTENT_TYPES must not be empty")
        return self

    @property
    def allowed_artifact_content_types(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower()
            for item in self.artifact_allowed_content_types.split(",")
            if item.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
