"""从环境变量或 .env 文件加载应用配置。"""

import re
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DEFAULT_AUTH_SECRET_KEY = "development-only-change-this-secret"
DEFAULT_AUTH_RATE_LIMIT_SECRET = "development-rate-limit-secret-change-me"
KID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
PRIVATE_IPV4_INGRESS_NETWORKS = tuple(
    IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
PRIVATE_IPV6_INGRESS_NETWORK = IPv6Network("fc00::/7")


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
    database_url: str | None = Field(default=None, repr=False)
    database_url_file: Path | None = Field(default=None, repr=False)
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: float = 30.0
    auth_secret_key: str = Field(default=DEFAULT_AUTH_SECRET_KEY, min_length=32, repr=False)
    auth_access_token_minutes: int = Field(default=30, ge=1, le=30)
    auth_key_ring_directory: Path | None = None
    auth_active_kid: str = "dev"
    auth_rate_limit_secret: str = Field(
        default=DEFAULT_AUTH_RATE_LIMIT_SECRET, min_length=32, repr=False
    )
    auth_rate_limit_secret_file: Path | None = Field(default=None, repr=False)
    public_origin: str | None = None
    trusted_proxy_cidr: str | None = None
    baidu_ocr_api_key: str = ""
    baidu_ocr_secret_key: str = ""
    baidu_ocr_endpoint: str = "accurate_basic"
    deepseek_api_key: str = Field(default="", repr=False)
    deepseek_api_key_file: Path | None = Field(default=None, repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=128)
    deepseek_chat_timeout_seconds: float = Field(default=30.0, gt=0, le=60)
    deepseek_chat_input_price_cny_per_million_tokens: Decimal = Field(
        default=Decimal("12"), ge=Decimal("12")
    )
    deepseek_chat_output_price_cny_per_million_tokens: Decimal = Field(
        default=Decimal("36"), ge=Decimal("36")
    )
    deepseek_chat_request_budget_cny: Decimal = Field(
        default=Decimal("0.50"), gt=0, le=Decimal("0.50")
    )
    artifact_storage_endpoint: str = "storage:9000"
    artifact_storage_access_key: str = Field(default="nora-app", repr=False)
    artifact_storage_access_key_file: Path | None = Field(default=None, repr=False)
    artifact_storage_secret_key: str = Field(
        default="development-artifact-secret", min_length=16, repr=False
    )
    artifact_storage_secret_key_file: Path | None = Field(default=None, repr=False)
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

    @model_validator(mode="before")
    @classmethod
    def load_secret_files(cls, values: Any) -> Any:
        """Resolve supported ``*_FILE`` settings without exposing values to Compose."""

        if not isinstance(values, dict):
            return values
        resolved = dict(values)
        for value_name in (
            "database_url",
            "auth_rate_limit_secret",
            "artifact_storage_access_key",
            "artifact_storage_secret_key",
            "deepseek_api_key",
        ):
            file_name = f"{value_name}_file"
            path_value = resolved.get(file_name)
            if path_value is None:
                continue
            if value_name in resolved:
                raise ValueError(
                    f"{value_name.upper()} and {file_name.upper()} are mutually exclusive"
                )
            resolved[value_name] = _read_secret_file(Path(path_value), file_name.upper())
        return resolved

    @model_validator(mode="after")
    def validate_environment_contracts(self) -> Self:
        """验证数据库驱动和非开发环境的认证密钥。"""

        if self.database_url is not None:
            require_postgresql_database_url(self.database_url)

        if (
            self.env is not Environment.DEV
            and self.auth_key_ring_directory is None
            and self.auth_secret_key == DEFAULT_AUTH_SECRET_KEY
        ):
            raise ValueError("AUTH_SECRET_KEY must be changed outside the dev environment")
        if KID_PATTERN.fullmatch(self.auth_active_kid) is None:
            raise ValueError("AUTH_ACTIVE_KID must match [A-Za-z0-9._-]{1,64}")
        if self.env is Environment.PROD:
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required in prod")
            if self.auth_rate_limit_secret == DEFAULT_AUTH_RATE_LIMIT_SECRET:
                raise ValueError("AUTH_RATE_LIMIT_SECRET must be changed in prod")
            if self.auth_key_ring_directory is None:
                raise ValueError("AUTH_KEY_RING_DIRECTORY is required in prod")
            ring = self.jwt_key_ring
            if self.auth_active_kid not in ring:
                raise ValueError("AUTH_ACTIVE_KID must identify a configured JWT key")
            if self.auth_rate_limit_secret in set(ring.values()):
                raise ValueError("AUTH_RATE_LIMIT_SECRET must be separate from JWT keys")
            self._validate_public_origin()
            self._validate_trusted_proxy()
        if "://" in self.artifact_storage_endpoint or "/" in self.artifact_storage_endpoint:
            raise ValueError("ARTIFACT_STORAGE_ENDPOINT must be host:port without scheme or path")
        bucket = self.artifact_storage_bucket
        if not (3 <= len(bucket) <= 63) or bucket.lower() != bucket or ".." in bucket:
            raise ValueError(
                "ARTIFACT_STORAGE_BUCKET must be a valid lowercase private bucket name"
            )
        if not self.allowed_artifact_content_types:
            raise ValueError("ARTIFACT_ALLOWED_CONTENT_TYPES must not be empty")
        if self.deepseek_api_key and (
            self.deepseek_api_key != self.deepseek_api_key.strip()
            or any(character.isspace() for character in self.deepseek_api_key)
            or len(self.deepseek_api_key) > 4096
        ):
            raise ValueError("DEEPSEEK_API_KEY must be a bounded value without whitespace")
        if self.deepseek_base_url != "https://api.deepseek.com":
            raise ValueError("DEEPSEEK_BASE_URL is fixed to https://api.deepseek.com")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.deepseek_chat_model) is None:
            raise ValueError("DEEPSEEK_CHAT_MODEL must be a stable model identifier")
        return self

    def _validate_public_origin(self) -> None:
        value = self.public_origin or ""
        try:
            parsed = urlsplit(value)
            parsed.port
        except ValueError as exc:
            raise ValueError("PUBLIC_ORIGIN must be one exact HTTPS origin without path") from exc
        if (
            value in {"*", "null"}
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != ""
            or parsed.query
            or parsed.fragment
            or "*" in parsed.hostname
            or any(char.isspace() for char in value)
        ):
            raise ValueError("PUBLIC_ORIGIN must be one exact HTTPS origin without path")

    def _validate_trusted_proxy(self) -> None:
        if self.trusted_proxy_cidr is None:
            raise ValueError("TRUSTED_PROXY_CIDR is required in prod")
        try:
            network = ip_network(self.trusted_proxy_cidr, strict=False)
        except ValueError as exc:
            raise ValueError("TRUSTED_PROXY_CIDR must be a valid private network") from exc
        allowed = (
            any(network.subnet_of(item) for item in PRIVATE_IPV4_INGRESS_NETWORKS)
            if isinstance(network, IPv4Network)
            else network.subnet_of(PRIVATE_IPV6_INGRESS_NETWORK)
        )
        if not allowed:
            raise ValueError("TRUSTED_PROXY_CIDR must be private")

    @property
    def jwt_key_ring(self) -> dict[str, str]:
        """Load a fixed allowlist; token headers never select file paths."""

        if self.auth_key_ring_directory is None:
            return {self.auth_active_kid: self.auth_secret_key}
        directory = self.auth_key_ring_directory
        if not directory.is_dir():
            raise ValueError("AUTH_KEY_RING_DIRECTORY must be a readable directory")
        ring: dict[str, str] = {}
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or KID_PATTERN.fullmatch(path.name) is None:
                raise ValueError("JWT key filenames must be valid kid values")
            secret = path.read_text(encoding="utf-8").rstrip("\r\n")
            if len(secret.encode("utf-8")) < 32:
                raise ValueError("JWT keys must contain at least 32 bytes")
            ring[path.name] = secret
        if not ring:
            raise ValueError("JWT key ring must contain at least one key")
        return ring

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


def _read_secret_file(path: Path, setting_name: str) -> str:
    """Read one small, non-symlink Secret file with private permissions."""

    if not path.is_absolute():
        raise ValueError(f"{setting_name} must be an absolute path")
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ValueError(f"{setting_name} must identify a readable Secret file") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{setting_name} must identify a regular non-symlink Secret file")
    if stat.st_mode & 0o027:
        raise ValueError(f"{setting_name} must not be group-writable or accessible by others")
    if stat.st_size < 1 or stat.st_size > 16 * 1024:
        raise ValueError(f"{setting_name} must contain 1-16384 bytes")
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{setting_name} must identify a readable UTF-8 Secret file") from exc
    if not value or "\x00" in value:
        raise ValueError(f"{setting_name} must contain a non-empty text value")
    return value
