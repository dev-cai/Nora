"""Decision analysis and versioned report public API contract tests."""

import asyncio
from uuid import uuid4

from app.apps.api import create_app
from app.apps.api.dependencies import get_artifact_storage, get_current_user
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import Base
from app.ports.knowledge import StoredObject, StoredObjectInfo
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine


class MemoryArtifactStorage:
    def __init__(self) -> None:
        self.values: dict[str, StoredObject] = {}

    async def put(self, *, object_key: str, data: bytes, content_type: str) -> None:
        self.values[object_key] = StoredObject(data=data, content_type=content_type)

    async def get(self, *, object_key: str) -> StoredObject:
        return self.values[object_key]

    async def delete(self, *, object_key: str) -> None:
        self.values.pop(object_key, None)

    async def list(self) -> list[StoredObjectInfo]:
        return []


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
        assert report_body["company_assessment"] is None

        replayed_report = client.post(f"/decisions/{case_id}/reports", headers=auth_a)
        assert replayed_report.status_code == 200
        assert replayed_report.json()["id"] == report_id
        assert replayed_report.json()["version"] == 1

        fetched = client.get(f"/reports/{report_id}", headers=auth_a)
        assert fetched.status_code == 200
        assert fetched.json() == report_body
        assert client.get(f"/reports/{report_id}/decision", headers=auth_a).status_code == 204
        missing_reason = client.post(
            f"/reports/{report_id}/decision",
            headers={**auth_a, "Idempotency-Key": "decision-missing-reason"},
            json={"status": "skip", "reason": ""},
        )
        assert missing_reason.status_code == 422
        decided = client.post(
            f"/reports/{report_id}/decision",
            headers={**auth_a, "Idempotency-Key": "decision-alice-1"},
            json={"status": "skip", "reason": "岗位地点不合适"},
        )
        assert decided.status_code == 201
        decision_body = decided.json()
        assert decision_body["report_id"] == report_id
        assert decision_body["report_version"] == report_body["version"]
        assert decision_body["decision_case_id"] == case_id
        assert decision_body["resume_version_id"] == inputs["resume_version_id"]
        assert decision_body["resume_version"] == inputs["resume_version"]
        assert decision_body["status"] == "skip"
        assert decision_body["reason"] == "岗位地点不合适"
        replayed_decision = client.post(
            f"/reports/{report_id}/decision",
            headers={**auth_a, "Idempotency-Key": "decision-alice-1"},
            json={"status": "skip", "reason": "岗位地点不合适"},
        )
        assert replayed_decision.status_code == 200
        assert replayed_decision.json() == decision_body
        conflicting_decision = client.post(
            f"/reports/{report_id}/decision",
            headers={**auth_a, "Idempotency-Key": "decision-alice-2"},
            json={"status": "apply", "reason": None},
        )
        assert conflicting_decision.status_code == 409
        assert conflicting_decision.json()["error_code"] == "application_decision_conflict"
        assert client.get(f"/reports/{report_id}/decision", headers=auth_a).json() == decision_body
        assert client.get(f"/decisions/{case_id}", headers=auth_b).status_code == 404
        assert client.get(f"/reports/{report_id}", headers=auth_b).status_code == 404
        assert client.get(f"/reports/{report_id}/decision", headers=auth_b).status_code == 404
        assert (
            client.post(
                f"/reports/{report_id}/decision",
                headers={**auth_b, "Idempotency-Key": "decision-bob-1"},
                json={"status": "apply", "reason": None},
            ).status_code
            == 404
        )
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


def test_company_api_returns_503_without_database() -> None:
    app = create_app(Settings(database_url=None))
    app.dependency_overrides[get_current_user] = lambda: User.create(
        username="offline-company-user",
        email="offline-company-user@example.com",
    )
    with TestClient(app) as client:
        response = client.get(f"/companies/{uuid4()}")
    assert response.status_code == 503
    assert response.json()["error_code"] == "database_unavailable"


def test_company_assessment_fixes_snapshot_version_in_report_contract(database_url: str) -> None:
    _reset_database(database_url)
    app = create_app(
        Settings(
            database_url=database_url,
            auth_secret_key="test-secret-key-32-bytes-long-key!",
        )
    )
    app.dependency_overrides[get_artifact_storage] = MemoryArtifactStorage
    with TestClient(app) as client:
        alice = _register_and_login(client, "company-report-alice")
        bob = _register_and_login(client, "company-report-bob")
        inputs = _seed_decision_inputs(client, alice, name="company-report")
        decision = client.post("/decisions", headers=alice, json=inputs)
        report = client.post(f"/decisions/{decision.json()['id']}/reports", headers=alice).json()

        uploaded = client.post(
            "/artifacts",
            headers={**alice, "Idempotency-Key": "company-source"},
            files={"file": ("company.txt", b"company source", "text/plain")},
        )
        assert uploaded.status_code == 201, uploaded.text
        source = client.post(
            "/sources",
            headers=alice,
            json={
                "artifact_id": uploaded.json()["id"],
                "source_kind": "manual",
                "acquisition_method": "user_entry",
                "license_note": "user supplied",
                "published_at": "2026-08-01T00:00:00Z",
            },
        )
        assert source.status_code == 201, source.text
        snapshot_payload = {
            "company_name": "Example Inc",
            "size": "100-499",
            "size_status": "confirmed",
            "industry": "Software",
            "industry_status": "confirmed",
            "review_summary": "Clear engineering ladder",
            "review_status": "unconfirmed",
            "source_id": source.json()["id"],
            "source_version": source.json()["version"],
            "source_tier": "official/company",
        }
        assert client.post("/companies", json=snapshot_payload).status_code == 401
        created = client.post("/companies", headers=alice, json=snapshot_payload)
        assert created.status_code == 201, created.text
        first = created.json()
        assert first["freshness"] == "fresh"
        assert "locator" not in first["source"]
        assert client.get(f"/companies/{first['id']}", headers=bob).status_code == 404

        missing = client.get(f"/reports/{report['id']}/company-assessment", headers=alice)
        assert missing.status_code == 204
        attached = client.post(
            f"/reports/{report['id']}/company-assessment",
            headers=alice,
            json={"company_snapshot_id": first["id"], "company_snapshot_version": 1},
        )
        assert attached.status_code == 201, attached.text
        assessment = attached.json()
        assert assessment["snapshot"]["version"] == 1
        assert assessment["decision_case_version"] == 1
        assert assessment["status"] == "available"
        assert assessment["status_reason"] == "fixed_snapshot"
        replay = client.post(
            f"/reports/{report['id']}/company-assessment",
            headers=alice,
            json={"company_snapshot_id": first["id"], "company_snapshot_version": 1},
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == assessment["id"]

        second_payload = {
            **snapshot_payload,
            "expected_version": 1,
            "size": "500-999",
            "size_status": "unconfirmed",
        }
        second_payload.pop("company_name")
        appended = client.post(
            f"/companies/{first['id']}/versions", headers=alice, json=second_payload
        )
        assert appended.status_code == 201, appended.text
        assert appended.json()["version"] == 2
        assert client.get(f"/companies/{first['id']}", headers=alice).json()["version"] == 2
        exact_first = client.get(f"/companies/{first['id']}/versions/1", headers=alice)
        assert exact_first.status_code == 200
        assert exact_first.json()["size"] == "100-499"
        versions = client.get(f"/companies/{first['id']}/versions", headers=alice)
        assert [item["version"] for item in versions.json()] == [2, 1]
        stale_append = client.post(
            f"/companies/{first['id']}/versions", headers=alice, json=second_payload
        )
        assert stale_append.status_code == 409
        assert stale_append.json()["error_code"] == "company_snapshot_version_conflict"

        historical = client.get(f"/reports/{report['id']}", headers=alice)
        assert historical.status_code == 200
        fixed = historical.json()["company_assessment"]
        assert fixed["id"] == assessment["id"]
        assert fixed["snapshot"]["version"] == 1
        assert fixed["snapshot"]["size"] == "100-499"
        deleted = client.delete(f"/artifacts/{uploaded.json()['id']}", headers=alice)
        assert deleted.status_code == 200
        assert client.get(f"/sources/{source.json()['id']}", headers=alice).status_code == 404
        after_source_delete = client.get(f"/reports/{report['id']}", headers=alice)
        assert after_source_delete.status_code == 200
        tombstone_source = after_source_delete.json()["company_assessment"]["snapshot"]["source"]
        assert tombstone_source["id"] == source.json()["id"]
        assert tombstone_source["version"] == source.json()["version"]
        assert "locator" not in tombstone_source
        assert "artifact_id" not in tombstone_source
        assert after_source_delete.json()["company_assessment"]["status"] == "available"

        second_inputs = _seed_decision_inputs(client, alice, name="company-source-deleted")
        second_case = client.post("/decisions", headers=alice, json=second_inputs)
        second_report = client.post(f"/decisions/{second_case.json()['id']}/reports", headers=alice)
        unavailable = client.post(
            f"/reports/{second_report.json()['id']}/company-assessment",
            headers=alice,
            json={"company_snapshot_id": first["id"], "company_snapshot_version": 1},
        )
        assert unavailable.status_code == 201
        assert unavailable.json()["status"] == "unknown"
        assert unavailable.json()["status_reason"] == "source_unavailable"
        conflict = client.post(
            f"/reports/{report['id']}/company-assessment",
            headers=alice,
            json={"company_snapshot_id": first["id"], "company_snapshot_version": 2},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "company_assessment_conflict"
        assert (
            client.post(
                f"/reports/{report['id']}/company-assessment",
                headers=bob,
                json={"company_snapshot_id": first["id"], "company_snapshot_version": 1},
            ).status_code
            == 404
        )
