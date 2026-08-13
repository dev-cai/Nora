"""Real MinIO ArtifactStorage adapter contract."""

import os
from uuid import uuid4

import pytest
from app.infrastructure.object_storage import create_minio_storage


@pytest.mark.asyncio
async def test_minio_upload_download_list_and_delete() -> None:
    endpoint = os.getenv("TEST_ARTIFACT_STORAGE_ENDPOINT")
    if not endpoint:
        pytest.skip("TEST_ARTIFACT_STORAGE_ENDPOINT is required for the real MinIO contract")
    storage = create_minio_storage(
        endpoint=endpoint,
        access_key=os.environ["TEST_ARTIFACT_STORAGE_ACCESS_KEY"],
        secret_key=os.environ["TEST_ARTIFACT_STORAGE_SECRET_KEY"],
        bucket=os.environ["TEST_ARTIFACT_STORAGE_BUCKET"],
        secure=False,
    )
    key = f"test/{uuid4().hex}"
    await storage.put(object_key=key, data=b"artifact", content_type="text/plain")
    stored = await storage.get(object_key=key)
    assert stored.data == b"artifact"
    assert stored.content_type == "text/plain"
    assert key in {item.object_key for item in await storage.list()}
    assert not any(item.object_key.startswith(".pending/") for item in await storage.list())
    await storage.delete(object_key=key)
    assert key not in {item.object_key for item in await storage.list()}
