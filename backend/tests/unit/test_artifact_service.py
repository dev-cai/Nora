"""Artifact application coordination tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.application.knowledge import ArtifactService, UploadArtifactCommand
from app.domain.base.exceptions import ApplicationError
from app.domain.knowledge import Artifact, ArtifactKind, ArtifactStatus
from app.ports.knowledge import StoredObject, StoredObjectInfo


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values: dict[object, Artifact] = {}
        self.committed: dict[object, Artifact] = {}
        self.commit_calls = 0
        self.fail_commit_at: int | None = None

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
            raise RuntimeError("commit failed")
        self.committed = dict(self.values)
        return None

    async def rollback(self):
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

    async def add(self, event):
        self.events.append(event)
        return event


class MemoryStorage:
    def __init__(self, *, fail_put=False, fail_delete=False):
        self.values = {}
        self.fail_put = fail_put
        self.fail_delete = fail_delete

    async def put(self, *, object_key, data, content_type):
        if self.fail_put:
            raise RuntimeError("put failed")
        self.values[object_key] = StoredObject(data, content_type)

    async def get(self, *, object_key):
        return self.values[object_key]

    async def delete(self, *, object_key):
        if self.fail_delete:
            raise RuntimeError("delete failed")
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
async def test_storage_failures_never_publish_success_and_deletion_is_retryable() -> None:
    failing_service, artifacts, _ = _service(MemoryStorage(fail_put=True))
    owner = uuid4()
    with pytest.raises(ApplicationError, match="unavailable"):
        await failing_service.upload(
            UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "fail")
        )
    assert next(iter(artifacts.values.values())).status is ArtifactStatus.FAILED

    storage = MemoryStorage()
    service, artifacts, _ = _service(storage)
    available = await service.upload(
        UploadArtifactCommand(owner, ArtifactKind.SOURCE, "text/plain", b"alpha", "delete")
    )
    storage.fail_delete = True
    with pytest.raises(ApplicationError, match="retried"):
        await service.delete(owner, available.id)
    assert artifacts.values[available.id].status is ArtifactStatus.DELETE_FAILED
    with pytest.raises(ApplicationError, match="not found"):
        await service.download(owner, available.id)
    storage.fail_delete = False
    assert await service.retry_deletions() == 1
    assert artifacts.values[available.id].status is ArtifactStatus.DELETED


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

    with pytest.raises(ApplicationError, match="unavailable"):
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
