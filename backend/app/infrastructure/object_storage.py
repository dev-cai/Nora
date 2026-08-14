"""Private MinIO/S3-compatible ArtifactStorage adapter."""

import asyncio
import hashlib
import logging
from io import BytesIO
from uuid import uuid4

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import MinioException

from app.ports.knowledge import ArtifactStorageError, StoredObject, StoredObjectInfo

logger = logging.getLogger(__name__)


class MinioArtifactStorage:
    def __init__(self, client: Minio, bucket: str) -> None:
        self.client, self.bucket = client, bucket

    async def ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(self.client.bucket_exists, self.bucket)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, self.bucket)

    async def put(self, *, object_key: str, data: bytes, content_type: str) -> None:
        self._validate_key(object_key)
        temporary_key = f".pending/{uuid4().hex}"
        primary_error: Exception | None = None
        try:
            await self.ensure_bucket()
            await asyncio.to_thread(
                self.client.put_object,
                self.bucket,
                temporary_key,
                BytesIO(data),
                len(data),
                content_type=content_type,
                metadata={"sha256": hashlib.sha256(data).hexdigest()},
            )
            stored = await asyncio.to_thread(self.client.stat_object, self.bucket, temporary_key)
            digest = hashlib.sha256(data).hexdigest()
            metadata = stored.metadata or {}
            stored_digest = metadata.get("x-amz-meta-sha256") or metadata.get("sha256")
            if (
                stored.size != len(data)
                or stored.content_type != content_type
                or stored_digest != digest
            ):
                raise ArtifactStorageError(
                    "Object storage verification failed", error_code="artifact_storage_unavailable"
                )
            await asyncio.to_thread(
                self.client.copy_object,
                self.bucket,
                object_key,
                CopySource(self.bucket, temporary_key),
            )
            published = await asyncio.to_thread(self.client.stat_object, self.bucket, object_key)
            published_metadata = published.metadata or {}
            published_digest = published_metadata.get(
                "x-amz-meta-sha256"
            ) or published_metadata.get("sha256")
            if (
                published.size != len(data)
                or published.content_type != content_type
                or published_digest != digest
            ):
                await asyncio.to_thread(self.client.remove_object, self.bucket, object_key)
                raise ArtifactStorageError(
                    "Object storage verification failed", error_code="artifact_storage_unavailable"
                )
        except MinioException as exc:
            primary_error = ArtifactStorageError(
                "Object storage write failed", error_code="artifact_storage_unavailable"
            )
            raise primary_error from exc
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            try:
                await asyncio.to_thread(self.client.remove_object, self.bucket, temporary_key)
            except MinioException as exc:
                logger.warning(
                    "Artifact storage cleanup failed compensation_stage=%s error_type=%s",
                    "temporary_object_delete",
                    type(exc).__name__,
                )
            except Exception as exc:
                if primary_error is not None:
                    raise ExceptionGroup(
                        "Artifact storage temporary cleanup failed", [primary_error, exc]
                    ) from primary_error
                raise

    async def get(self, *, object_key: str) -> StoredObject:
        self._validate_key(object_key)
        response = None
        try:
            response = await asyncio.to_thread(self.client.get_object, self.bucket, object_key)
            data = await asyncio.to_thread(response.read)
            return StoredObject(
                data=data,
                content_type=response.headers.get("content-type", "application/octet-stream"),
            )
        except MinioException as exc:
            raise ArtifactStorageError(
                "Object storage read failed", error_code="artifact_storage_unavailable"
            ) from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    async def delete(self, *, object_key: str) -> None:
        self._validate_key(object_key)
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, object_key)
        except MinioException as exc:
            raise ArtifactStorageError(
                "Object storage delete failed", error_code="artifact_storage_unavailable"
            ) from exc

    async def list(self) -> list[StoredObjectInfo]:
        try:
            objects = await asyncio.to_thread(
                lambda: list(self.client.list_objects(self.bucket, recursive=True))
            )
        except MinioException as exc:
            raise ArtifactStorageError(
                "Object storage list failed", error_code="artifact_storage_unavailable"
            ) from exc
        return [
            StoredObjectInfo(object_key=item.object_name, last_modified=item.last_modified)
            for item in objects
        ]

    @staticmethod
    def _validate_key(value: str) -> None:
        if not value or value.startswith("/") or ".." in value.split("/"):
            raise ArtifactStorageError("Object key is invalid", error_code="invalid_object_key")


def create_minio_storage(
    *, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool
) -> MinioArtifactStorage:
    return MinioArtifactStorage(
        Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure), bucket
    )
