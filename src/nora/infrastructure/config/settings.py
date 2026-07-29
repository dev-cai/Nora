"""从环境变量或 .env 文件加载应用配置。"""

from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """支持的运行环境。"""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    """应用配置；同名环境变量优先于 .env 文件。"""

    env: Environment = Environment.DEV
    debug: bool = False
    log_level: str = "INFO"
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程内复用的配置实例。"""

    return Settings()
