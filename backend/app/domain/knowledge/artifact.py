"""Immutable Artifact and SourceDocument lifecycle rules."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.base.exceptions import DomainError


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETE_PENDING = "delete_pending"
    DELETE_FAILED = "delete_failed"
    DELETED = "deleted"


class ArtifactKind(StrEnum):
    SOURCE = "source"
    GENERATED = "generated"


class SourceKind(StrEnum):
    FILE = "file"
    WEB = "web"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Artifact:
    id: UUID
    owner_id: UUID
    version: int
    kind: ArtifactKind
    content_type: str
    size_bytes: int
    sha256: str
    object_key: str | None
    status: ArtifactStatus
    idempotency_key: str
    generator_version: str | None
    generation_identity: str | None
    created_at: datetime
    deleted_at: datetime | None = None

    @classmethod
    def pending(
        cls,
        *,
        owner_id: UUID,
        kind: ArtifactKind,
        content_type: str,
        size_bytes: int,
        sha256: str,
        idempotency_key: str,
        generator_version: str | None = None,
        generation_identity: str | None = None,
        now: datetime | None = None,
    ) -> "Artifact":
        content_type = content_type.strip().lower()
        key = idempotency_key.strip()
        digest = sha256.strip().lower()
        if not content_type or len(content_type) > 255:
            raise DomainError("Content type is invalid", error_code="invalid_artifact_content_type")
        if size_bytes < 1:
            raise DomainError("Artifact must not be empty", error_code="invalid_artifact_size")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise DomainError("SHA-256 is invalid", error_code="invalid_artifact_sha256")
        if not key or len(key) > 255:
            raise DomainError("Idempotency key is invalid", error_code="invalid_idempotency_key")
        generator = " ".join(generator_version.split()) if generator_version else None
        identity = generation_identity.strip().lower() if generation_identity else None
        if kind is ArtifactKind.GENERATED and (
            not generator
            or len(generator) > 100
            or identity is None
            or len(identity) != 64
            or any(char not in "0123456789abcdef" for char in identity)
        ):
            raise DomainError(
                "Generated Artifact identity is invalid",
                error_code="invalid_generation_identity",
            )
        if kind is ArtifactKind.SOURCE and (generator is not None or identity is not None):
            raise DomainError(
                "Source Artifact cannot have a generator identity",
                error_code="invalid_generation_identity",
            )
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            version=1,
            kind=kind,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=digest,
            object_key=None,
            status=ArtifactStatus.PENDING,
            idempotency_key=key,
            generator_version=generator,
            generation_identity=identity,
            created_at=_utc(now),
        )

    def publish(self, object_key: str) -> "Artifact":
        if self.status not in {ArtifactStatus.PENDING, ArtifactStatus.FAILED}:
            raise DomainError("Artifact cannot be published", error_code="artifact_state_conflict")
        if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
            raise DomainError("Object key is invalid", error_code="invalid_object_key")
        return replace(self, object_key=object_key, status=ArtifactStatus.AVAILABLE)

    def fail(self) -> "Artifact":
        if self.status not in {ArtifactStatus.PENDING, ArtifactStatus.FAILED}:
            raise DomainError("Artifact cannot fail", error_code="artifact_state_conflict")
        return replace(self, status=ArtifactStatus.FAILED)

    def request_delete(self) -> "Artifact":
        if self.status not in {ArtifactStatus.AVAILABLE, ArtifactStatus.DELETE_FAILED}:
            raise DomainError("Artifact cannot be deleted", error_code="artifact_state_conflict")
        return replace(self, status=ArtifactStatus.DELETE_PENDING)

    def deletion_failed(self) -> "Artifact":
        if self.status is not ArtifactStatus.DELETE_PENDING:
            raise DomainError("Artifact deletion cannot fail", error_code="artifact_state_conflict")
        return replace(self, status=ArtifactStatus.DELETE_FAILED)

    def mark_deleted(self, now: datetime | None = None) -> "Artifact":
        if self.status is not ArtifactStatus.DELETE_PENDING:
            raise DomainError(
                "Artifact cannot become deleted", error_code="artifact_state_conflict"
            )
        return replace(self, status=ArtifactStatus.DELETED, object_key=None, deleted_at=_utc(now))


@dataclass(frozen=True, slots=True)
class SourceDocument:
    id: UUID
    owner_id: UUID
    version: int
    artifact_id: UUID
    artifact_version: int
    source_kind: SourceKind
    acquisition_method: str
    license_note: str
    locator: str | None
    acquired_at: datetime
    published_at: datetime | None
    content_sha256: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        artifact: Artifact,
        source_kind: SourceKind,
        acquisition_method: str,
        license_note: str,
        locator: str | None = None,
        acquired_at: datetime | None = None,
        published_at: datetime | None = None,
        now: datetime | None = None,
    ) -> "SourceDocument":
        if artifact.status is not ArtifactStatus.AVAILABLE:
            raise DomainError("Source artifact is unavailable", error_code="artifact_unavailable")
        method = " ".join(acquisition_method.split())
        license_value = " ".join(license_note.split())
        locator_value = " ".join(locator.split()) if locator else None
        if not method or len(method) > 100 or not license_value or len(license_value) > 500:
            raise DomainError("Source metadata is invalid", error_code="invalid_source_metadata")
        if locator_value and len(locator_value) > 2000:
            raise DomainError("Source locator is invalid", error_code="invalid_source_locator")
        return cls(
            id=uuid4(),
            owner_id=artifact.owner_id,
            version=1,
            artifact_id=artifact.id,
            artifact_version=artifact.version,
            source_kind=source_kind,
            acquisition_method=method,
            license_note=license_value,
            locator=locator_value,
            acquired_at=_utc(acquired_at),
            published_at=_utc(published_at) if published_at else None,
            content_sha256=artifact.sha256,
            created_at=_utc(now),
        )


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError("Timestamp must include a timezone", error_code="invalid_timestamp")
    return result.astimezone(timezone.utc)
