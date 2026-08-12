"""Decision analysis and versioned report public API contract tests."""

import asyncio
from uuid import uuid4

from app.apps.api import create_app
from app.apps.api.dependencies import get_current_user
from app.domain.identity import User
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
    registered = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password-123",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": username, "password": "password-123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _profile_payload(*, confirm_skills: bool = True) -> dict[str, object]:
    confirmed = "confirmed"
    unconfirmed = "unconfirmed"
    skill_status = confirmed if confirm_skills else unconfirmed
    return {
        "basic_information": {
            "display_name": {"value": "Alice", "confirmation_status": confirmed},
            "current_location": {"value": "上海", "confirmation_status": confirmed},
        },
        "preferences": {
            "target_locations": {"value": ["上海"], "confirmation_status": confirmed},
            "accepts_remote": {"value": True, "confirmation_status": confirmed},
            "target_roles": {"value": ["后端工程师"], "confirmation_status": confirmed},
        },
        "education": [],
        "experiences": [],
        "skills": [
            {
                "id": str(uuid4()),
                "name": {"value": "Python", "confirmation_status": skill_status},
                "proficiency": {"value": "advanced", "confirmation_status": unconfirmed},
                "years": {"value": 3, "confirmation_status": unconfirmed},
            }
        ],
    }


def _requirement_payload(*, skills_status: str = "confirmed") -> dict[str, object]:
    def fact(value: object, confirmation_status: str = "confirmed") -> dict[str, object]:
        return {
            "value": value,
            "confirmation_status": confirmation_status,
            "source_type": "manual",
            "source_range": None,
        }

    return {
        "content": {
            "required_skills": fact(["Python"], skills_status),
            "minimum_experience_years": fact(None, "unknown"),
            "degree_requirement": fact(None, "unknown"),
            "location_requirement": fact("上海"),
            "work_mode": fact("remote"),
        },
        "job_posting_version": 1,
    }


def _seed_decision_inputs(
    client: TestClient,
    auth: dict[str, str],
    *,
    name: str,
    skills_status: str = "confirmed",
) -> dict[str, object]:
    posting = client.post(
        "/job-postings",
        headers={**auth, "Idempotency-Key": f"posting-{name}"},
        json={"jd_text": f"{name} Python backend role"},
    )
    assert posting.status_code == 201
    posting_body = posting.json()
    requirement = client.post(
        f"/job-postings/{posting_body['id']}/requirements",
        headers=auth,
        json=_requirement_payload(skills_status=skills_status),
    )
    assert requirement.status_code == 201
    profile = client.put("/profile", headers=auth, json=_profile_payload())
    assert profile.status_code == 200
    resume = client.post(
        "/resumes",
        headers=auth,
        json={"title": f"{name} resume", "profile_version": profile.json()["version"]},
    )
    assert resume.status_code == 201
    return {
        "job_posting_id": posting_body["id"],
        "job_posting_version": posting_body["version"],
        "job_requirement_snapshot_id": requirement.json()["id"],
        "job_requirement_snapshot_version": requirement.json()["version"],
        "candidate_profile_id": profile.json()["id"],
        "candidate_profile_version": profile.json()["version"],
        "resume_version_id": resume.json()["id"],
        "resume_version": resume.json()["version"],
    }


def test_decision_and_report_api_contract(database_url: str) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    with TestClient(create_app(settings)) as client:
        auth_a = _register_and_login(client, "decision-api-alice")
        auth_b = _register_and_login(client, "decision-api-bob")
        inputs = _seed_decision_inputs(client, auth_a, name="alice")

        assert client.post("/decisions", json=inputs).status_code == 401
        invalid = client.post(
            "/decisions",
            headers=auth_a,
            json={**inputs, "resume_version": 0},
        )
        assert invalid.status_code == 422

        created = client.post("/decisions", headers=auth_a, json=inputs)
        assert created.status_code == 201
        case_id = created.json()["id"]
        assert created.json()["rule_set_version"] == "m3-rules-v1"
        replay = client.post("/decisions", headers=auth_a, json=inputs)
        assert replay.status_code == 200
        assert replay.json()["id"] == case_id

        analysis = client.get(f"/decisions/{case_id}", headers=auth_a)
        assert analysis.status_code == 200
        assert [item["rule_id"] for item in analysis.json()["rule_results"]] == [
            "skills.coverage",
            "experience.minimum_years",
            "location_work_mode.compatibility",
            "degree.minimum",
        ]
        assert {item["status"] for item in analysis.json()["rule_results"]} >= {"unknown"}

        report = client.post(f"/decisions/{case_id}/reports", headers=auth_a)
        assert report.status_code == 200
        report_body = report.json()
        report_id = report_body["id"]
        assert report_body["decision_case_id"] == case_id
        assert report_body["generator_version"] == "m3-report-v1"
        assert report_body["unknowns"]
        assert report_body["facts"]
        assert report_body["rule_results"]
        assert report_body["recommendations"]
        assert report_body["citations"]

        replayed_report = client.post(f"/decisions/{case_id}/reports", headers=auth_a)
        assert replayed_report.status_code == 200
        assert replayed_report.json()["id"] == report_id
        assert replayed_report.json()["version"] == 1

        fetched = client.get(f"/reports/{report_id}", headers=auth_a)
        assert fetched.status_code == 200
        assert fetched.json() == report_body
        assert client.get(f"/decisions/{case_id}", headers=auth_b).status_code == 404
        assert client.get(f"/reports/{report_id}", headers=auth_b).status_code == 404
        assert client.post(f"/decisions/{case_id}/reports", headers=auth_b).status_code == 404

        empty = client.get("/reports", headers=auth_b)
        assert empty.status_code == 200
        assert empty.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}
        listed = client.get("/reports?page=1&page_size=1", headers=auth_a)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert [item["id"] for item in listed.json()["items"]] == [report_id]

        second_inputs = _seed_decision_inputs(client, auth_a, name="alice-second")
        second_case = client.post("/decisions", headers=auth_a, json=second_inputs)
        assert second_case.status_code == 201
        second_report = client.post(
            f"/decisions/{second_case.json()['id']}/reports",
            headers=auth_a,
        )
        assert second_report.status_code == 200
        second_report_id = second_report.json()["id"]

        first_page = client.get("/reports?page=1&page_size=1", headers=auth_a)
        second_page = client.get("/reports?page=2&page_size=1", headers=auth_a)
        assert first_page.json()["total"] == 2
        assert [item["id"] for item in first_page.json()["items"]] == [second_report_id]
        assert [item["id"] for item in second_page.json()["items"]] == [report_id]
        assert client.get("/reports?page=0", headers=auth_a).status_code == 422


def test_decision_api_maps_visible_relationship_conflict_and_foreign_input(
    database_url: str,
) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    with TestClient(create_app(settings)) as client:
        auth_a = _register_and_login(client, "decision-conflict-alice")
        auth_b = _register_and_login(client, "decision-conflict-bob")
        first = _seed_decision_inputs(client, auth_a, name="first")
        second_posting = client.post(
            "/job-postings",
            headers={**auth_a, "Idempotency-Key": "posting-second"},
            json={"jd_text": "Second role"},
        ).json()
        second_requirement = client.post(
            f"/job-postings/{second_posting['id']}/requirements",
            headers=auth_a,
            json=_requirement_payload(),
        ).json()

        incompatible = client.post(
            "/decisions",
            headers=auth_a,
            json={
                **first,
                "job_requirement_snapshot_id": second_requirement["id"],
                "job_requirement_snapshot_version": second_requirement["version"],
            },
        )
        assert incompatible.status_code == 409
        assert incompatible.json()["error_code"] == "decision_input_conflict"

        foreign = client.post("/decisions", headers=auth_b, json=first)
        assert foreign.status_code == 404
        assert foreign.json()["error_code"] == "entity_not_found"


def test_decision_api_returns_503_without_database() -> None:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[get_current_user] = lambda: User.create(
        username="offline-user",
        email="offline-user@example.com",
    )
    with TestClient(app) as client:
        response = client.get("/reports")
    assert response.status_code == 503
    assert response.json()["error_code"] == "database_unavailable"
