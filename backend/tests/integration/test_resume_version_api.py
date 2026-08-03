"""ResumeVersion API 发布、历史不可变与用户隔离测试。"""

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


def _profile_payload(skill_id: str, skill_name: str) -> dict[str, object]:
    return {
        "basic_information": {
            "display_name": {"value": "Alice", "confirmation_status": "confirmed"},
            "current_location": {"value": "Shanghai", "confirmation_status": "unconfirmed"},
        },
        "preferences": {
            "target_locations": {"value": ["Shanghai"], "confirmation_status": "confirmed"},
            "accepts_remote": {"value": True, "confirmation_status": "confirmed"},
            "target_roles": {"value": ["Backend Engineer"], "confirmation_status": "confirmed"},
        },
        "education": [],
        "experiences": [],
        "skills": [
            {
                "id": skill_id,
                "name": {"value": skill_name, "confirmation_status": "confirmed"},
                "proficiency": {"value": "advanced", "confirmation_status": "unconfirmed"},
                "years": {"value": 5, "confirmation_status": "unconfirmed"},
            }
        ],
    }


def test_resume_versions_snapshot_profile_and_remain_user_scoped(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    skill_id = str(uuid4())

    with TestClient(create_app(settings)) as client:
        auth_a = _register_and_login(client, "resume-alice")
        auth_b = _register_and_login(client, "resume-bob")

        assert client.get("/resumes").status_code == 401
        profile_v1 = client.put(
            "/profile", headers=auth_a, json=_profile_payload(skill_id, "Python")
        )
        assert profile_v1.status_code == 200

        first = client.post(
            "/resumes",
            headers=auth_a,
            json={"title": "Backend Resume", "profile_version": 1},
        )
        assert first.status_code == 201
        first_body = first.json()
        assert first_body["version"] == 1
        assert first_body["profile_version"] == 1
        assert first_body["content"] == {
            "basic_information": {"display_name": "Alice"},
            "skills": [{"id": skill_id, "name": "Python"}],
        }

        profile_v2 = client.put("/profile", headers=auth_a, json=_profile_payload(skill_id, "Go"))
        assert profile_v2.status_code == 200
        second = client.post(
            "/resumes",
            headers=auth_a,
            json={"title": "Updated Resume", "profile_version": 2},
        )
        assert second.status_code == 201
        assert second.json()["version"] == 2
        assert second.json()["content"]["skills"][0]["name"] == "Go"

        old = client.get(f"/resumes/{first_body['id']}", headers=auth_a)
        assert old.status_code == 200
        assert old.json()["content"]["skills"][0]["name"] == "Python"
        assert client.get(f"/resumes/{first_body['id']}", headers=auth_b).status_code == 404

        first_page = client.get("/resumes?page=1&page_size=1", headers=auth_a)
        assert first_page.status_code == 200
        assert first_page.json()["total"] == 2
        assert first_page.json()["items"][0]["version"] == 2
        second_page = client.get("/resumes?page=2&page_size=1", headers=auth_a)
        assert second_page.json()["items"][0]["version"] == 1

        assert (
            client.post(
                "/resumes",
                headers=auth_a,
                json={"title": "Missing", "profile_version": 99},
            ).status_code
            == 404
        )
        assert client.get("/resumes?page=0", headers=auth_a).status_code == 422
