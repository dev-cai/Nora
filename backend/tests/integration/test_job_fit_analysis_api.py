"""Authenticated AI job-fit generation, recovery, isolation and fallback API tests."""

import asyncio
import json
from typing import cast
from uuid import uuid4

from app.apps.api import create_app
from app.apps.api.dependencies.decision import get_model_port
from app.domain.agent_runtime import AgentRunStatus, AgentToolCallStatus
from app.domain.base.exceptions import ErrorCode
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    AgentRunRecord,
    AgentToolCallRecord,
    Base,
    JobFitAnalysisRecord,
)
from app.ports.model import ModelError, ModelOutputT, ModelRequest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class CatalogJobFitModel:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.illegal_citation = False

    async def generate_structured(
        self,
        request: ModelRequest,
        output_type: type[ModelOutputT],
    ) -> ModelOutputT:
        self.calls += 1
        if self.fail:
            raise ModelError(
                "Model provider is unavailable",
                ErrorCode.MODEL_PROVIDER_UNAVAILABLE,
            )
        payload = json.loads(request.user_input)
        catalog = payload["evidence_catalog"]
        skill = next(
            item
            for item in catalog
            if item["source"] == "candidate_profile" and item["field_path"] == "skills"
        )
        required = next(
            item
            for item in catalog
            if item["source"] == "job_requirement_snapshot"
            and item["field_path"] == "required_skills"
        )
        experience = next(
            item
            for item in catalog
            if item["source"] == "candidate_profile" and item["field_path"] == "experiences"
        )

        def citation(item: dict[str, object], citation_id: str) -> dict[str, object]:
            return {
                "citation_id": citation_id,
                "source": item["source"],
                "object_id": item["object_id"],
                "version": item["version"],
                "field_path": item["field_path"],
            }

        result = {
            "overall_fit": "moderate",
            "overall_fit_reason": {
                "text": "Python 匹配，搜索 API 经验可迁移，但向量检索证据不足。",
                "citation_ids": ["skill", "required", "experience"],
            },
            "strong_matches": [{"text": "已确认 Python 能力。", "citation_ids": ["skill"]}],
            "transferable_evidence": [
                {
                    "text": "搜索 API 的接口与性能经验可迁移到向量检索服务。",
                    "citation_ids": ["experience", "required"],
                }
            ],
            "critical_gaps": [],
            "non_blocking_gaps": [
                {"text": "缺少直接向量检索项目证据。", "citation_ids": ["required"]}
            ],
            "resume_actions": [
                {"text": "补充搜索 API 的量化结果。", "citation_ids": ["experience"]}
            ],
            "project_deep_dive_risks": [],
            "interview_focus": [
                {"text": "说明传统搜索经验的迁移路径。", "citation_ids": ["experience"]}
            ],
            "unknowns": [],
            "citations": [
                citation(skill, "skill"),
                citation(required, "required"),
                citation(experience, "experience"),
            ],
        }
        if self.illegal_citation:
            result["citations"][0]["object_id"] = str(uuid4())
        return cast(ModelOutputT, output_type.model_validate(result))


def _reset_database(database_url: str) -> None:
    async def reset() -> None:
        engine = create_async_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(reset())


def _register(client: TestClient, username: str) -> dict[str, str]:
    assert (
        client.post(
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "password-123",
            },
        ).status_code
        == 201
    )
    response = client.post("/auth/login", json={"username": username, "password": "password-123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _profile() -> dict[str, object]:
    def fact(value: object) -> dict[str, object]:
        return {"value": value, "confirmation_status": "confirmed"}

    return {
        "basic_information": {
            "display_name": fact("Alice"),
            "current_location": fact("上海"),
        },
        "preferences": {
            "target_locations": fact(["上海"]),
            "accepts_remote": fact(True),
            "target_roles": fact(["AI 应用工程师"]),
        },
        "education": [],
        "experiences": [
            {
                "id": str(uuid4()),
                "company": fact("示例公司"),
                "job_title": fact("后端工程师"),
                "start_date": fact("2024-01-01"),
                "end_date": fact("2025-01-01"),
                "responsibilities": fact(["构建搜索 API"]),
                "achievements": fact(["降低接口延迟"]),
            }
        ],
        "skills": [
            {
                "id": str(uuid4()),
                "name": fact("Python"),
                "proficiency": fact("advanced"),
                "years": fact(2),
            }
        ],
    }


def _inputs(client: TestClient, auth: dict[str, str], name: str) -> dict[str, object]:
    posting = client.post(
        "/job-postings",
        headers={**auth, "Idempotency-Key": f"job-fit-{name}"},
        json={
            "jd_text": "负责智能检索服务，需要 Python 与向量检索经验。",
            "job_title": "AI 应用工程师",
            "company_name": "示例公司",
            "location": "上海",
            "source_type": "manual",
        },
    ).json()

    def requirement(value: object) -> dict[str, object]:
        return {
            "value": value,
            "confirmation_status": "confirmed",
            "source_type": "manual",
            "source_range": None,
        }

    requirements = client.post(
        f"/job-postings/{posting['id']}/requirements",
        headers=auth,
        json={
            "job_posting_version": posting["version"],
            "content": {
                "required_skills": requirement(["Python", "向量检索"]),
                "minimum_experience_years": requirement(1),
                "degree_requirement": requirement("本科"),
                "location_requirement": requirement("上海"),
                "work_mode": requirement("hybrid"),
            },
        },
    ).json()
    profile_response = client.put("/profile", headers=auth, json=_profile())
    assert profile_response.status_code == 200
    profile = profile_response.json()
    resume_response = client.post(
        "/resumes",
        headers=auth,
        json={"title": f"{name} resume", "profile_version": profile["version"]},
    )
    assert resume_response.status_code == 201
    resume = resume_response.json()
    return {
        "job_posting_id": posting["id"],
        "job_posting_version": posting["version"],
        "job_requirement_snapshot_id": requirements["id"],
        "job_requirement_snapshot_version": requirements["version"],
        "candidate_profile_id": profile["id"],
        "candidate_profile_version": profile["version"],
        "resume_version_id": resume["id"],
        "resume_version": resume["version"],
    }


def _report(client: TestClient, auth: dict[str, str], name: str) -> dict[str, object]:
    case_response = client.post("/decisions", headers=auth, json=_inputs(client, auth, name))
    assert case_response.status_code == 201
    case = case_response.json()
    response = client.post(f"/decisions/{case['id']}/reports", headers=auth)
    assert response.status_code == 200
    return response.json()


def _analysis_count(database_url: str) -> int:
    async def count() -> int:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            value = await session.scalar(select(func.count()).select_from(JobFitAnalysisRecord))
        await engine.dispose()
        return int(value or 0)

    return asyncio.run(count())


def test_job_fit_analysis_api_generation_recovery_isolation_and_fallback(
    database_url: str,
) -> None:
    _reset_database(database_url)
    settings = Settings(
        database_url=database_url,
        auth_secret_key="test-secret-key-32-bytes-long-key!",
    )
    model = CatalogJobFitModel()
    app = create_app(settings)
    app.dependency_overrides[get_model_port] = lambda: model
    with TestClient(app) as client:
        alice = _register(client, "job-fit-alice")
        bob = _register(client, "job-fit-bob")
        report = _report(client, alice, "success")
        report_id = report["id"]

        empty = client.get(f"/reports/{report_id}/job-fit-analysis", headers=alice)
        assert empty.status_code == 204
        assert _analysis_count(database_url) == 0

        agent = client.post(
            "/agent-runs/decision-analysis",
            headers=alice,
            json={"report_id": report_id},
        )
        assert agent.status_code == 201
        agent_body = agent.json()
        assert agent_body["status"] == AgentRunStatus.COMPLETED.value
        assert agent_body["approval"] is None
        assert [item["tool_name"] for item in agent_body["tool_calls"]] == ["analyze_job_fit"]
        assert agent_body["tool_calls"][0]["status"] == AgentToolCallStatus.SUCCEEDED.value
        result_ref = agent_body["tool_calls"][0]["result_ref"]
        assert result_ref.startswith("job-fit-analysis:")
        assert model.calls == 1
        assert _analysis_count(database_url) == 1

        restored = client.get(f"/reports/{report_id}/job-fit-analysis", headers=alice)
        assert restored.status_code == 200
        body = restored.json()
        assert body["overall_fit"] == "moderate"
        assert body["transferable_evidence"]
        assert body["generation_identity"]
        analysis_id = body["id"]
        assert result_ref == f"job-fit-analysis:{analysis_id}:v{body['version']}"

        replay_agent = client.post(
            "/agent-runs/decision-analysis",
            headers=alice,
            json={"report_id": report_id},
        )
        assert replay_agent.status_code == 201
        replay_agent_body = replay_agent.json()
        assert replay_agent_body["status"] == AgentRunStatus.COMPLETED.value
        assert replay_agent_body["approval"] is None
        assert replay_agent_body["tool_calls"][0]["result_ref"] == result_ref
        assert model.calls == 1
        assert _analysis_count(database_url) == 1

        replay = client.post(f"/reports/{report_id}/job-fit-analysis", headers=alice)
        assert replay.status_code == 200
        assert replay.json() == body
        assert model.calls == 1
        assert client.get(f"/reports/{report_id}/job-fit-analysis", headers=bob).status_code == 404

        invalid_report = _report(client, alice, "invalid-citation")
        model.illegal_citation = True
        invalid = client.post(
            f"/reports/{invalid_report['id']}/job-fit-analysis",
            headers=alice,
        )
        assert invalid.status_code == 502
        assert invalid.json()["error_code"] == "model_output_invalid"
        assert _analysis_count(database_url) == 1

        fallback_report = _report(client, alice, "fallback")
        model.illegal_citation = False
        model.fail = True
        failed = client.post(f"/reports/{fallback_report['id']}/job-fit-analysis", headers=alice)
        assert failed.status_code == 503
        assert failed.json()["error_code"] == "model_provider_unavailable"
        assert client.get(f"/reports/{fallback_report['id']}", headers=alice).status_code == 200
        assert _analysis_count(database_url) == 1

        agent_failed = client.post(
            "/agent-runs/decision-analysis",
            headers=alice,
            json={"report_id": fallback_report["id"]},
        )
        assert agent_failed.status_code == 503

        async def runtime_failure_state() -> tuple[str, str]:
            engine = create_async_engine(database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                run = await session.scalar(
                    select(AgentRunRecord).order_by(AgentRunRecord.created_at.desc())
                )
                call = await session.scalar(
                    select(AgentToolCallRecord).order_by(AgentToolCallRecord.created_at.desc())
                )
            await engine.dispose()
            assert run is not None
            assert call is not None
            return run.status, call.status

        run_status, call_status = asyncio.run(runtime_failure_state())
        assert run_status == AgentRunStatus.FAILED.value
        assert call_status == AgentToolCallStatus.FAILED.value
