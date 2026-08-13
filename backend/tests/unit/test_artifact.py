"""Artifact and SourceDocument lifecycle tests."""

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.domain.base.exceptions import DomainError
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus, SourceDocument, SourceKind


def _pending() -> Artifact:
    data = b"resume"
    return Artifact.pending(
        owner_id=uuid4(),
        kind=ArtifactKind.SOURCE,
        content_type="text/plain",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        idempotency_key="upload-1",
    )


def test_artifact_lifecycle_preserves_tombstone_without_object_key() -> None:
    pending = _pending()
    available = pending.publish(f"{pending.owner_id}/{pending.id}/1/random")
    delete_pending = available.request_delete()
    deleted = delete_pending.mark_deleted(datetime(2026, 8, 13, tzinfo=timezone.utc))

    assert pending.status is ArtifactStatus.PENDING
    assert available.status is ArtifactStatus.AVAILABLE
    assert deleted.status is ArtifactStatus.DELETED
    assert deleted.object_key is None
    assert deleted.deleted_at == datetime(2026, 8, 13, tzinfo=timezone.utc)


def test_source_requires_available_artifact_and_fixes_exact_version() -> None:
    pending = _pending()
    with pytest.raises(DomainError, match="unavailable"):
        SourceDocument.create(
            artifact=pending,
            source_kind=SourceKind.FILE,
            acquisition_method="user_upload",
            license_note="user supplied",
        )

    available = pending.publish(f"{pending.owner_id}/{pending.id}/1/random")
    source = SourceDocument.create(
        artifact=available,
        source_kind=SourceKind.FILE,
        acquisition_method="user_upload",
        license_note="user supplied",
    )
    assert source.artifact_id == available.id
    assert source.artifact_version == 1
    assert source.content_sha256 == available.sha256


@pytest.mark.parametrize("key", ["/absolute", "owner/../secret", ""])
def test_artifact_rejects_unsafe_object_keys(key: str) -> None:
    with pytest.raises(DomainError, match="Object key"):
        _pending().publish(key)


def test_generated_artifact_requires_stable_generation_identity() -> None:
    with pytest.raises(DomainError, match="identity"):
        Artifact.pending(
            owner_id=uuid4(),
            kind=ArtifactKind.GENERATED,
            content_type="application/pdf",
            size_bytes=3,
            sha256=hashlib.sha256(b"pdf").hexdigest(),
            idempotency_key="pdf-1",
        )
    artifact = Artifact.pending(
        owner_id=uuid4(),
        kind=ArtifactKind.GENERATED,
        content_type="application/pdf",
        size_bytes=3,
        sha256=hashlib.sha256(b"pdf").hexdigest(),
        idempotency_key="pdf-1",
        generator_version="pdf-v1",
        generation_identity=hashlib.sha256(b"inputs").hexdigest(),
    )
    assert artifact.generator_version == "pdf-v1"
