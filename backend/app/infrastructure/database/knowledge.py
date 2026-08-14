"""Artifact and SourceDocument PostgreSQL records and user-scoped repositories."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus, SourceDocument, SourceKind
from app.infrastructure.database.base import Base


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_artifact_owner_key"),
        UniqueConstraint("id", "version", "owner_id", name="uq_artifact_id_version_owner"),
        CheckConstraint("version >= 1", name="ck_artifact_version"),
        CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        CheckConstraint("length(sha256) = 64", name="ck_artifact_sha256"),
        CheckConstraint("kind IN ('source', 'generated')", name="ck_artifact_kind"),
        CheckConstraint(
            "(kind = 'generated' AND generator_version IS NOT NULL AND "
            "generation_identity IS NOT NULL) OR "
            "(kind = 'source' AND generator_version IS NULL AND generation_identity IS NULL)",
            name="ck_artifact_generation_identity",
        ),
        CheckConstraint(
            "status IN ('pending', 'available', 'failed', "
            "'delete_pending', 'delete_failed', 'deleted')",
            name="ck_artifact_status",
        ),
        CheckConstraint(
            "(status = 'deleted' AND object_key IS NULL AND deleted_at IS NOT NULL) OR "
            "(status <> 'deleted' AND deleted_at IS NULL)",
            name="ck_artifact_tombstone",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    generator_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceDocumentRecord(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint("id", "version", "owner_id", name="uq_source_id_version_owner"),
        CheckConstraint("version >= 1", name="ck_source_version"),
        CheckConstraint("source_kind IN ('file', 'web', 'manual')", name="ck_source_kind"),
        CheckConstraint("length(content_sha256) = 64", name="ck_source_sha256"),
        ForeignKeyConstraint(
            ["artifact_id", "artifact_version", "owner_id"],
            ["artifacts.id", "artifacts.version", "artifacts.owner_id"],
            name="fk_source_artifact_owner",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    acquisition_method: Mapped[str] = mapped_column(String(100), nullable=False)
    license_note: Mapped[str] = mapped_column(String(500), nullable=False)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyArtifactRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session, self.owner_id = session, owner_id

    @staticmethod
    def _to_domain(record: ArtifactRecord) -> Artifact:
        return Artifact(
            id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            kind=ArtifactKind(record.kind),
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            object_key=record.object_key,
            status=ArtifactStatus(record.status),
            idempotency_key=record.idempotency_key,
            generator_version=record.generator_version,
            generation_identity=record.generation_identity,
            created_at=_utc(record.created_at),
            deleted_at=_utc(record.deleted_at) if record.deleted_at else None,
        )

    async def get_by_id(self, artifact_id: UUID) -> Artifact | None:
        record = await self.session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.id == artifact_id, ArtifactRecord.owner_id == self.owner_id
            )
        )
        return self._to_domain(record) if record else None

    async def get_by_idempotency_key(self, key: str) -> Artifact | None:
        record = await self.session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.owner_id == self.owner_id, ArtifactRecord.idempotency_key == key
            )
        )
        return self._to_domain(record) if record else None

    async def add(self, artifact: Artifact) -> Artifact:
        self._check_owner(artifact)
        self.session.add(ArtifactRecord(**_artifact_values(artifact)))
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Artifact conflict", error_code=ErrorCode.ARTIFACT_CONFLICT
            ) from exc
        return artifact

    async def update(self, artifact: Artifact) -> Artifact:
        self._check_owner(artifact)
        record = await self.session.scalar(
            select(ArtifactRecord)
            .where(ArtifactRecord.id == artifact.id, ArtifactRecord.owner_id == self.owner_id)
            .with_for_update()
        )
        if record is None:
            raise InfrastructureError("Artifact not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        for name, value in _artifact_values(artifact).items():
            setattr(record, name, value)
        await self.session.flush()
        return artifact

    async def list_retryable(self, *, limit: int) -> list[Artifact]:
        records = (
            await self.session.scalars(
                select(ArtifactRecord)
                .where(
                    ArtifactRecord.owner_id == self.owner_id,
                    ArtifactRecord.status.in_(
                        [ArtifactStatus.DELETE_PENDING.value, ArtifactStatus.DELETE_FAILED.value]
                    ),
                )
                .limit(limit)
            )
        ).all()
        return [self._to_domain(record) for record in records]

    async def list_object_keys(self) -> set[str]:
        values = await self.session.scalars(
            select(ArtifactRecord.object_key).where(
                ArtifactRecord.owner_id == self.owner_id,
                ArtifactRecord.object_key.is_not(None),
            )
        )
        return {value for value in values if value is not None}

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    def _check_owner(self, artifact: Artifact) -> None:
        if artifact.owner_id != self.owner_id:
            raise InfrastructureError("Artifact not found", error_code=ErrorCode.ENTITY_NOT_FOUND)


class SqlAlchemySourceDocumentRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session, self.owner_id = session, owner_id

    async def add(self, source: SourceDocument) -> SourceDocument:
        if source.owner_id != self.owner_id:
            raise InfrastructureError("Source not found", error_code=ErrorCode.ENTITY_NOT_FOUND)
        self.session.add(
            SourceDocumentRecord(
                id=source.id,
                owner_id=source.owner_id,
                version=source.version,
                artifact_id=source.artifact_id,
                artifact_version=source.artifact_version,
                source_kind=source.source_kind.value,
                acquisition_method=source.acquisition_method,
                license_note=source.license_note,
                locator=source.locator,
                acquired_at=source.acquired_at,
                published_at=source.published_at,
                content_sha256=source.content_sha256,
                created_at=source.created_at,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise InfrastructureError(
                "Source conflict", error_code=ErrorCode.SOURCE_CONFLICT
            ) from exc
        return source

    async def get_by_id(self, source_id: UUID) -> SourceDocument | None:
        record = await self.session.scalar(
            select(SourceDocumentRecord).where(
                SourceDocumentRecord.id == source_id, SourceDocumentRecord.owner_id == self.owner_id
            )
        )
        if not record:
            return None
        return SourceDocument(
            id=record.id,
            owner_id=record.owner_id,
            version=record.version,
            artifact_id=record.artifact_id,
            artifact_version=record.artifact_version,
            source_kind=SourceKind(record.source_kind),
            acquisition_method=record.acquisition_method,
            license_note=record.license_note,
            locator=record.locator,
            acquired_at=_utc(record.acquired_at),
            published_at=_utc(record.published_at) if record.published_at else None,
            content_sha256=record.content_sha256,
            created_at=_utc(record.created_at),
        )

    async def commit(self) -> None:
        await self.session.commit()


def _artifact_values(value: Artifact) -> dict[str, object]:
    return {
        "id": value.id,
        "owner_id": value.owner_id,
        "version": value.version,
        "kind": value.kind.value,
        "content_type": value.content_type,
        "size_bytes": value.size_bytes,
        "sha256": value.sha256,
        "object_key": value.object_key,
        "status": value.status.value,
        "idempotency_key": value.idempotency_key,
        "generator_version": value.generator_version,
        "generation_identity": value.generation_identity,
        "created_at": value.created_at,
        "deleted_at": value.deleted_at,
    }


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
