"""不可变岗位快照及其领域规则。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError, ErrorCode

MAX_JD_TEXT_LENGTH = 100_000
MAX_METADATA_LENGTH = 200
MAX_SOURCE_URL_LENGTH = 2_048
SUMMARY_MAX_LENGTH = 240
UNKNOWN_JOB_TITLE = "未提供职位"
UNKNOWN_COMPANY_NAME = "未提供公司"
UNKNOWN_LOCATION = "未提供地点"


class JobPostingStatus(StrEnum):
    """岗位快照状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class JobSourceType(StrEnum):
    """当前支持的岗位来源类型。"""

    MANUAL = "manual"
    URL = "url"


@dataclass(frozen=True, slots=True)
class JobPosting:
    """用户归属的不可变岗位正文快照。"""

    id: UUID
    owner_id: UUID
    jd_text: str
    job_title: str
    company_name: str
    location: str
    source_type: JobSourceType
    source_url: str | None
    imported_at: datetime
    text_summary: str
    status: JobPostingStatus
    version: int
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        owner_id: UUID,
        jd_text: str,
        job_title: str | None = None,
        company_name: str | None = None,
        location: str | None = None,
        source_type: JobSourceType = JobSourceType.MANUAL,
        source_url: str | None = None,
        now: datetime | None = None,
    ) -> "JobPosting":
        """规范化输入并创建 active 岗位快照。"""

        normalized_text = _normalize_jd_text(jd_text)
        normalized_source_url = _normalize_source_url(source_url)
        if not isinstance(source_type, JobSourceType):
            raise DomainError(
                "Job source type is invalid", error_code=ErrorCode.INVALID_SOURCE_TYPE
            )
        if source_type is JobSourceType.URL and normalized_source_url is None:
            raise DomainError(
                "URL source requires source_url", error_code=ErrorCode.INVALID_SOURCE_URL
            )

        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise DomainError(
                "Timestamp must include a timezone", error_code=ErrorCode.INVALID_TIMESTAMP
            )
        timestamp = timestamp.astimezone(timezone.utc)

        return cls(
            id=uuid4(),
            owner_id=owner_id,
            jd_text=normalized_text,
            job_title=_normalize_metadata(
                job_title, ErrorCode.INVALID_JOB_TITLE, UNKNOWN_JOB_TITLE
            ),
            company_name=_normalize_metadata(
                company_name, ErrorCode.INVALID_COMPANY_NAME, UNKNOWN_COMPANY_NAME
            ),
            location=_normalize_metadata(location, ErrorCode.INVALID_LOCATION, UNKNOWN_LOCATION),
            source_type=source_type,
            source_url=normalized_source_url,
            imported_at=timestamp,
            text_summary=_summarize(normalized_text),
            status=JobPostingStatus.ACTIVE,
            version=1,
            created_at=timestamp,
        )


def _normalize_jd_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DomainError("JD text cannot be blank", error_code=ErrorCode.INVALID_JD_TEXT)
    if len(normalized) > MAX_JD_TEXT_LENGTH:
        raise DomainError(
            f"JD text cannot exceed {MAX_JD_TEXT_LENGTH} characters",
            error_code=ErrorCode.JD_TEXT_TOO_LONG,
        )
    return normalized


def _normalize_metadata(value: str | None, error_code: ErrorCode, fallback: str) -> str:
    if value is None:
        return fallback
    normalized = " ".join(value.split())
    if not normalized:
        raise DomainError("Metadata cannot be blank", error_code=error_code)
    if len(normalized) > MAX_METADATA_LENGTH:
        raise DomainError(
            f"Metadata cannot exceed {MAX_METADATA_LENGTH} characters",
            error_code=error_code,
        )
    return normalized


def _normalize_source_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_SOURCE_URL_LENGTH or any(char.isspace() for char in normalized):
        raise DomainError("Source URL is invalid", error_code=ErrorCode.INVALID_SOURCE_URL)
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
    except ValueError as exc:
        raise DomainError("Source URL is invalid", error_code=ErrorCode.INVALID_SOURCE_URL) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DomainError("Source URL is invalid", error_code=ErrorCode.INVALID_SOURCE_URL)
    return normalized


def _summarize(jd_text: str) -> str:
    collapsed = " ".join(jd_text.split())
    if len(collapsed) <= SUMMARY_MAX_LENGTH:
        return collapsed
    return f"{collapsed[: SUMMARY_MAX_LENGTH - 3].rstrip()}..."
