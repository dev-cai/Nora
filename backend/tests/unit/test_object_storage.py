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


class PublishAndCleanupFailingMinio(CleanupFailingMinio):
    def copy_object(self, *_args) -> None:
        raise RuntimeError("publish defect")

    def remove_object(self, _bucket: str, _object_key: str) -> None:
        raise RuntimeError("cleanup defect")


class UnavailableMinio(CleanupFailingMinio):
    def bucket_exists(self, _bucket: str) -> bool:
        raise MinioException("private endpoint details")


@pytest.mark.asyncio
async def test_temporary_cleanup_failure_is_observable_without_sensitive_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = MinioArtifactStorage(CleanupFailingMinio(), "artifacts")  # type: ignore[arg-type]

    with caplog.at_level("WARNING"):
        await storage.put(
            object_key="owner/artifact/1/object", data=b"payload", content_type="text/plain"
        )

    assert "compensation_stage=temporary_object_delete" in caplog.text
    assert "error_type=MinioException" in caplog.text
    assert "secret temporary object key" not in caplog.text
    assert ".pending/" not in caplog.text


@pytest.mark.asyncio
async def test_unknown_temporary_cleanup_failure_preserves_primary_error() -> None:
    storage = MinioArtifactStorage(  # type: ignore[arg-type]
        PublishAndCleanupFailingMinio(), "artifacts"
    )

    with pytest.raises(ExceptionGroup) as error:
        await storage.put(
            object_key="owner/artifact/1/object", data=b"payload", content_type="text/plain"
        )

    assert str(error.value.exceptions[0]) == "publish defect"
    assert str(error.value.exceptions[1]) == "cleanup defect"


@pytest.mark.asyncio
async def test_readiness_only_reports_bucket_availability() -> None:
    available = MinioArtifactStorage(CleanupFailingMinio(), "artifacts")  # type: ignore[arg-type]
    unavailable = MinioArtifactStorage(UnavailableMinio(), "artifacts")  # type: ignore[arg-type]

    assert await available.ready() is True
    assert await unavailable.ready() is False
