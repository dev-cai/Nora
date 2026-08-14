"""MinIO ArtifactStorage failure-boundary tests."""

from types import SimpleNamespace

import pytest
from app.infrastructure.object_storage import MinioArtifactStorage
from minio.error import MinioException


class CleanupFailingMinio:
    def bucket_exists(self, _bucket: str) -> bool:
        return True

    def put_object(self, *_args, **_kwargs) -> None:
        return None

    def stat_object(self, _bucket: str, _object_key: str):
        return SimpleNamespace(
            size=7,
            content_type="text/plain",
            metadata={"sha256": "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"},
        )

    def copy_object(self, *_args) -> None:
        return None

    def remove_object(self, _bucket: str, object_key: str) -> None:
        if object_key.startswith(".pending/"):
            raise MinioException("secret temporary object key")


@pytest.mark.asyncio
async def test_temporary_cleanup_failure_is_observable_without_sensitive_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = MinioArtifactStorage(CleanupFailingMinio(), "artifacts")  # type: ignore[arg-type]

    with caplog.at_level("WARNING"):
        await storage.put(
            object_key="owner/artifact/1/object", data=b"payload", content_type="text/plain"
        )

    record = caplog.records[0]
    assert record.compensation_stage == "temporary_object_delete"
    assert record.error_type == "MinioException"
    assert "secret temporary object key" not in caplog.text
    assert ".pending/" not in caplog.text
