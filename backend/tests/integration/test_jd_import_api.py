"""JD ImportSession/Draft API 的确认、版本与用户隔离测试。"""

import asyncio

from app.apps.api import create_app
from app.apps.api.dependencies.decision import get_model_port
from app.infrastructure.config import Settings
from app.infrastructure.database import Base
from app.infrastructure.model import FakeModelAdapter
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


def _model_content(text: str) -> dict[str, object]:
    unknown = {
        "value": None,
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": None,
    }
    return {
        "jd_text": text,
        "job_title": "后端工程师",
        "company_name": "Nora",
        "location": "上海",
        "requirements": {
            "required_skills": {
                "value": ["Python"],
                "confirmation_status": "unconfirmed",
                "source_type": "text_range",
                "source_range": None,
            },
            "minimum_experience_years": unknown,
            "degree_requirement": unknown,
            "location_requirement": unknown,
            "work_mode": unknown,
        },
    }


def test_jd_import_requires_confirmation_and_enforces_version_scope(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    app = create_app(settings)
    app.dependency_overrides[get_model_port] = lambda: FakeModelAdapter(
        [_model_content("Python 后端工程师\n负责服务开发")]
    )

    with TestClient(app) as client:
        auth_a = _register_and_login(client, "jd-import-alice")
        auth_b = _register_and_login(client, "jd-import-bob")
        created = client.post(
            "/imports/jd",
            headers=auth_a,
            json={"source_type": "image", "jd_text": "Python 后端工程师\n负责服务开发"},
        )
        assert created.status_code == 201, created.text
        draft = created.json()
        session_id = draft["session_id"]
        assert draft["status"] == "draft_ready"
        assert draft["content"]["job_title"] == "后端工程师"

        jobs_before = client.get("/job-postings", headers=auth_a)
        assert jobs_before.status_code == 200
        assert jobs_before.json()["total"] == 0

        foreign = client.get(f"/imports/jd/{session_id}", headers=auth_b)
        assert foreign.status_code == 404

        edited_content = draft["content"]
        edited_content["location"] = "北京"
        edited = client.put(
            f"/imports/jd/{session_id}/draft",
            headers=auth_a,
            json={"base_version": 1, "content": edited_content},
        )
        assert edited.status_code == 200, edited.text
        edited_body = edited.json()
        assert edited_body["version"] == 2
        assert edited_body["content"]["location"] == "北京"

        stale = client.post(
            f"/imports/jd/{session_id}/confirm",
            headers=auth_a,
            json={"base_version": 1, "content_fingerprint": draft["content_fingerprint"]},
        )
        assert stale.status_code == 409
        assert stale.json()["error_code"] == "import_confirmation_conflict"

        confirmed = client.post(
            f"/imports/jd/{session_id}/confirm",
            headers=auth_a,
            json={
                "base_version": edited_body["version"],
                "content_fingerprint": edited_body["content_fingerprint"],
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()
        assert result["job_posting"]["location"] == "北京"
        assert result["requirement_snapshot"]["job_posting_id"] == result["job_posting"]["id"]

        replay = client.post(
            f"/imports/jd/{session_id}/confirm",
            headers=auth_a,
            json={
                "base_version": edited_body["version"],
                "content_fingerprint": edited_body["content_fingerprint"],
            },
        )
        assert replay.status_code == 200
        assert replay.json()["job_posting"]["id"] == result["job_posting"]["id"]

        jobs_after = client.get("/job-postings", headers=auth_a)
        assert jobs_after.json()["total"] == 1
