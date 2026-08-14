"""Authenticated Artifact and Source API contract tests."""

import asyncio
from datetime import datetime, timezone

from app.apps.api import create_app
from app.apps.api.dependencies import get_artifact_storage
from app.infrastructure.config import Settings
from app.infrastructure.database import Base
from app.ports.knowledge import ArtifactStorageError, StoredObject, StoredObjectInfo
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine


class MemoryArtifactStorage:
    def __init__(self, *, put_error: Exception | None = None) -> None:
        self.values: dict[str, StoredObject] = {}
        self.put_error = put_error

    async def put(self, *, object_key: str, data: bytes, content_type: str) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.values[object_key] = StoredObject(data=data, content_type=content_type)

    async def get(self, *, object_key: str) -> StoredObject:
        return self.values[object_key]

    async def delete(self, *, object_key: str) -> None:
        self.values.pop(object_key, None)

    async def list(self) -> list[StoredObjectInfo]:
        return [
            StoredObjectInfo(
                object_key=key,
                last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            for key in self.values
        ]


def _reset_database(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())


def _client(
    database_url: str,
    *,
    storage: MemoryArtifactStorage | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    _reset_database(database_url)
    app = create_app(
        Settings(
            database_url=database_url,
            auth_secret_key="test-secret-key-32-bytes-long-key!",
            artifact_max_size_bytes=8,
            artifact_allowed_content_types="text/plain,application/pdf",
        )
    )
    selected_storage = storage or MemoryArtifactStorage()
    app.dependency_overrides[get_artifact_storage] = lambda: selected_storage
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _register_and_login(client: TestClient, username: str) -> dict[str, str]:
    registered = client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "password-123"},
    )
    assert registered.status_code == 201, registered.text
    response = client.post("/auth/login", json={"username": username, "password": "password-123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(
    client: TestClient,
    auth: dict[str, str],
    *,
    key: str,
    content: bytes = b"artifact",
    content_type: str = "text/plain",
    data: dict[str, str] | None = None,
):
    return client.post(
        "/artifacts",
        headers={**auth, "Idempotency-Key": key},
        files={"file": ("input.txt", content, content_type)},
        data=data or {},
    )


def test_artifact_source_lifecycle_and_cross_user_isolation(database_url: str) -> None:
    with _client(database_url) as client:
        alice = _register_and_login(client, "artifact-api-alice")
        bob = _register_and_login(client, "artifact-api-bob")

        created = _upload(client, alice, key="artifact-lifecycle")
        assert created.status_code == 201, created.text
        artifact = created.json()
        assert artifact["status"] == "available"
        assert "object_key" not in artifact

        downloaded = client.get(f"/artifacts/{artifact['id']}/content", headers=alice)
        assert downloaded.status_code == 200
        assert downloaded.content == b"artifact"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert "attachment" in downloaded.headers["content-disposition"]

        source = client.post(
            "/sources",
            headers=alice,
            json={
                "artifact_id": artifact["id"],
                "source_kind": "file",
                "acquisition_method": "user_upload",
                "license_note": "user supplied",
            },
        )
        assert source.status_code == 201, source.text
        assert source.json()["artifact_version"] == artifact["version"]
        assert source.json()["content_sha256"] == artifact["sha256"]

        for path in (
            f"/artifacts/{artifact['id']}",
            f"/artifacts/{artifact['id']}/content",
            f"/sources/{source.json()['id']}",
        ):
            assert client.get(path, headers=bob).status_code == 404
        assert client.delete(f"/artifacts/{artifact['id']}", headers=bob).status_code == 404

        deleted = client.delete(f"/artifacts/{artifact['id']}", headers=alice)
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["status"] == "deleted"
        assert client.get(f"/artifacts/{artifact['id']}/content", headers=alice).status_code == 404
        assert client.get(f"/sources/{source.json()['id']}", headers=alice).status_code == 404


def test_artifact_api_enforces_bounds_and_complete_idempotency(database_url: str) -> None:
    with _client(database_url) as client:
        auth = _register_and_login(client, "artifact-api-validation")
        identity = "a" * 64
        generated = {
            "kind": "generated",
            "generator_version": "renderer-1",
            "generation_identity": identity,
        }
        first = _upload(client, auth, key="generated", content=b"pdf", data=generated)
        assert first.status_code == 201, first.text
        replay = _upload(client, auth, key="generated", content=b"pdf", data=generated)
        assert replay.status_code == 201
        assert replay.json()["id"] == first.json()["id"]

        changed_identity = {**generated, "generation_identity": "b" * 64}
        conflict = _upload(client, auth, key="generated", content=b"pdf", data=changed_identity)
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "idempotency_conflict"

        too_large = _upload(client, auth, key="large", content=b"123456789")
        assert too_large.status_code == 413
        unsupported = _upload(client, auth, key="image", content=b"image", content_type="image/png")
        assert unsupported.status_code == 415
        assert _upload(client, {}, key="anonymous").status_code == 401


def test_known_artifact_storage_failure_returns_stable_503(database_url: str) -> None:
    storage = MemoryArtifactStorage(put_error=ArtifactStorageError("storage unavailable"))
    with _client(database_url, storage=storage) as client:
        auth = _register_and_login(client, "artifact-api-storage-failure")
        response = _upload(client, auth, key="known-storage-failure")

    assert response.status_code == 503
    assert response.json()["error_code"] == "artifact_storage_unavailable"


def test_unknown_artifact_storage_failure_returns_sanitized_500(database_url: str) -> None:
    secret = "internal storage secret"
    storage = MemoryArtifactStorage(put_error=RuntimeError(secret))
    with _client(
        database_url,
        storage=storage,
        raise_server_exceptions=False,
    ) as client:
        auth = _register_and_login(client, "artifact-api-unknown-failure")
        response = _upload(client, auth, key="unknown-storage-failure")

    assert response.status_code == 500
    assert response.json() == {
        "error_code": "internal_error",
        "message": "Internal server error",
    }
    assert secret not in response.text
