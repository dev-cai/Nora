"""CandidateProfile API 用户隔离与版本契约测试。"""

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


def _payload(status: str = "unconfirmed") -> dict[str, object]:
    return {
        "basic_information": {
            "display_name": {"value": "Alice", "confirmation_status": status},
            "current_location": {"value": "Shanghai", "confirmation_status": "confirmed"},
        },
        "preferences": {
            "target_locations": {"value": ["Shanghai"], "confirmation_status": "confirmed"},
            "accepts_remote": {"value": True, "confirmation_status": "confirmed"},
            "target_roles": {"value": ["Backend Engineer"], "confirmation_status": "unconfirmed"},
        },
        "education": [],
        "experiences": [],
        "skills": [],
    }


def test_profile_versions_are_user_scoped(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )

    with TestClient(create_app(settings)) as client:
        auth_a = _register_and_login(client, "profile-alice")
        auth_b = _register_and_login(client, "profile-bob")

        first = client.put("/profile", headers=auth_a, json=_payload())
        assert first.status_code == 200
        assert first.json()["version"] == 1
        assert (
            first.json()["content"]["basic_information"]["display_name"]["source_type"]
            == "user_input"
        )

        second = client.put("/profile", headers=auth_a, json=_payload("confirmed"))
        assert second.status_code == 200
        assert second.json()["version"] == 2
        assert client.get("/profile?version=1", headers=auth_a).json()["version"] == 1
        assert client.get("/profile", headers=auth_b).status_code == 404

        invalid_dates = _payload()
        invalid_dates["education"] = [
            {
                "school": {"value": "Example University"},
                "degree": {"value": "BS"},
                "major": {"value": "Computer Science"},
                "start_date": {"value": "2025-01-01"},
                "end_date": {"value": "2024-01-01"},
            }
        ]
        assert client.put("/profile", headers=auth_a, json=invalid_dates).status_code == 422

        missing_id = _payload()
        missing_id["skills"] = [
            {
                "name": {"value": "Python"},
                "proficiency": {"value": "advanced"},
                "years": {"value": 5},
            }
        ]
        assert client.put("/profile", headers=auth_a, json=missing_id).status_code == 422

        duplicate_id = str(uuid4())
        duplicate_ids = _payload()
        duplicate_ids["skills"] = [
            {
                "id": duplicate_id,
                "name": {"value": name},
                "proficiency": {"value": "advanced"},
                "years": {"value": 5},
            }
            for name in ("Python", "Go")
        ]
        assert client.put("/profile", headers=auth_a, json=duplicate_ids).status_code == 422
