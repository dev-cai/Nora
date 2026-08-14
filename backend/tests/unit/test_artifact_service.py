"""Artifact application coordination tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.knowledge import ArtifactService, UploadArtifactCommand
from app.domain.base.exceptions import (
    ApplicationError,
    DomainError,
    ErrorCode,
    InfrastructureError,
)
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus
from app.ports.knowledge import ArtifactStorageError, StoredObject, StoredObjectInfo


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values: dict[object, Artifact] = {}
        self.committed: dict[object, Artifact] = {}
        self.commit_calls = 0
        self.fail_commit_at: int | None = None
        self.commit_error: Exception = RuntimeError("commit failed")
        self.rollback_error: Exception | None = None

    async def get_by_id(self, artifact_id):
        return self.values.get(artifact_id)

    async def get_by_idempotency_key(self, key):
        return next((v for v in self.values.values() if v.idempotency_key == key), None)

    async def add(self, artifact):
        self.values[artifact.id] = artifact
        return artifact

    async def update(self, artifact):
        self.values[artifact.id] = artifact
        return artifact

    async def list_retryable(self, *, limit):
        return [
            v
            for v in self.values.values()
            if v.status in {ArtifactStatus.DELETE_PENDING, ArtifactStatus.DELETE_FAILED}
        ][:limit]

    async def list_object_keys(self):
        return {value.object_key for value in self.values.values() if value.object_key}

    async def commit(self):
        self.commit_calls += 1
        if self.commit_calls == self.fail_commit_at:
            raise self.commit_error
        self.committed = dict(self.values)
        return None

    async def rollback(self):
        if self.rollback_error is not None:
            raise self.rollback_error
        self.values = dict(self.committed)
        return None


class MemorySources:
    async def add(self, source):
        return source

    async def get_by_id(self, source_id):
        return None

    async def commit(self):
        return None


class MemoryAudit:
    def __init__(self):
        self.events = []
        self.fail_add_at: int | None = None
        self.add_calls = 0
        self.add_error: Exception = RuntimeError("audit failed")

    async def add(self, event):
        self.add_calls += 1
        if self.add_calls == self.fail_add_at:
            raise self.add_error
        self.events.append(event)
        return event


class MemoryStorage:
    def __init__(
        self,
        *,
        put_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self.values = {}
        self.put_error = put_error
        self.delete_error = delete_error

    async def put(self, *, object_key, data, content_type):
        if self.put_error is not None:
            raise self.put_error
        self.values[object_key] = StoredObject(data, content_type)

    async def get(self, *, object_key):
        return self.values[object_key]

    async def delete(self, *, object_key):
        if self.delete_error is not None:
            raise self.delete_error
        self.values.pop(object_key, None)

    async def list(self):
        return [
            StoredObjectInfo(
                object_key=key,
                last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            for key in self.values
        ]


def _service(
    storage: MemoryStorage,
) -> tuple[ArtifactService, MemoryArtifacts, MemoryAudit]:
    artifacts = MemoryArtifacts()
    audit = MemoryAudit()
    return (
        ArtifactService(
            artifacts,
            MemorySources(),
            storage,
            audit,
            max_size_bytes=100,
            allowed_content_types=frozenset({"text/plain"}),
        ),
        artifacts,
        audit,
    )


@pytest.mark.asyncio
async def test_upload_is_idempotent_and_conflicting_content_is_rejected() -> None:
    service, _, _ = _service(MemoryStorage())
    owner = uuid4()
    command = UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "same")
    first = await service.upload(command)
    second = await service.upload(command)
    assert first == second
    with pytest.raises(ApplicationError, match="different Artifact"):
        await service.upload(
            UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"beta", "same")
        )


@pytest.mark.asyncio
async def test_idempotency_compares_kind_and_generation_identity() -> None:
    service, _, _ = _service(MemoryStorage())
    owner = uuid4()
    identity = "a" * 64
    command = UploadArtifactCommand(
        owner,
        ArtifactKind.GENERATED,
        "text/plain",
        b"alpha",
        " generated-key ",
        generator_version=" renderer 1 ",
        generation_identity=identity,
    )
    first = await service.upload(command)
    assert await service.upload(command) == first
    with pytest.raises(ApplicationError, match="different Artifact"):
        await service.upload(
            UploadArtifactCommand(
                owner,
                ArtifactKind.GENERATED,
                "text/plain",
                b"alpha",
                "generated-key",
                generator_version="renderer 1",
                generation_identity="b" * 64,
            )
        )
    with pytest.raises(ApplicationError, match="different Artifact"):
        await service.upload(
            UploadArtifactCommand(
                owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "generated-key"
            )
        )


@pytest.mark.asyncio
async def test_known_storage_failures_have_stable_codes_and_retryable_states() -> None:
    failing_service, artifacts, _ = _service(
        MemoryStorage(put_error=ArtifactStorageError("put failed"))
    )
    owner = uuid4()
    with pytest.raises(ApplicationError, match="unavailable") as upload_error:
        await failing_service.upload(
            UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "fail")
        )
    assert upload_error.value.error_code == "artifact_storage_unavailable"
    assert next(iter(artifacts.values.values())).status is ArtifactStatus.FAILED

    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    available = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "delete")
    )
    storage.delete_error = ArtifactStorageError("delete failed")
    with pytest.raises(ApplicationError, match="retried") as delete_error:
        await service.delete(owner, available.id)
    assert delete_error.value.error_code == "artifact_delete_failed"
    assert artifacts.values[available.id].status is ArtifactStatus.DELETE_FAILED
    with pytest.raises(ApplicationError, match="not found"):
        await service.download(owner, available.id)
    storage.delete_error = None
    assert await service.retry_deletions() == 1
    assert artifacts.values[available.id].status is ArtifactStatus.DELETED


@pytest.mark.asyncio
async def test_unknown_put_failure_is_not_reported_as_storage_unavailable() -> None:
    service, artifacts, _ = _service(MemoryStorage(put_error=RuntimeError("program defect")))
    owner = uuid4()

    with pytest.raises(RuntimeError, match="program defect"):
        await service.upload(
            UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "fail")
        )

    assert next(iter(artifacts.values.values())).status is ArtifactStatus.PENDING


@pytest.mark.asyncio
async def test_pending_repository_failure_is_not_reported_as_storage_unavailable() -> None:
    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    artifacts.fail_commit_at = 1
    artifacts.commit_error = InfrastructureError("database failed", ErrorCode.DATABASE_UNAVAILABLE)

    with pytest.raises(InfrastructureError, match="database failed") as error:
        await service.upload(
            UploadArtifactCommand(
                uuid4(), ArtifactKind.SOURCE, "text/plain", b"alpha", "pending-failure"
            )
        )

    assert error.value.error_code == "database_unavailable"
    assert storage.values == {}


@pytest.mark.asyncio
async def test_database_publish_failure_removes_object_and_retry_recovers() -> None:
    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    artifacts.fail_commit_at = 2
    owner = uuid4()
    command = UploadArtifactCommand(
        owner,
        ArtifactKind.GENERATED,
        "text/plain",
        b"alpha",
        "database-publish-failure",
        generator_version="renderer-1",
        generation_identity="a" * 64,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.upload(command)

    pending = next(iter(artifacts.values.values()))
    assert pending.status is ArtifactStatus.PENDING
    assert storage.values == {}

    artifacts.fail_commit_at = None
    recovered = await service.upload(command)
    assert recovered.id == pending.id
    assert recovered.status is ArtifactStatus.AVAILABLE
    assert len(storage.values) == 1


@pytest.mark.asyncio
async def test_audit_publish_failure_removes_object_and_preserves_original_error() -> None:
    storage = MemoryStorage()
    service, artifacts, audit = _service(storage)
    audit.fail_add_at = 1
    audit.add_error = InfrastructureError("audit database failed", ErrorCode.DATABASE_UNAVAILABLE)
    owner = uuid4()

    with pytest.raises(InfrastructureError, match="audit database failed") as error:
        await service.upload(
            UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "audit")
        )

    assert error.value.error_code == "database_unavailable"
    assert next(iter(artifacts.values.values())).status is ArtifactStatus.PENDING
    assert storage.values == {}


@pytest.mark.asyncio
async def test_domain_publish_failure_removes_object_and_preserves_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)

    def fail_publish(_artifact: Artifact, _object_key: str) -> Artifact:
        raise DomainError("invalid publish transition", ErrorCode.ARTIFACT_STATE_CONFLICT)

    monkeypatch.setattr(Artifact, "publish", fail_publish)
    with pytest.raises(DomainError, match="invalid publish transition"):
        await service.upload(
            UploadArtifactCommand(uuid4(), ArtifactKind.SOURCE, "text/plain", b"alpha", "domain")
        )

    assert next(iter(artifacts.values.values())).status is ArtifactStatus.PENDING
    assert storage.values == {}


@pytest.mark.asyncio
async def test_known_compensation_delete_failure_is_logged_without_sensitive_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = MemoryStorage(
        delete_error=ArtifactStorageError("private content at owner/object/key")
    )
    service, artifacts, audit = _service(storage)
    audit.fail_add_at = 1
    original = InfrastructureError("audit failed", ErrorCode.DATABASE_UNAVAILABLE)
    audit.add_error = original

    with caplog.at_level("WARNING"):
        with pytest.raises(InfrastructureError) as error:
            await service.upload(
                UploadArtifactCommand(
                    uuid4(), ArtifactKind.SOURCE, "text/plain", b"private content", "cleanup"
                )
            )

    artifact = next(iter(artifacts.values.values()))
    assert error.value is original
    assert str(artifact.id) in caplog.text
    assert "compensation_stage=object_delete" in caplog.text
    assert "error_type=ArtifactStorageError" in caplog.text
    assert "owner/object/key" not in caplog.text
    assert "private content" not in caplog.text


@pytest.mark.asyncio
async def test_unknown_compensation_failure_preserves_both_errors() -> None:
    storage = MemoryStorage(delete_error=RuntimeError("cleanup defect"))
    service, _, audit = _service(storage)
    audit.fail_add_at = 1
    original = InfrastructureError("audit failed", ErrorCode.DATABASE_UNAVAILABLE)
    audit.add_error = original

    with pytest.raises(ExceptionGroup) as error:
        await service.upload(
            UploadArtifactCommand(
                uuid4(), ArtifactKind.SOURCE, "text/plain", b"alpha", "cleanup-group"
            )
        )

    assert error.value.exceptions[0] is original
    assert isinstance(error.value.exceptions[1], RuntimeError)
    assert str(error.value.exceptions[1]) == "cleanup defect"


@pytest.mark.asyncio
async def test_delete_publish_failure_stays_pending_and_retry_recovers() -> None:
    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    owner = uuid4()
    available = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "delete-db")
    )
    artifacts.fail_commit_at = artifacts.commit_calls + 2

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.delete(owner, available.id)

    assert artifacts.values[available.id].status is ArtifactStatus.DELETE_PENDING
    assert storage.values == {}
    artifacts.fail_commit_at = None
    assert await service.retry_deletions() == 1
    assert artifacts.values[available.id].status is ArtifactStatus.DELETED


@pytest.mark.asyncio
async def test_delete_audit_failure_stays_pending_and_retry_recovers() -> None:
    storage = MemoryStorage()
    service, artifacts, audit = _service(storage)
    owner = uuid4()
    available = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "delete-audit")
    )
    audit.fail_add_at = audit.add_calls + 2
    original = InfrastructureError("delete audit failed", ErrorCode.DATABASE_UNAVAILABLE)
    audit.add_error = original

    with pytest.raises(InfrastructureError, match="delete audit failed") as error:
        await service.delete(owner, available.id)

    assert error.value is original
    assert artifacts.values[available.id].status is ArtifactStatus.DELETE_PENDING
    assert storage.values == {}
    audit.fail_add_at = None
    assert await service.retry_deletions() == 1
    assert artifacts.values[available.id].status is ArtifactStatus.DELETED


@pytest.mark.asyncio
async def test_unknown_physical_delete_failure_is_not_reported_as_storage_error() -> None:
    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    owner = uuid4()
    available = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "delete-bug")
    )
    storage.delete_error = RuntimeError("delete program defect")

    with pytest.raises(RuntimeError, match="delete program defect"):
        await service.delete(owner, available.id)

    assert artifacts.values[available.id].status is ArtifactStatus.DELETE_PENDING


@pytest.mark.asyncio
async def test_cleanup_only_removes_old_unreferenced_objects() -> None:
    storage = MemoryStorage()
    service, _, _ = _service(storage)
    owner = uuid4()
    storage.values[".pending/old"] = StoredObject(b"old", "text/plain")
    storage.values[f"{owner}/orphan"] = StoredObject(b"old", "text/plain")
    storage.values[f"{uuid4()}/other-user"] = StoredObject(b"keep", "text/plain")
    removed = await service.cleanup_orphans(
        owner_id=owner,
        older_than=datetime(2026, 6, 1, tzinfo=timezone.utc),
        include_temporary=True,
    )
    assert set(removed) == {".pending/old", f"{owner}/orphan"}
    assert len(storage.values) == 1


@pytest.mark.asyncio
async def test_audit_summaries_do_not_disclose_storage_or_content() -> None:
    storage = MemoryStorage()
    service, _, audit = _service(storage)
    owner = uuid4()
    artifact = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"private", "audit")
    )
    await service.download(owner, artifact.id)
    await service.delete(owner, artifact.id)

    summaries = "\n".join(event.after_summary or "" for event in audit.events)
    assert "private" not in summaries
    assert artifact.object_key not in summaries
    assert "bucket" not in summaries.lower()
    assert "credential" not in summaries.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored",
    [StoredObject(b"private!", "text/plain"), StoredObject(b"private", "application/pdf")],
)
async def test_download_rejects_size_or_content_type_drift(stored: StoredObject) -> None:
    storage = MemoryStorage()
    service, _, _ = _service(storage)
    owner = uuid4()
    artifact = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"private", "integrity")
    )
    assert artifact.object_key is not None
    storage.values[artifact.object_key] = stored
    with pytest.raises(ApplicationError, match="integrity"):
        await service.download(owner, artifact.id)
