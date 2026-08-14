"""Artifact upload, download, source metadata, and deletion coordination."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.domain.base.exceptions import ApplicationError, InfrastructureError
from app.domain.governance import AuditAction, AuditEvent
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus, SourceDocument, SourceKind
from app.ports.governance import AuditEventRepository
from app.ports.knowledge import (
    ArtifactRepository,
    ArtifactStorage,
    ArtifactStorageError,
    SourceDocumentRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UploadArtifactCommand:
    owner_id: UUID
    kind: ArtifactKind
    content_type: str
    data: bytes
    idempotency_key: str
    generator_version: str | None = None
    generation_identity: str | None = None


@dataclass(frozen=True, slots=True)
class CreateSourceCommand:
    owner_id: UUID
    artifact_id: UUID
    source_kind: SourceKind
    acquisition_method: str
    license_note: str
    locator: str | None = None
    acquired_at: datetime | None = None
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    artifact: Artifact
    data: bytes


class ArtifactService:
    def __init__(
        self,
        artifacts: ArtifactRepository,
        sources: SourceDocumentRepository,
        storage: ArtifactStorage,
        audit_events: AuditEventRepository,
        *,
        max_size_bytes: int,
        allowed_content_types: frozenset[str],
    ) -> None:
        self.artifacts = artifacts
        self.sources = sources
        self.storage = storage
        self.audit_events = audit_events
        self.max_size_bytes = max_size_bytes
        self.allowed_content_types = allowed_content_types

    async def upload(self, command: UploadArtifactCommand) -> Artifact:
        content_type = command.content_type.strip().lower()
        if content_type not in self.allowed_content_types:
            raise ApplicationError(
                "Artifact content type is not allowed", error_code="unsupported_artifact_type"
            )
        if not command.data or len(command.data) > self.max_size_bytes:
            raise ApplicationError("Artifact size is invalid", error_code="artifact_too_large")
        digest = hashlib.sha256(command.data).hexdigest()
        candidate = Artifact.pending(
            owner_id=command.owner_id,
            kind=command.kind,
            content_type=content_type,
            size_bytes=len(command.data),
            sha256=digest,
            idempotency_key=command.idempotency_key,
            generator_version=command.generator_version,
            generation_identity=command.generation_identity,
        )
        existing = await self.artifacts.get_by_idempotency_key(candidate.idempotency_key)
        if existing is not None:
            if (
                existing.sha256 != candidate.sha256
                or existing.content_type != candidate.content_type
                or existing.size_bytes != candidate.size_bytes
                or existing.kind is not candidate.kind
                or existing.generator_version != candidate.generator_version
                or existing.generation_identity != candidate.generation_identity
            ):
                raise ApplicationError(
                    "Idempotency key is already used for a different Artifact",
                    error_code="idempotency_conflict",
                )
            if existing.status is ArtifactStatus.AVAILABLE:
                return existing
            artifact = existing
        else:
            artifact = candidate
            await self.artifacts.add(artifact)
            await self.artifacts.commit()

        object_key = f"{command.owner_id}/{artifact.id}/{artifact.version}/{uuid4().hex}"
        try:
            await self.storage.put(
                object_key=object_key, data=command.data, content_type=content_type
            )
        except ArtifactStorageError as exc:
            failed = artifact.fail()
            cleanup_errors = await self._persist_compensation_state(
                failed,
                action=AuditAction.CREATE,
                result="storage_failed",
                idempotency_key=command.idempotency_key,
            )
            self._raise_cleanup_errors(
                "Artifact upload failure persistence failed", exc, cleanup_errors
            )
            raise ApplicationError(
                "Artifact storage is unavailable", error_code="artifact_storage_unavailable"
            ) from exc

        try:
            published = artifact.publish(object_key)
            await self.artifacts.update(published)
            await self._audit(
                actor_id=command.owner_id,
                action=AuditAction.CREATE,
                artifact=published,
                result="available",
                idempotency_key=command.idempotency_key,
            )
            await self.artifacts.commit()
            return published
        except Exception as exc:
            cleanup_errors = await self._compensate_failed_publish(artifact, object_key)
            self._raise_cleanup_errors("Artifact publish compensation failed", exc, cleanup_errors)
            raise

    async def get(self, owner_id: UUID, artifact_id: UUID) -> Artifact:
        artifact = await self.artifacts.get_by_id(artifact_id)
        if artifact is None or artifact.owner_id != owner_id:
            raise ApplicationError("Artifact not found", error_code="entity_not_found")
        return artifact

    async def download(self, owner_id: UUID, artifact_id: UUID) -> ArtifactDownload:
        artifact = await self.get(owner_id, artifact_id)
        if artifact.status is not ArtifactStatus.AVAILABLE or not artifact.object_key:
            raise ApplicationError("Artifact not found", error_code="entity_not_found")
        stored = await self.storage.get(object_key=artifact.object_key)
        if (
            len(stored.data) != artifact.size_bytes
            or stored.content_type.strip().lower() != artifact.content_type
            or hashlib.sha256(stored.data).hexdigest() != artifact.sha256
        ):
            raise ApplicationError("Artifact integrity check failed", error_code="artifact_corrupt")
        await self._audit(
            actor_id=owner_id,
            action=AuditAction.READ,
            artifact=artifact,
            result="downloaded",
        )
        await self.artifacts.commit()
        return ArtifactDownload(artifact=artifact, data=stored.data)

    async def create_source(self, command: CreateSourceCommand) -> SourceDocument:
        artifact = await self.get(command.owner_id, command.artifact_id)
        source = SourceDocument.create(
            artifact=artifact,
            source_kind=command.source_kind,
            acquisition_method=command.acquisition_method,
            license_note=command.license_note,
            locator=command.locator,
            acquired_at=command.acquired_at,
            published_at=command.published_at,
        )
        await self.sources.add(source)
        await self.audit_events.add(
            AuditEvent.create(
                actor_id=command.owner_id,
                action=AuditAction.CREATE,
                target_type="source_document",
                target_id=source.id,
                target_version=source.version,
                after_summary=f"source_kind={source.source_kind.value};result=available",
            )
        )
        await self.sources.commit()
        return source

    async def get_source(self, owner_id: UUID, source_id: UUID) -> SourceDocument:
        source = await self.sources.get_by_id(source_id)
        if source is None:
            raise ApplicationError("Source not found", error_code="entity_not_found")
        artifact = await self.get(owner_id, source.artifact_id)
        if (
            artifact.version != source.artifact_version
            or artifact.status is not ArtifactStatus.AVAILABLE
        ):
            raise ApplicationError("Source not found", error_code="entity_not_found")
        return source

    async def delete(self, owner_id: UUID, artifact_id: UUID) -> Artifact:
        artifact = await self.get(owner_id, artifact_id)
        if artifact.status is ArtifactStatus.DELETED:
            return artifact
        pending = artifact.request_delete()
        await self.artifacts.update(pending)
        await self._audit(
            actor_id=owner_id,
            action=AuditAction.DELETE,
            artifact=pending,
            result="delete_pending",
        )
        await self.artifacts.commit()
        return await self._physical_delete(pending)

    async def retry_deletions(self, *, limit: int = 100) -> int:
        completed = 0
        for artifact in await self.artifacts.list_retryable(limit=limit):
            pending = (
                artifact.request_delete()
                if artifact.status is ArtifactStatus.DELETE_FAILED
                else artifact
            )
            if pending is not artifact:
                await self.artifacts.update(pending)
                await self.artifacts.commit()
            result = await self._physical_delete(pending)
            completed += result.status is ArtifactStatus.DELETED
        return completed

    async def cleanup_orphans(
        self, *, owner_id: UUID, older_than: datetime, include_temporary: bool = False
    ) -> tuple[str, ...]:
        if older_than.tzinfo is None or older_than.utcoffset() is None:
            raise ApplicationError(
                "Cleanup cutoff requires a timezone", error_code="invalid_timestamp"
            )
        known = await self.artifacts.list_object_keys()
        removed: list[str] = []
        for item in await self.storage.list():
            in_owner_scope = item.object_key.startswith(f"{owner_id}/")
            is_temporary = include_temporary and item.object_key.startswith(".pending/")
            if (in_owner_scope and item.object_key not in known) or is_temporary:
                if item.last_modified.astimezone(timezone.utc) >= older_than.astimezone(
                    timezone.utc
                ):
                    continue
                await self.storage.delete(object_key=item.object_key)
                removed.append(item.object_key)
        return tuple(removed)

    async def _physical_delete(self, artifact: Artifact) -> Artifact:
        try:
            if artifact.object_key:
                await self.storage.delete(object_key=artifact.object_key)
        except ArtifactStorageError as exc:
            failed = artifact.deletion_failed()
            cleanup_errors = await self._persist_compensation_state(
                failed,
                action=AuditAction.DELETE,
                result="delete_failed",
            )
            self._raise_cleanup_errors(
                "Artifact delete failure persistence failed", exc, cleanup_errors
            )
            raise ApplicationError(
                "Artifact deletion will be retried", error_code="artifact_delete_failed"
            ) from exc

        try:
            deleted = artifact.mark_deleted()
            await self.artifacts.update(deleted)
            await self._audit(
                actor_id=artifact.owner_id,
                action=AuditAction.DELETE,
                artifact=deleted,
                result="deleted",
            )
            await self.artifacts.commit()
            return deleted
        except Exception as exc:
            cleanup_errors = await self._rollback_compensation("delete_publish", artifact)
            self._raise_cleanup_errors(
                "Artifact delete publish rollback failed", exc, cleanup_errors
            )
            raise

    async def _compensate_failed_publish(
        self, artifact: Artifact, object_key: str
    ) -> list[Exception]:
        errors = await self._rollback_compensation("upload_publish", artifact)
        try:
            await self.storage.delete(object_key=object_key)
        except ArtifactStorageError as exc:
            self._log_compensation_failure("object_delete", artifact, exc)
        except Exception as exc:
            errors.append(exc)
        return errors

    async def _persist_compensation_state(
        self,
        artifact: Artifact,
        *,
        action: AuditAction,
        result: str,
        idempotency_key: str | None = None,
    ) -> list[Exception]:
        errors: list[Exception] = []
        try:
            await self.artifacts.update(artifact)
            await self._audit(
                actor_id=artifact.owner_id,
                action=action,
                artifact=artifact,
                result=result,
                idempotency_key=idempotency_key,
            )
            await self.artifacts.commit()
            return errors
        except InfrastructureError as exc:
            self._log_compensation_failure("state_publish", artifact, exc)
        except Exception as exc:
            errors.append(exc)
        errors.extend(await self._rollback_compensation("state_publish", artifact))
        return errors

    async def _rollback_compensation(self, stage: str, artifact: Artifact) -> list[Exception]:
        try:
            await self.artifacts.rollback()
        except InfrastructureError as exc:
            self._log_compensation_failure(f"{stage}_rollback", artifact, exc)
        except Exception as exc:
            return [exc]
        return []

    @staticmethod
    def _raise_cleanup_errors(message: str, original: Exception, errors: list[Exception]) -> None:
        if errors:
            raise ExceptionGroup(message, [original, *errors]) from original

    @staticmethod
    def _log_compensation_failure(stage: str, artifact: Artifact, error: Exception) -> None:
        logger.warning(
            "Artifact compensation failed artifact_id=%s compensation_stage=%s error_type=%s",
            artifact.id,
            stage,
            type(error).__name__,
        )

    async def _audit(
        self,
        *,
        actor_id: UUID,
        action: AuditAction,
        artifact: Artifact,
        result: str,
        idempotency_key: str | None = None,
    ) -> None:
        await self.audit_events.add(
            AuditEvent.create(
                actor_id=actor_id,
                action=action,
                target_type="artifact",
                target_id=artifact.id,
                target_version=artifact.version,
                after_summary=(
                    f"kind={artifact.kind.value};status={artifact.status.value};result={result}"
                ),
                idempotency_key=idempotency_key,
            )
        )
