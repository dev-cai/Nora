"""ImportSession/ImportDraft PostgreSQL Adapter。"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.imports import (
    ImportDraft,
    ImportSession,
    ImportSessionStatus,
    ImportSourceType,
    ImportType,
)
from app.infrastructure.database.base import Base
from app.ports.imports import ImportRepository


class ImportSessionRecord(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (
        CheckConstraint("import_type IN ('jd')", name="ck_import_sessions_type"),
        CheckConstraint(
            "source_type IN ('text', 'image', 'url')", name="ck_import_sessions_source_type"
        ),
        CheckConstraint(
            "status IN ('created', 'draft_ready', 'failed', 'confirmed')",
            name="ck_import_sessions_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    import_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_draft_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_job_posting_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_requirement_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportDraftRecord(Base):
    __tablename__ = "import_drafts"
    __table_args__ = (
        CheckConstraint("import_type IN ('jd')", name="ck_import_drafts_type"),
        CheckConstraint("version >= 1", name="ck_import_drafts_version"),
        CheckConstraint("length(content_fingerprint) = 64", name="ck_import_drafts_fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_sessions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    import_type: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyImportRepository(ImportRepository):
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add_session(self, value: ImportSession) -> ImportSession:
        self._check_owner(value.owner_id)
        self.session.add(_session_record(value))
        await self.session.flush()
        return value

    async def update_session(self, value: ImportSession) -> ImportSession:
        self._check_owner(value.owner_id)
        record = await self._session(value.id)
        if record is None:
            raise InfrastructureError(
                "Import session not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        _copy_session(record, value)
        await self.session.flush()
        return value

    async def get_session(self, session_id: UUID) -> ImportSession | None:
        return _to_session(await self._session(session_id))

    async def add_draft(self, value: ImportDraft) -> ImportDraft:
        self._check_owner(value.owner_id)
        self.session.add(_draft_record(value))
        await self.session.flush()
        return value

    async def update_draft(self, value: ImportDraft) -> ImportDraft:
        self._check_owner(value.owner_id)
        record = await self.session.scalar(
            select(ImportDraftRecord).where(
                ImportDraftRecord.id == value.id,
                ImportDraftRecord.owner_id == self.owner_id,
            )
        )
        if record is None:
            raise InfrastructureError(
                "Import draft not found", error_code=ErrorCode.ENTITY_NOT_FOUND
            )
        record.version = value.version
        record.content = value.content
        record.content_fingerprint = value.content_fingerprint
        record.updated_at = value.updated_at
        await self.session.flush()
        return value

    async def get_draft(self, draft_id: UUID) -> ImportDraft | None:
        record = await self.session.scalar(
            select(ImportDraftRecord).where(
                ImportDraftRecord.id == draft_id,
                ImportDraftRecord.owner_id == self.owner_id,
            )
        )
        return _to_draft(record)

    async def _session(self, session_id: UUID) -> ImportSessionRecord | None:
        return await self.session.scalar(
            select(ImportSessionRecord).where(
                ImportSessionRecord.id == session_id,
                ImportSessionRecord.owner_id == self.owner_id,
            )
        )

    def _check_owner(self, owner_id: UUID) -> None:
        if owner_id != self.owner_id:
            raise InfrastructureError(
                "Import object is outside user scope", error_code=ErrorCode.ENTITY_NOT_FOUND
            )


def _session_record(value: ImportSession) -> ImportSessionRecord:
    return ImportSessionRecord(
        id=value.id,
        owner_id=value.owner_id,
        import_type=value.import_type.value,
        source_type=value.source_type.value,
        source_url=value.source_url,
        status=value.status.value,
        current_draft_id=value.current_draft_id,
        confirmed_job_posting_id=value.confirmed_job_posting_id,
        confirmed_requirement_snapshot_id=value.confirmed_requirement_snapshot_id,
        failure_code=value.failure_code.value if value.failure_code else None,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _copy_session(record: ImportSessionRecord, value: ImportSession) -> None:
    record.status = value.status.value
    record.current_draft_id = value.current_draft_id
    record.confirmed_job_posting_id = value.confirmed_job_posting_id
    record.confirmed_requirement_snapshot_id = value.confirmed_requirement_snapshot_id
    record.failure_code = value.failure_code.value if value.failure_code else None
    record.updated_at = value.updated_at


def _draft_record(value: ImportDraft) -> ImportDraftRecord:
    return ImportDraftRecord(
        id=value.id,
        session_id=value.session_id,
        owner_id=value.owner_id,
        import_type=value.import_type.value,
        version=value.version,
        content=value.content,
        content_fingerprint=value.content_fingerprint,
        prompt_version=value.prompt_version,
        model_version=value.model_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _to_session(record: ImportSessionRecord | None) -> ImportSession | None:
    if record is None:
        return None
    return ImportSession(
        id=record.id,
        owner_id=record.owner_id,
        import_type=ImportType(record.import_type),
        source_type=ImportSourceType(record.source_type),
        source_url=record.source_url,
        status=ImportSessionStatus(record.status),
        current_draft_id=record.current_draft_id,
        confirmed_job_posting_id=record.confirmed_job_posting_id,
        confirmed_requirement_snapshot_id=record.confirmed_requirement_snapshot_id,
        failure_code=ErrorCode(record.failure_code) if record.failure_code else None,
        created_at=_utc(record.created_at),
        updated_at=_utc(record.updated_at),
    )


def _to_draft(record: ImportDraftRecord | None) -> ImportDraft | None:
    if record is None:
        return None
    return ImportDraft(
        id=record.id,
        session_id=record.session_id,
        owner_id=record.owner_id,
        import_type=ImportType(record.import_type),
        version=record.version,
        content=record.content,
        content_fingerprint=record.content_fingerprint,
        prompt_version=record.prompt_version,
        model_version=record.model_version,
        created_at=_utc(record.created_at),
        updated_at=_utc(record.updated_at),
    )


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


__all__ = (
    "ImportDraftRecord",
    "ImportSessionRecord",
    "SqlAlchemyImportRepository",
)
