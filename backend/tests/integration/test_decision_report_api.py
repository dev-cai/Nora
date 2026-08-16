"""Decision analysis and versioned report public API contract tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.apps.api import create_app
from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.followup import get_resume_pdf_renderer
from app.apps.api.dependencies.governance import get_audit_event_repository
from app.apps.api.dependencies.knowledge import get_artifact_storage
from app.domain.base.exceptions import ErrorCode, InfrastructureError
from app.domain.followup import (
    TemplateAccent,
    TemplateDefinition,
    TemplateDensity,
    TemplatePageSize,
)
from app.domain.identity import User
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    ApplicationRecordRow,
    ApplicationRecordTransitionRow,
    AuditEventRecord,
    Base,
    InterviewCaseRow,
    TemplateDefinitionRecord,
)
from app.ports.followup import RenderedPdf
from app.ports.knowledge import ArtifactStorageError, StoredObject, StoredObjectInfo
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class MemoryArtifactStorage:
    def __init__(self) -> None:
        self.values: dict[str, StoredObject] = {}
        self.fail_put = False

    async def put(self, *, object_key: str, data: bytes, content_type: str) -> None:
        if self.fail_put:
            raise ArtifactStorageError("storage unavailable")
        self.values[object_key] = StoredObject(data=data, content_type=content_type)

    async def get(self, *, object_key: str) -> StoredObject:
        return self.values[object_key]

    async def delete(self, *, object_key: str) -> None:
        self.values.pop(object_key, None)

    async def list(self) -> list[StoredObjectInfo]:
        return []


class DeterministicPdfRenderer:
    renderer_version = "weasyprint-69.0-pango-1.56.3-api-test"
    font_set_version = "noto-cjk-api-test"

    def render(self, variant, template, generation_identity: str) -> RenderedPdf:
        del variant, template
        return RenderedPdf(
            data=b"%PDF-1.7\n" + generation_identity.encode() + b"\n" + b"0" * 64 + b"\n%%EOF"
        )


class UpgradedDeterministicPdfRenderer(DeterministicPdfRenderer):
    renderer_version = "weasyprint-69.0-pango-1.56.3-api-test-v2"


class FailingAuditRepository:
    async def add(self, _event) -> None:
        raise InfrastructureError("audit unavailable", error_code=ErrorCode.DATABASE_UNAVAILABLE)


def _reset_database(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())


def _seed_resume_template(database_url: str) -> TemplateDefinition:
    template = TemplateDefinition.create(
        template_id=uuid4(),
        version=1,
        name="API 清晰单栏",
        page_size=TemplatePageSize.A4,
        density=TemplateDensity.STANDARD,
        accent=TemplateAccent.NEUTRAL,
        section_order=("basic_information", "skills"),
        allowed_fields=("basic_information.*", "skills.*.*"),
        required_fields=("basic_information.display_name",),
        published_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )

    async def seed() -> None:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                TemplateDefinitionRecord(
                    record_id=uuid4(),
                    template_id=template.id,
                    version=template.version,
                    name=template.name,
                    definition={
                        "page_size": template.page_size.value,
                        "density": template.density.value,
                        "accent": template.accent.value,
                        "section_order": list(template.section_order),
                        "allowed_fields": list(template.allowed_fields),
                        "required_fields": list(template.required_fields),
                    },
                    definition_hash=template.definition_hash,
                    published_at=template.published_at,
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    return template


def _application_fact_counts(database_url: str, record_id: str) -> tuple[int, int, int]:
    async def count() -> tuple[int, int, int]:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            records = await session.scalar(
                select(func.count())
                .select_from(ApplicationRecordRow)
                .where(ApplicationRecordRow.id == UUID(record_id))
            )
            transitions = await session.scalar(
                select(func.count())
                .select_from(ApplicationRecordTransitionRow)
                .where(ApplicationRecordTransitionRow.application_record_id == UUID(record_id))
            )
            audits = await session.scalar(
                select(func.count())
                .select_from(AuditEventRecord)
                .where(
                    AuditEventRecord.target_type == "application_record",
                    AuditEventRecord.target_id == UUID(record_id),
                )
            )
        await engine.dispose()
        return int(records or 0), int(transitions or 0), int(audits or 0)

    return asyncio.run(count())


def _interview_facts(database_url: str, interview_id: str) -> tuple[int, list[str]]:
    async def read() -> tuple[int, list[str]]:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            versions = await session.scalar(
                select(func.count())
                .select_from(InterviewCaseRow)
                .where(InterviewCaseRow.id == UUID(interview_id))
            )
            audits = await session.scalars(
                select(AuditEventRecord.after_summary)
                .where(
                    AuditEventRecord.target_type == "interview_case",
                    AuditEventRecord.target_id == UUID(interview_id),
                )
                .order_by(AuditEventRecord.target_version)
            )
        await engine.dispose()
        return int(versions or 0), [value or "" for value in audits]

    return asyncio.run(read())


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
        foreign_source = client.post("/companies", headers=bob, json=snapshot_payload)
        assert foreign_source.status_code == 404
        assert foreign_source.json()["error_code"] == "entity_not_found"
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
        assert "decision_case_version" not in assessment
        assert assessment["status"] == "available"
        assert assessment["status_reason"] == "fixed_snapshot"
        replay = client.post(
            f"/reports/{report['id']}/company-assessment",
            headers=alice,
            json={"company_snapshot_id": first["id"], "company_snapshot_version": 1},
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == assessment["id"]
        assessment_schema = client.get("/openapi.json").json()["components"]["schemas"][
            "CompanyAssessmentResponse"
        ]["properties"]
        assert "decision_case_version" not in assessment_schema

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


def test_resume_variant_api_is_idempotent_versioned_and_user_scoped(
    database_url: str, capsys
) -> None:
    _reset_database(database_url)
    template = _seed_resume_template(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    app = create_app(settings)
    storage = MemoryArtifactStorage()
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    app.dependency_overrides[get_resume_pdf_renderer] = DeterministicPdfRenderer
    with TestClient(app) as client:
        alice = _register_and_login(client, "variant-alice")
        bob = _register_and_login(client, "variant-bob")
        inputs = _seed_decision_inputs(client, alice, name="variant")
        decision_case = client.post("/decisions", headers=alice, json=inputs)
        assert decision_case.status_code == 201
        report = client.post(f"/decisions/{decision_case.json()['id']}/reports", headers=alice)
        assert report.status_code == 200
        apply = client.post(
            f"/reports/{report.json()['id']}/decision",
            headers={**alice, "Idempotency-Key": "variant-apply"},
            json={"status": "apply", "reason": None},
        )
        assert apply.status_code == 201
        resume = client.get(f"/resumes/{inputs['resume_version_id']}", headers=alice).json()
        skill = resume["content"]["skills"][0]

        assert client.get("/templates").status_code == 401
        templates = client.get("/templates", headers=alice)
        assert templates.status_code == 200
        assert templates.json()[0]["definition_hash"] == template.definition_hash
        exact_template = client.get(
            f"/templates/{template.id}/versions/{template.version}", headers=alice
        )
        assert exact_template.status_code == 200
        assert "script" not in exact_template.text.lower()
        payload = {
            "application_decision_id": apply.json()["id"],
            "template_id": str(template.id),
            "template_version": template.version,
            "title": "后端岗位定制版",
            "blocks": [
                {
                    "source_path": "basic_information.display_name",
                    "label": "姓名",
                    "value": resume["content"]["basic_information"]["display_name"],
                },
                {
                    "source_path": f"skills.{skill['id']}.name",
                    "label": "核心技能",
                    "value": "Python / FastAPI",
                },
            ],
        }
        assert client.post("/resume-variants", json=payload).status_code == 401
        foreign = client.post(
            "/resume-variants",
            headers={**bob, "Idempotency-Key": "foreign-variant"},
            json=payload,
        )
        assert foreign.status_code == 404
        created = client.post(
            "/resume-variants",
            headers={**alice, "Idempotency-Key": "variant-1"},
            json=payload,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["decision_case_id"] == decision_case.json()["id"]
        assert body["job_posting_id"] == inputs["job_posting_id"]
        assert body["job_posting_version"] == inputs["job_posting_version"]
        assert body["job_requirement_snapshot_id"] == inputs["job_requirement_snapshot_id"]
        assert (
            body["job_requirement_snapshot_version"] == inputs["job_requirement_snapshot_version"]
        )
        assert body["resume_version_id"] == inputs["resume_version_id"]
        assert body["resume_version"] == inputs["resume_version"]
        assert body["template_version"] == 1

        replay = client.post(
            "/resume-variants",
            headers={**alice, "Idempotency-Key": "variant-1"},
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == body["id"]
        conflict = client.post(
            "/resume-variants",
            headers={**alice, "Idempotency-Key": "variant-1"},
            json={
                **payload,
                "blocks": [payload["blocks"][0], {**payload["blocks"][1], "value": "Rust"}],
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "idempotency_conflict"
        malicious = client.post(
            "/resume-variants",
            headers={**alice, "Idempotency-Key": "variant-malicious"},
            json={
                **payload,
                "blocks": [
                    payload["blocks"][0],
                    {
                        "source_path": "skills.skill-1.<script>",
                        "label": "x",
                        "value": "https://evil.example/script.js",
                    },
                ],
            },
        )
        assert malicious.status_code == 400

        listed = client.get("/resume-variants", headers=alice)
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["content_fingerprint"] == body["content_fingerprint"]
        assert client.get("/resume-variants", headers=bob).json()["total"] == 0
        assert client.get(f"/resume-variants/{body['id']}", headers=alice).json() == body
        assert client.get(f"/resume-variants/{body['id']}", headers=bob).status_code == 404

        assert client.get(f"/resume-variants/{body['id']}/pdf", headers=alice).status_code == 204
        assert client.post(f"/resume-variants/{body['id']}/pdf").status_code == 401
        assert client.post(f"/resume-variants/{body['id']}/pdf", headers=bob).status_code == 404
        generated = client.post(f"/resume-variants/{body['id']}/pdf", headers=alice)
        assert generated.status_code == 201, generated.text
        pdf = generated.json()
        assert pdf["status"] == "available"
        assert pdf["resume_variant_id"] == body["id"]
        assert pdf["resume_variant_version"] == body["version"]
        assert pdf["template_definition_hash"] == template.definition_hash
        assert pdf["variant_content_fingerprint"] == body["content_fingerprint"]
        assert pdf["artifact_size_bytes"] > 100
        artifact = client.get(f"/artifacts/{pdf['artifact_id']}", headers=alice)
        assert artifact.status_code == 200
        assert artifact.json()["kind"] == "generated"
        assert artifact.json()["content_type"] == "application/pdf"
        assert artifact.json()["status"] == "available"
        assert artifact.json()["size_bytes"] == pdf["artifact_size_bytes"]
        assert artifact.json()["sha256"] == pdf["artifact_sha256"]

        pdf_replay = client.post(f"/resume-variants/{body['id']}/pdf", headers=alice)
        assert pdf_replay.status_code == 200
        assert pdf_replay.json()["id"] == pdf["id"]
        assert pdf_replay.json()["artifact_sha256"] == pdf["artifact_sha256"]
        assert client.get(f"/resume-variants/{body['id']}/pdf", headers=alice).json() == pdf
        assert client.get(f"/resume-pdfs/{pdf['id']}", headers=alice).json() == pdf

        inline = client.get(f"/resume-pdfs/{pdf['id']}/content?download=false", headers=alice)
        assert inline.status_code == 200
        assert inline.content.startswith(b"%PDF-1.7")
        assert inline.headers["content-type"] == "application/pdf"
        assert inline.headers["content-disposition"].startswith("inline;")
        assert inline.headers["cache-control"] == "private, no-store"
        assert inline.headers["x-content-type-options"] == "nosniff"
        attachment = client.get(f"/resume-pdfs/{pdf['id']}/content", headers=alice)
        assert attachment.headers["content-disposition"].startswith("attachment;")
        assert client.get(f"/resume-pdfs/{pdf['id']}", headers=bob).status_code == 404
        assert client.get(f"/resume-pdfs/{pdf['id']}/content", headers=bob).status_code == 404

        assert (
            client.get(f"/resume-variants/{body['id']}/message-draft", headers=alice).status_code
            == 204
        )
        draft_payload = {
            "style": "professional",
            "user_note": "可在本周沟通",
            "referral_context": None,
        }
        assert (
            client.post(
                f"/resume-variants/{body['id']}/message-drafts", json=draft_payload
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/resume-variants/{body['id']}/message-drafts",
                headers={**bob, "Idempotency-Key": "foreign-draft"},
                json=draft_payload,
            ).status_code
            == 404
        )
        generated_draft = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-professional"},
            json=draft_payload,
        )
        assert generated_draft.status_code == 201, generated_draft.text
        draft = generated_draft.json()
        assert draft["version"] == 1
        assert draft["revision_type"] == "generated"
        assert draft["application_decision_id"] == apply.json()["id"]
        assert draft["resume_variant_id"] == body["id"]
        assert draft["candidate_profile_id"] == inputs["candidate_profile_id"]
        assert draft["resume_version_id"] == inputs["resume_version_id"]
        assert "Alice" in draft["text"]
        assert "Python" in draft["text"]
        assert "unknown" not in draft["text"]
        assert "补充说明：可在本周沟通" in draft["text"]
        draft_replay = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-professional"},
            json=draft_payload,
        )
        assert draft_replay.status_code == 200
        assert draft_replay.json()["id"] == draft["id"]
        same_generation = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-professional-replay"},
            json=draft_payload,
        )
        assert same_generation.status_code == 200
        assert same_generation.json()["id"] == draft["id"]
        draft_conflict = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-professional"},
            json={**draft_payload, "user_note": "不同内容"},
        )
        assert draft_conflict.status_code == 409
        assert draft_conflict.json()["error_code"] == "idempotency_conflict"
        missing_referral = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-referral-missing"},
            json={"style": "referral", "referral_context": None},
        )
        assert missing_referral.status_code == 400
        assert missing_referral.json()["error_code"] == "referral_context_required"
        referral = client.post(
            f"/resume-variants/{body['id']}/message-drafts",
            headers={**alice, "Idempotency-Key": "draft-referral"},
            json={
                "style": "referral",
                "referral_context": "经张女士建议，我来联系您。",
            },
        )
        assert referral.status_code == 201
        assert "经张女士建议" in referral.json()["text"]
        assert referral.json()["generation_identity"] != draft["generation_identity"]
        latest_for_variant = client.get(
            f"/resume-variants/{body['id']}/message-draft", headers=alice
        )
        assert latest_for_variant.status_code == 200
        assert latest_for_variant.json()["id"] == referral.json()["id"]

        edited_text = f"{draft['text']}\n\n期待您的回复。"
        edited = client.post(
            f"/message-drafts/{draft['id']}/revisions",
            headers={**alice, "Idempotency-Key": "draft  edit  1"},
            json={"base_version": 1, "text": edited_text},
        )
        assert edited.status_code == 201, edited.text
        assert edited.json()["version"] == 2
        assert edited.json()["previous_version"] == 1
        assert edited.json()["revision_type"] == "edited"
        edit_replay = client.post(
            f"/message-drafts/{draft['id']}/revisions",
            headers={**alice, "Idempotency-Key": "draft  edit  1"},
            json={"base_version": 1, "text": edited_text},
        )
        assert edit_replay.status_code == 200
        assert edit_replay.json()["content_fingerprint"] == edited.json()["content_fingerprint"]
        stale_edit = client.post(
            f"/message-drafts/{draft['id']}/revisions",
            headers={**alice, "Idempotency-Key": "draft-edit-stale"},
            json={"base_version": 1, "text": "过期编辑"},
        )
        assert stale_edit.status_code == 409
        assert stale_edit.json()["error_code"] == "message_draft_version_conflict"
        assert client.get(f"/message-drafts/{draft['id']}", headers=alice).json()["version"] == 2
        versions = client.get(f"/message-drafts/{draft['id']}/versions", headers=alice)
        assert [item["version"] for item in versions.json()] == [2, 1]
        original = client.get(f"/message-drafts/{draft['id']}/versions/1", headers=alice)
        assert original.status_code == 200
        assert original.json()["text"] == draft["text"]
        drafts = client.get("/message-drafts", headers=alice)
        assert drafts.status_code == 200
        assert drafts.json()["total"] == 2
        assert client.get("/message-drafts", headers=bob).json()["total"] == 0
        assert client.get(f"/message-drafts/{draft['id']}", headers=bob).status_code == 404

        application_payload = {
            "application_decision_id": apply.json()["id"],
            "resume_variant_id": body["id"],
            "resume_pdf_id": pdf["id"],
            "message_draft_id": draft["id"],
            "message_draft_version": 2,
        }
        assert client.post("/application-records", json=application_payload).status_code == 401
        assert (
            client.post(
                "/application-records",
                headers={**bob, "Idempotency-Key": "foreign-application"},
                json=application_payload,
            ).status_code
            == 404
        )
        created_application = client.post(
            "/application-records",
            headers={**alice, "Idempotency-Key": " application  one "},
            json=application_payload,
        )
        assert created_application.status_code == 201, created_application.text
        application = created_application.json()
        assert application["status"] == "planned"
        assert application["version"] == 1
        assert application["resume_pdf_id"] == pdf["id"]
        assert application["artifact_id"] == pdf["artifact_id"]
        assert application["artifact_sha256"] == pdf["artifact_sha256"]
        assert application["message_draft_id"] == draft["id"]
        assert application["message_draft_version"] == 2
        assert application["message_content_fingerprint"] == edited.json()["content_fingerprint"]
        application_replay = client.post(
            "/application-records",
            headers={**alice, "Idempotency-Key": "application  one"},
            json=application_payload,
        )
        assert application_replay.status_code == 200
        assert application_replay.json()["id"] == application["id"]
        assert client.get("/application-records", headers=alice).json()["total"] == 1
        assert client.get("/application-records", headers=bob).json()["total"] == 0
        assert (
            client.get(f"/application-records/{application['id']}", headers=bob).status_code == 404
        )
        assert (
            client.get(
                f"/application-records/{application['id']}/transitions", headers=alice
            ).json()
            == []
        )

        occurred_at = "2026-08-15T08:30:00+08:00"
        missing_channel = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application-missing-channel"},
            json={
                "base_version": 1,
                "to_status": "applied",
                "occurred_at": occurred_at,
                "channel": None,
            },
        )
        assert missing_channel.status_code == 400
        assert missing_channel.json()["error_code"] == "invalid_application_record"
        illegal_transition = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application-illegal"},
            json={
                "base_version": 1,
                "to_status": "interviewing",
                "occurred_at": occurred_at,
            },
        )
        assert illegal_transition.status_code == 409
        assert illegal_transition.json()["error_code"] == "application_record_transition_conflict"
        applied = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": " application  applied "},
            json={
                "base_version": 1,
                "to_status": "applied",
                "occurred_at": occurred_at,
                "channel": "company  website",
                "note": "user  confirmed",
            },
        )
        assert applied.status_code == 201, applied.text
        assert applied.json()["status"] == "applied"
        assert applied.json()["version"] == 2
        applied_replay = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application  applied"},
            json={
                "base_version": 1,
                "to_status": "applied",
                "occurred_at": occurred_at,
                "channel": "company website",
                "note": "user confirmed",
            },
        )
        assert applied_replay.status_code == 200
        assert applied_replay.json()["version"] == 2
        stale_transition = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application-stale"},
            json={
                "base_version": 1,
                "to_status": "withdrawn",
                "occurred_at": occurred_at,
            },
        )
        assert stale_transition.status_code == 409
        assert stale_transition.json()["error_code"] == "application_record_version_conflict"
        transitions = client.get(
            f"/application-records/{application['id']}/transitions", headers=alice
        )
        assert transitions.status_code == 200
        assert len(transitions.json()) == 1
        assert transitions.json()[0]["source"] == "user_confirmation"
        assert transitions.json()[0]["channel"] == "company website"
        assert transitions.json()[0]["actor_id"] == apply.json()["actor_id"]
        refreshed_application = client.get(
            f"/application-records/{application['id']}", headers=alice
        )
        assert refreshed_application.json()["status"] == "applied"
        assert refreshed_application.json()["version"] == 2

        app.dependency_overrides[get_audit_event_repository] = FailingAuditRepository
        audit_failure = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application-audit-failure"},
            json={
                "base_version": 2,
                "to_status": "interviewing",
                "occurred_at": occurred_at,
                "channel": "招聘平台",
            },
        )
        assert audit_failure.status_code == 503
        assert audit_failure.json()["error_code"] == "database_unavailable"
        app.dependency_overrides.pop(get_audit_event_repository)
        after_audit_failure = client.get(f"/application-records/{application['id']}", headers=alice)
        assert after_audit_failure.json()["status"] == "applied"
        assert after_audit_failure.json()["version"] == 2
        assert (
            len(
                client.get(
                    f"/application-records/{application['id']}/transitions", headers=alice
                ).json()
            )
            == 1
        )
        assert _application_fact_counts(database_url, application["id"]) == (1, 1, 2)

        interview_payload = {
            "starts_at": "2026-10-15T09:30:00+08:00",
            "timezone": "Asia/Shanghai",
            "mode": "online",
            "location": None,
            "meeting_url": "https://meet.example.com/private-token",
            "round_number": 1,
            "note": "private interview note",
            "status": "scheduled",
        }
        before_interviewing = client.post(
            f"/application-records/{application['id']}/interviews",
            headers={**alice, "Idempotency-Key": "interview-before-confirmation"},
            json=interview_payload,
        )
        assert before_interviewing.status_code == 409
        assert before_interviewing.json()["error_code"] == "interview_case_application_conflict"

        interviewing = client.post(
            f"/application-records/{application['id']}/transitions",
            headers={**alice, "Idempotency-Key": "application-interviewing"},
            json={
                "base_version": 2,
                "to_status": "interviewing",
                "occurred_at": occurred_at,
                "channel": "招聘平台",
            },
        )
        assert interviewing.status_code == 201, interviewing.text
        assert interviewing.json()["version"] == 3

        created_interview = client.post(
            f"/application-records/{application['id']}/interviews",
            headers={**alice, "Idempotency-Key": " interview  create "},
            json=interview_payload,
        )
        assert created_interview.status_code == 201, created_interview.text
        interview = created_interview.json()
        assert interview["version"] == 1
        assert interview["meeting_url"] == interview_payload["meeting_url"]
        assert interview["note"] == interview_payload["note"]

        interview_replay = client.post(
            f"/application-records/{application['id']}/interviews",
            headers={**alice, "Idempotency-Key": "interview  create"},
            json=interview_payload,
        )
        assert interview_replay.status_code == 200
        assert interview_replay.json()["id"] == interview["id"]
        assert client.get("/interviews", headers=alice).json()["total"] == 1
        assert client.get("/interviews", headers=bob).json()["total"] == 0
        assert client.get(f"/interviews/{interview['id']}", headers=bob).status_code == 404

        update_payload = {
            **interview_payload,
            "base_version": 1,
            "starts_at": "2026-10-15T10:30:00+08:00",
            "mode": "onsite",
            "location": "Shanghai office",
            "meeting_url": None,
            "round_number": 2,
            "note": "private updated note",
        }
        updated_interview = client.post(
            f"/interviews/{interview['id']}/versions",
            headers={**alice, "Idempotency-Key": "interview-update"},
            json=update_payload,
        )
        assert updated_interview.status_code == 201, updated_interview.text
        assert updated_interview.json()["version"] == 2
        update_replay = client.post(
            f"/interviews/{interview['id']}/versions",
            headers={**alice, "Idempotency-Key": "interview-update"},
            json=update_payload,
        )
        assert update_replay.status_code == 200
        stale_interview = client.post(
            f"/interviews/{interview['id']}/versions",
            headers={**alice, "Idempotency-Key": "interview-stale"},
            json={**update_payload, "round_number": 3},
        )
        assert stale_interview.status_code == 409
        assert stale_interview.json()["error_code"] == "interview_case_version_conflict"
        versions = client.get(f"/interviews/{interview['id']}/versions", headers=alice)
        assert [item["version"] for item in versions.json()] == [2, 1]
        original = client.get(f"/interviews/{interview['id']}/versions/1", headers=alice)
        assert original.status_code == 200
        assert original.json()["meeting_url"] == interview_payload["meeting_url"]

        def submit_concurrent_interview(round_number: int) -> tuple[int, dict[str, object]]:
            response = client.post(
                f"/interviews/{interview['id']}/versions",
                headers={
                    **alice,
                    "Idempotency-Key": f"interview-concurrent-{round_number}",
                },
                json={
                    **update_payload,
                    "base_version": 2,
                    "round_number": round_number,
                },
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            interview_results = list(executor.map(submit_concurrent_interview, [3, 4]))
        assert sorted(status for status, _body in interview_results) == [201, 409]
        assert client.get(f"/interviews/{interview['id']}", headers=alice).json()["version"] == 3
        version_count, interview_audits = _interview_facts(database_url, interview["id"])
        assert version_count == 3
        assert len(interview_audits) == 3
        assert all("private" not in summary for summary in interview_audits)
        assert all("meet.example.com" not in summary for summary in interview_audits)
        captured = capsys.readouterr()
        runtime_output = captured.out + captured.err
        assert "https://meet.example.com/private-token" not in runtime_output
        assert "private interview note" not in runtime_output
        assert "private updated note" not in runtime_output

        def submit_concurrent_transition(target: str) -> tuple[int, dict[str, object]]:
            response = client.post(
                f"/application-records/{application['id']}/transitions",
                headers={**alice, "Idempotency-Key": f"application-concurrent-{target}"},
                json={
                    "base_version": 3,
                    "to_status": target,
                    "occurred_at": occurred_at,
                    "channel": "招聘平台",
                },
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent_results = list(
                executor.map(submit_concurrent_transition, ["offer_received", "rejected"])
            )
        assert sorted(status for status, _body in concurrent_results) == [201, 409]
        loser = next(body for status, body in concurrent_results if status == 409)
        assert loser["error_code"] == "application_record_version_conflict"
        concurrent_winner = client.get(
            f"/application-records/{application['id']}", headers=alice
        ).json()
        assert concurrent_winner["version"] == 4
        assert concurrent_winner["status"] in {"offer_received", "rejected"}
        assert _application_fact_counts(database_url, application["id"]) == (1, 3, 4)

        app.dependency_overrides[get_resume_pdf_renderer] = UpgradedDeterministicPdfRenderer
        upgraded = client.post(f"/resume-variants/{body['id']}/pdf", headers=alice)
        assert upgraded.status_code == 201
        upgraded_pdf = upgraded.json()
        assert upgraded_pdf["id"] != pdf["id"]
        assert upgraded_pdf["artifact_id"] != pdf["artifact_id"]
        assert upgraded_pdf["generation_identity"] != pdf["generation_identity"]
        historical = client.get(f"/resume-pdfs/{pdf['id']}/content", headers=alice)
        assert historical.status_code == 200
        assert historical.content == inline.content
        assert client.get(f"/resume-pdfs/{pdf['id']}", headers=alice).json() == pdf

        retry_variant = client.post(
            "/resume-variants",
            headers={**alice, "Idempotency-Key": "variant-pdf-retry"},
            json={**payload, "title": "存储失败重试版"},
        )
        assert retry_variant.status_code == 201
        storage.fail_put = True
        failed = client.post(f"/resume-variants/{retry_variant.json()['id']}/pdf", headers=alice)
        assert failed.status_code == 503
        assert failed.json()["error_code"] == "artifact_storage_unavailable"
        failed_status = client.get(
            f"/resume-variants/{retry_variant.json()['id']}/pdf", headers=alice
        )
        assert failed_status.status_code == 200
        assert failed_status.json()["status"] == "failed"
        storage.fail_put = False
        recovered = client.post(f"/resume-variants/{retry_variant.json()['id']}/pdf", headers=alice)
        assert recovered.status_code == 201
        assert recovered.json()["id"] == failed_status.json()["id"]
        assert (
            recovered.json()["generation_identity"] == failed_status.json()["generation_identity"]
        )
        assert recovered.json()["status"] == "available"
