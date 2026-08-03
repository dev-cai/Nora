"""Opportunity ORM 模型和 Repository 适配器。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base.exceptions import InfrastructureError
from app.domain.opportunity import JobPosting, JobPostingStatus, JobSourceType
from app.infrastructure.database.base import AuditMixin, Base, OwnedByUserMixin
from app.infrastructure.database.repository import SqlAlchemyUserScopedRepository
from app.ports.opportunity import StoredIdempotentJobPosting


class JobPostingRecord(Base, AuditMixin, OwnedByUserMixin):
    """岗位快照持久化记录。"""

    __tablename__ = "job_postings"
    __table_args__ = (
        CheckConstraint("length(trim(jd_text)) > 0", name="ck_job_postings_jd_text_nonempty"),
        CheckConstraint("length(jd_text) <= 100000", name="ck_job_postings_jd_text_max_length"),
        CheckConstraint("source_type IN ('manual', 'url')", name="ck_job_postings_source_type"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_job_postings_status"),
        CheckConstraint("length(trim(job_title)) > 0", name="ck_job_postings_job_title_nonempty"),
        CheckConstraint(
            "length(trim(company_name)) > 0", name="ck_job_postings_company_name_nonempty"
        ),
        CheckConstraint("length(trim(location)) > 0", name="ck_job_postings_location_nonempty"),
    )

    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text_summary: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class JobPostingIdempotencyRecord(Base, AuditMixin, OwnedByUserMixin):
    """用户范围内岗位创建请求的持久化幂等记录。"""

    __tablename__ = "job_posting_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_job_posting_idempotency_owner_key",
        ),
        UniqueConstraint("job_posting_id", name="uq_job_posting_idempotency_posting"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    job_posting_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )


class SqlAlchemyJobPostingRepository:
    """基于当前用户范围持久化岗位快照。"""

    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self._records = SqlAlchemyUserScopedRepository(session, JobPostingRecord, owner_id)

    @staticmethod
    def _to_domain(record: JobPostingRecord) -> JobPosting:
        return JobPosting(
            id=record.id,
            owner_id=record.owner_id,
            jd_text=record.jd_text,
            job_title=record.job_title,
            company_name=record.company_name,
            location=record.location,
            source_type=JobSourceType(record.source_type),
            source_url=record.source_url,
            imported_at=_as_utc(record.imported_at),
            text_summary=record.text_summary,
            status=JobPostingStatus(record.status),
            version=record.version,
            created_at=_as_utc(record.created_at),
        )

    async def add(self, job_posting: JobPosting) -> JobPosting:
        if job_posting.owner_id != self.owner_id:
            raise InfrastructureError(
                "Job posting is outside user scope", error_code="entity_not_found"
            )
        record = JobPostingRecord(
            id=job_posting.id,
            owner_id=job_posting.owner_id,
            jd_text=job_posting.jd_text,
            job_title=job_posting.job_title,
            company_name=job_posting.company_name,
            location=job_posting.location,
            source_type=job_posting.source_type.value,
            source_url=job_posting.source_url,
            imported_at=job_posting.imported_at,
            text_summary=job_posting.text_summary,
            status=job_posting.status.value,
            created_at=job_posting.created_at,
            updated_at=job_posting.created_at,
        )
        await self._records.add(record)
        return self._to_domain(record)

    async def add_idempotent(
        self,
        job_posting: JobPosting,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JobPosting:
        stored = await self.add(job_posting)
        self.session.add(
            JobPostingIdempotencyRecord(
                owner_id=self.owner_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                job_posting_id=stored.id,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Idempotency key is already in use",
                error_code="idempotency_key_taken",
            ) from exc
        return stored

    async def get_by_id(self, job_posting_id: UUID) -> JobPosting | None:
        record = await self._records.get(job_posting_id)
        return None if record is None else self._to_domain(record)

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> StoredIdempotentJobPosting | None:
        row = (
            await self.session.execute(
                select(JobPostingRecord, JobPostingIdempotencyRecord.request_fingerprint)
                .join(
                    JobPostingIdempotencyRecord,
                    JobPostingIdempotencyRecord.job_posting_id == JobPostingRecord.id,
                )
                .where(
                    JobPostingRecord.owner_id == self.owner_id,
                    JobPostingIdempotencyRecord.owner_id == self.owner_id,
                    JobPostingIdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        record, request_fingerprint = row
        return StoredIdempotentJobPosting(
            job_posting=self._to_domain(record),
            request_fingerprint=request_fingerprint,
        )

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[JobPosting]:
        records = await self.session.scalars(
            select(JobPostingRecord)
            .where(JobPostingRecord.owner_id == self.owner_id)
            .order_by(JobPostingRecord.created_at.desc(), JobPostingRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [self._to_domain(record) for record in records]

    async def count(self) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(JobPostingRecord)
            .where(JobPostingRecord.owner_id == self.owner_id)
        )
        return int(total or 0)

    async def commit(self) -> None:
        await self.session.commit()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
