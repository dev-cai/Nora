"""JobRequirementSnapshot API 创建、版本追加、幂等与用户隔离测试。"""

import asyncio
from uuid import uuid4

from app.apps.api import create_app
from app.infrastructure.config import Settings
from app.infrastructure.database import Base
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


def _create_posting(client: TestClient, auth: dict[str, str], title: str = "Backend JD") -> str:
    response = client.post(
        "/job-postings",
        headers={**auth, "Idempotency-Key": str(uuid4())},
        json={
            "jd_text": "Senior backend engineer with Python, FastAPI and PostgreSQL experience.",
            "job_title": title,
            "company_name": "Example Corp",
            "location": "Beijing",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _content(skills: list[str] | None = None) -> dict[str, object]:
    return {
        "required_skills": {
            "value": skills or [],
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "minimum_experience_years": {
            "value": 3,
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "degree_requirement": {
            "value": "本科",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "location_requirement": {
            "value": "北京",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
        "work_mode": {
            "value": "hybrid",
            "confirmation_status": "unconfirmed",
            "source_type": "manual",
            "source_range": None,
        },
    }


def test_requirements_create_append_replay_and_scope(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    with TestClient(create_app(settings)) as client:
        auth_a = _register_and_login(client, "req-alice")
        auth_b = _register_and_login(client, "req-bob")
        posting_id = _create_posting(client, auth_a)

        assert (
            client.get(f"/job-postings/{posting_id}/requirements", headers=auth_a).status_code
            == 200
        )

        first = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth_a,
            json={"content": _content(skills=["Python"]), "job_posting_version": 1},
        )
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["version"] == 1
        assert body["content_hash"]

        replay = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth_a,
            json={"content": _content(skills=["Python"]), "job_posting_version": 1},
        )
        assert replay.status_code == 200
        assert replay.json()["version"] == 1

        second = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth_a,
            json={"content": _content(skills=["Python", "SQL"]), "job_posting_version": 1},
        )
        assert second.status_code == 201
        assert second.json()["version"] == 2
        assert second.json()["id"] == body["id"]

        listed = client.get(f"/job-postings/{posting_id}/requirements", headers=auth_a)
        assert listed.status_code == 200
        assert [item["version"] for item in listed.json()["items"]] == [2, 1]

        latest = client.get(f"/job-postings/{posting_id}/requirements/latest", headers=auth_a)
        assert latest.status_code == 200
        assert latest.json()["version"] == 2

        version_one = client.get(f"/job-postings/{posting_id}/requirements/1", headers=auth_a)
        assert version_one.status_code == 200
        assert version_one.json()["version"] == 1

        missing = client.get(f"/job-postings/{posting_id}/requirements/99", headers=auth_a)
        assert missing.status_code == 404

        foreign = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth_b,
            json={"content": _content(skills=["Go"]), "job_posting_version": 1},
        )
        assert foreign.status_code == 404


def test_requirements_validation_and_auth(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    with TestClient(create_app(settings)) as client:
        auth = _register_and_login(client, "req-carol")
        posting_id = _create_posting(client, auth)

        assert (
            client.post(
                f"/job-postings/{posting_id}/requirements", json={"content": _content()}
            ).status_code
            == 401
        )

        invalid_enum = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth,
            json={
                "content": _content(),
                "job_posting_version": 0,
            },
        )
        assert invalid_enum.status_code == 422

        invalid_work_mode = _content()
        invalid_work_mode["work_mode"]["value"] = "invalid"
        domain_rejected = client.post(
            f"/job-postings/{posting_id}/requirements",
            headers=auth,
            json={"content": invalid_work_mode, "job_posting_version": 1},
        )
        assert domain_rejected.status_code == 400
        assert domain_rejected.json()["error_code"] == "invalid_requirement_field"
