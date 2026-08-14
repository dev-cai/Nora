"""岗位快照创建、幂等重放与读取用例。"""

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from app.domain.base.exceptions import ApplicationError, ErrorCode, InfrastructureError
from app.domain.governance import AuditAction, AuditEvent
from app.domain.opportunity import JobPosting, JobSourceType
from app.ports.governance import AuditEventRepository
from app.ports.opportunity import JobPostingRepository
from app.ports.transaction import Transaction


@dataclass(frozen=True, slots=True)
class CreateJobPostingCommand:
    """创建岗位快照所需的认证用户输入。"""

    owner_id: UUID
    idempotency_key: str
    jd_text: str
    job_title: str | None = None
    company_name: str | None = None
    location: str | None = None
    source_type: JobSourceType = JobSourceType.MANUAL
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class CreateJobPostingResult:
    """创建结果及是否命中历史幂等结果。"""

    job_posting: JobPosting
    replayed: bool


@dataclass(frozen=True, slots=True)
class GetJobPostingQuery:
    """按认证用户范围读取岗位快照。"""

    owner_id: UUID
    job_posting_id: UUID


@dataclass(frozen=True, slots=True)
class ListJobPostingsQuery:
    """按认证用户范围分页读取岗位快照。"""

    owner_id: UUID
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class ListJobPostingsResult:
    """稳定分页的岗位快照及总数。"""

    items: tuple[JobPosting, ...]
    page: int
    page_size: int
    total: int


class CreateJobPostingUseCase:
    """创建一次岗位快照，或重放同键同内容的首次结果。"""

    def __init__(
        self,
        repository: JobPostingRepository,
        audit_repository: AuditEventRepository,
        transaction: Transaction,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.transaction = transaction

    async def execute(self, command: CreateJobPostingCommand) -> CreateJobPostingResult:
        idempotency_key = _normalize_idempotency_key(command.idempotency_key)
        posting = JobPosting.create(
            owner_id=command.owner_id,
            jd_text=command.jd_text,
            job_title=command.job_title,
            company_name=command.company_name,
            location=command.location,
            source_type=command.source_type,
            source_url=command.source_url,
        )
        request_fingerprint = _request_fingerprint(posting)

        existing = await self.repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return _resolve_replay(
                existing.job_posting,
                existing.request_fingerprint,
                request_fingerprint,
            )

        try:
            stored = await self.repository.add_idempotent(
                posting,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
            await self.audit_repository.add(
                AuditEvent.create(
                    actor_id=command.owner_id,
                    action=AuditAction.CREATE,
                    target_type="job_posting",
                    target_id=stored.id,
                    target_version=stored.version,
                    after_summary=_audit_summary(stored),
                    idempotency_key=idempotency_key,
                )
            )
            await self.transaction.commit()
        except InfrastructureError as exc:
            await self.transaction.rollback()
            if exc.error_code != "idempotency_key_taken":
                raise
            existing = await self.repository.get_by_idempotency_key(idempotency_key)
            if existing is None:
                raise InfrastructureError(
                    "Could not recover idempotent request",
                    error_code=ErrorCode.JOB_POSTING_PERSISTENCE_FAILED,
                ) from exc
            return _resolve_replay(
                existing.job_posting,
                existing.request_fingerprint,
                request_fingerprint,
            )
        except Exception:
            await self.transaction.rollback()
            raise

        return CreateJobPostingResult(job_posting=stored, replayed=False)


class GetJobPostingUseCase:
    """读取当前用户拥有的单条岗位快照。"""

    def __init__(self, repository: JobPostingRepository) -> None:
        self.repository = repository

    async def execute(self, query: GetJobPostingQuery) -> JobPosting:
        posting = await self.repository.get_by_id(query.job_posting_id)
        if posting is None or posting.owner_id != query.owner_id:
            raise ApplicationError("Job posting not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        return posting


class ListJobPostingsUseCase:
    """按创建时间倒序返回当前用户的岗位快照。"""

    def __init__(self, repository: JobPostingRepository) -> None:
        self.repository = repository

    async def execute(self, query: ListJobPostingsQuery) -> ListJobPostingsResult:
        if query.page < 1 or not 1 <= query.page_size <= 100:
            raise ApplicationError(
                "Page must be at least 1 and page_size must be between 1 and 100",
                error_code=ErrorCode.INVALID_PAGINATION,
            )
        offset = (query.page - 1) * query.page_size
        items = await self.repository.list(offset=offset, limit=query.page_size)
        total = await self.repository.count()
        return ListJobPostingsResult(
            items=tuple(items),
            page=query.page,
            page_size=query.page_size,
            total=total,
        )


def _normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 255:
        raise ApplicationError(
            "Idempotency key must contain 1-255 characters",
            error_code=ErrorCode.INVALID_IDEMPOTENCY_KEY,
        )
    return normalized


def _request_fingerprint(posting: JobPosting) -> str:
    content = {
        "company_name": posting.company_name,
        "jd_text": posting.jd_text,
        "job_title": posting.job_title,
        "location": posting.location,
        "source_type": posting.source_type.value,
        "source_url": posting.source_url,
    }
    serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _audit_summary(posting: JobPosting) -> str:
    """生成不复制完整 JD 的确定性审计摘要。"""

    content = {
        "source_type": posting.source_type.value,
        "status": posting.status.value,
    }
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _resolve_replay(
    posting: JobPosting,
    stored_fingerprint: str,
    request_fingerprint: str,
) -> CreateJobPostingResult:
    if stored_fingerprint != request_fingerprint:
        raise ApplicationError(
            "Idempotency key was already used with different content",
            error_code=ErrorCode.IDEMPOTENCY_CONFLICT,
        )
    return CreateJobPostingResult(job_posting=posting, replayed=True)
