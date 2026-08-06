"""JD 受控链接抓取预览 API 测试。"""

import asyncio
from uuid import uuid4

from app.apps.api import create_app
from app.apps.api.dependencies import get_jd_input_adapter
from app.infrastructure.config import Settings
from app.infrastructure.database import Base
from app.ports.jd_input import (
    JdImageInput,
    JdInputError,
    JdInputErrorCode,
    JdInputKind,
    JdInputPort,
    JdInputResult,
    JdUrlInput,
)
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine


def _reset_database(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())


def _register_and_login(client: TestClient, username: str) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "password-123"},
    )
    response = client.post("/auth/login", json={"username": username, "password": "password-123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class FakeFetchAdapter(JdInputPort):
    async def extract_image(self, request: JdImageInput) -> JdInputResult:
        raise JdInputError("not implemented", JdInputErrorCode.OCR_FAILED)

    async def fetch_url(self, request: JdUrlInput) -> JdInputResult:
        return JdInputResult(
            jd_text="Senior backend engineer with Python and FastAPI.",
            kind=JdInputKind.URL,
            source_url=request.url,
        )


def _app_with_fake_adapter(database_url: str) -> TestClient:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    app = create_app(settings)
    app.dependency_overrides[get_jd_input_adapter] = lambda: FakeFetchAdapter()
    return TestClient(app)


def test_fetch_requires_auth_and_rejects_invalid_url(database_url: str) -> None:
    client = _app_with_fake_adapter(database_url)
    with client:
        assert (
            client.post(
                "/job-postings/fetch", json={"url": "https://jobs.example.com/x"}
            ).status_code
            == 401
        )

        auth = _register_and_login(client, "fetch-alice")
        invalid = client.post(
            "/job-postings/fetch",
            headers=auth,
            json={"url": "ftp://jobs.example.com/x"},
        )
        assert invalid.status_code == 400
        assert invalid.json()["error_code"] == "invalid_url"


def test_fetch_returns_preview_that_feeds_creation(database_url: str) -> None:
    client = _app_with_fake_adapter(database_url)
    with client:
        auth = _register_and_login(client, "fetch-bob")

        preview = client.post(
            "/job-postings/fetch",
            headers=auth,
            json={"url": "https://jobs.example.com/backend"},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["kind"] == "url"
        assert body["source_url"] == "https://jobs.example.com/backend"
        assert "Python" in body["jd_text"]

        created = client.post(
            "/job-postings",
            headers={**auth, "Idempotency-Key": str(uuid4())},
            json={
                "jd_text": body["jd_text"],
                "job_title": "Backend Engineer",
                "company_name": "Example Corp",
                "source_type": "url",
                "source_url": body["source_url"],
            },
        )
        assert created.status_code == 201, created.text
        posting = created.json()
        assert posting["source_type"] == "url"
        assert posting["source_url"] == "https://jobs.example.com/backend"
        assert posting["jd_text"] == "Senior backend engineer with Python and FastAPI."
