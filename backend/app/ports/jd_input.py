"""JD 图片 OCR 与受控链接抓取的 provider-neutral 契约。"""

from dataclasses import dataclass, field
from enum import StrEnum
from ipaddress import ip_address
from re import fullmatch
from typing import Protocol, Sequence, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from app.domain.base.exceptions import NoraError

MAX_JD_IMAGE_BYTES = 10 * 1024 * 1024
MAX_JD_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_JD_TEXT_LENGTH = 100_000
ALLOWED_JD_IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png"})

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_FORBIDDEN_HOST_SUFFIXES = (".home.arpa", ".internal", ".local", ".localhost")


class JdInputKind(StrEnum):
    """产生 JD 文本的输入方式。"""

    IMAGE = "image"
    URL = "url"


class JdInputErrorCode(StrEnum):
    """跨 API、应用层与 Adapter 保持稳定的失败分类。"""

    UNSUPPORTED_IMAGE = "unsupported_image"
    IMAGE_TOO_LARGE = "image_too_large"
    INVALID_URL = "invalid_url"
    UNSAFE_URL = "unsafe_url"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    RESPONSE_TOO_LARGE = "response_too_large"
    FETCH_TIMEOUT = "fetch_timeout"
    FETCH_FAILED = "fetch_failed"
    OCR_FAILED = "ocr_failed"
    EMPTY_CONTENT = "empty_content"
    CONTENT_TOO_LARGE = "content_too_large"
    INVALID_INPUT_KIND = "invalid_input_kind"


class JdInputError(NoraError):
    """JD 输入在校验、OCR 或抓取边界上的可预期失败。"""

    def __init__(self, message: str, error_code: JdInputErrorCode) -> None:
        super().__init__(message, error_code=error_code)


@dataclass(frozen=True, slots=True)
class JdImageInput:
    """交给 OCR Adapter 前已完成基础格式校验的图片。"""

    content: bytes
    media_type: str

    def __post_init__(self) -> None:
        media_type = self.media_type.strip().lower()
        object.__setattr__(self, "media_type", media_type)
        if len(self.content) > MAX_JD_IMAGE_BYTES:
            raise JdInputError(
                "JD image exceeds the 10 MiB limit",
                JdInputErrorCode.IMAGE_TOO_LARGE,
            )
        if media_type not in ALLOWED_JD_IMAGE_MEDIA_TYPES or not _matches_media_type(
            self.content, media_type
        ):
            raise JdInputError(
                "JD image must be a non-empty PNG or JPEG with matching content",
                JdInputErrorCode.UNSUPPORTED_IMAGE,
            )


@dataclass(frozen=True, slots=True)
class JdUrlFetchPolicy:
    """所有 URL 抓取 Adapter 必须执行的固定资源与 SSRF 边界。"""

    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    max_redirects: int = 3
    max_response_bytes: int = MAX_JD_RESPONSE_BYTES
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        allowed_schemes = frozenset(self.allowed_schemes)
        object.__setattr__(self, "allowed_schemes", allowed_schemes)
        if not allowed_schemes or not allowed_schemes <= {"http", "https"}:
            raise ValueError("allowed_schemes can only contain http and https")
        if not 0 <= self.max_redirects <= 3:
            raise ValueError("max_redirects must be between 0 and 3")
        if not 0 < self.max_response_bytes <= MAX_JD_RESPONSE_BYTES:
            raise ValueError("max_response_bytes cannot exceed the JD response limit")
        if not 0 < self.connect_timeout_seconds <= 5.0:
            raise ValueError("connect_timeout_seconds must be between 0 and 5")
        if not 0 < self.read_timeout_seconds <= 10.0:
            raise ValueError("read_timeout_seconds must be between 0 and 10")

    def ensure_redirect_count(self, redirect_count: int) -> None:
        if redirect_count < 0 or redirect_count > self.max_redirects:
            raise JdInputError(
                "JD URL exceeded the redirect limit",
                JdInputErrorCode.TOO_MANY_REDIRECTS,
            )

    def ensure_response_size(self, response_bytes: int) -> None:
        if response_bytes < 0 or response_bytes > self.max_response_bytes:
            raise JdInputError(
                "JD URL response exceeds the size limit",
                JdInputErrorCode.RESPONSE_TOO_LARGE,
            )

    def ensure_public_addresses(self, addresses: Sequence[str]) -> None:
        if not addresses:
            raise JdInputError(
                "JD URL host did not resolve to an address",
                JdInputErrorCode.FETCH_FAILED,
            )
        for value in addresses:
            try:
                address = ip_address(value)
            except ValueError as exc:
                raise JdInputError(
                    "JD URL host resolved to an invalid address",
                    JdInputErrorCode.FETCH_FAILED,
                ) from exc
            if not address.is_global:
                raise JdInputError(
                    "JD URL must resolve only to public addresses",
                    JdInputErrorCode.UNSAFE_URL,
                )


@dataclass(frozen=True, slots=True)
class JdUrlInput:
    """语法已校验、等待 Adapter 解析 DNS 并抓取的 URL。"""

    url: str
    policy: JdUrlFetchPolicy = field(default_factory=JdUrlFetchPolicy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", _validated_url(self.url, self.policy))


@dataclass(frozen=True, slots=True)
class JdInputResult:
    """OCR 或抓取成功后可进入既有 JobPosting 文本路径的结果。"""

    jd_text: str
    kind: JdInputKind
    source_url: str | None = None

    def __post_init__(self) -> None:
        try:
            kind = JdInputKind(self.kind)
        except ValueError as exc:
            raise JdInputError(
                "JD input result kind is invalid",
                JdInputErrorCode.INVALID_INPUT_KIND,
            ) from exc
        object.__setattr__(self, "kind", kind)
        normalized = "\n".join(line.rstrip() for line in self.jd_text.strip().splitlines())
        if not normalized:
            raise JdInputError("JD input produced no text", JdInputErrorCode.EMPTY_CONTENT)
        if len(normalized) > MAX_JD_TEXT_LENGTH:
            raise JdInputError(
                "JD input produced too much text",
                JdInputErrorCode.CONTENT_TOO_LARGE,
            )
        if kind is JdInputKind.URL:
            if not self.source_url:
                raise JdInputError(
                    "URL input result must retain its source URL",
                    JdInputErrorCode.INVALID_URL,
                )
            object.__setattr__(self, "source_url", JdUrlInput(self.source_url).url)
        if kind is JdInputKind.IMAGE and self.source_url is not None:
            raise JdInputError(
                "Image input result cannot declare a source URL",
                JdInputErrorCode.INVALID_URL,
            )
        object.__setattr__(self, "jd_text", normalized)


@runtime_checkable
class JdInputPort(Protocol):
    """M3.7 OCR 与受控抓取 Adapter 需要实现的稳定端口。"""

    async def extract_image(self, request: JdImageInput) -> JdInputResult: ...

    async def fetch_url(self, request: JdUrlInput) -> JdInputResult: ...


def _matches_media_type(content: bytes, media_type: str) -> bool:
    if media_type == "image/png":
        return content.startswith(_PNG_SIGNATURE)
    if media_type == "image/jpeg":
        return content.startswith(_JPEG_SIGNATURE)
    return False


def _validated_url(value: str, policy: JdUrlFetchPolicy) -> str:
    raw_url = value.strip()
    if not raw_url or len(raw_url) > 2_048:
        raise JdInputError("JD URL is empty or too long", JdInputErrorCode.INVALID_URL)
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise JdInputError("JD URL is malformed", JdInputErrorCode.INVALID_URL) from exc
    scheme = parsed.scheme.lower()
    if scheme not in policy.allowed_schemes or not parsed.hostname:
        raise JdInputError(
            "JD URL must use HTTP or HTTPS and include a host",
            JdInputErrorCode.INVALID_URL,
        )
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise JdInputError(
            "JD URL cannot contain credentials or a fragment",
            JdInputErrorCode.INVALID_URL,
        )
    raw_hostname = parsed.hostname.rstrip(".").lower()
    try:
        literal_address = ip_address(raw_hostname)
    except ValueError:
        literal_address = None
    hostname = literal_address.compressed if literal_address else _validated_hostname(raw_hostname)
    if literal_address is None:
        try:
            literal_address = ip_address(hostname)
        except ValueError:
            literal_address = None
        else:
            hostname = literal_address.compressed
    if literal_address is not None and not literal_address.is_global:
        raise JdInputError(
            "JD URL cannot target a non-public address",
            JdInputErrorCode.UNSAFE_URL,
        )
    default_port = 80 if scheme == "http" else 443
    host_part = f"[{hostname}]" if literal_address and literal_address.version == 6 else hostname
    netloc = host_part if port in (None, default_port) else f"{host_part}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def _validated_hostname(hostname: str) -> str:
    normalized = hostname.rstrip(".").lower()
    try:
        ascii_hostname = normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise JdInputError("JD URL host is malformed", JdInputErrorCode.INVALID_URL) from exc
    if ascii_hostname == "localhost" or ascii_hostname.endswith(_FORBIDDEN_HOST_SUFFIXES):
        raise JdInputError("JD URL host is not public", JdInputErrorCode.UNSAFE_URL)
    if len(ascii_hostname) > 253 or any(
        not fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in ascii_hostname.split(".")
    ):
        raise JdInputError("JD URL host is malformed", JdInputErrorCode.INVALID_URL)
    return ascii_hostname
