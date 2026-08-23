"""JD 导入固定 Graph 的清洗、识别和校验测试。"""

import pytest
from app.agent_runtime import JdImportAgent
from app.application.imports.jd import JdImportDraftContent
from app.domain.base.exceptions import DomainError
from app.infrastructure.model import FakeModelAdapter


def _content() -> JdImportDraftContent:
    unknown = {
        "value": None,
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": None,
    }
    return JdImportDraftContent.model_validate(
        {
            "jd_text": "模型可能返回的原始文本",
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
    )


@pytest.mark.asyncio
async def test_jd_agent_runs_clean_recognize_validate_graph_in_order() -> None:
    model = FakeModelAdapter([_content()])
    agent = JdImportAgent(model)

    result = await agent.run("职位\n职位\n\nPython  后端\r\n")

    assert result.jd_text == "职位\nPython 后端"
    assert result.job_title == "后端工程师"
    assert len(model.requests) == 1
    assert '"jd_text": "职位\\nPython 后端"' in model.requests[0].user_input
    assert model.requests[0].max_input_tokens == 16_000
    assert model.requests[0].max_output_tokens == 8_192


@pytest.mark.asyncio
async def test_jd_agent_rejects_empty_input_before_model_call() -> None:
    model = FakeModelAdapter([_content()])
    agent = JdImportAgent(model)

    with pytest.raises(DomainError, match="JD text is empty"):
        await agent.run(" \n\t ")

    assert model.requests == []


@pytest.mark.asyncio
async def test_jd_agent_normalizes_model_fact_values_before_domain_validation() -> None:
    candidate = _content().model_dump(mode="json")
    candidate["requirements"]["required_skills"] = {
        "value": "Python，SQL",
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": "熟悉 Python、SQL",
    }
    candidate["requirements"]["minimum_experience_years"] = {
        "value": "3年以上",
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": "3年以上经验",
    }
    candidate["requirements"]["work_mode"] = {
        "value": "远程",
        "confirmation_status": "unknown",
        "source_type": "text_range",
        "source_range": "支持远程办公",
    }

    result = await JdImportAgent(FakeModelAdapter([candidate])).run("JD")

    assert result.requirements.required_skills.value == ["Python", "SQL"]
    assert result.requirements.required_skills.confirmation_status == "unconfirmed"
    assert result.requirements.minimum_experience_years.value == 3
    assert result.requirements.minimum_experience_years.confirmation_status == "unconfirmed"
    assert result.requirements.work_mode.value == "remote"
