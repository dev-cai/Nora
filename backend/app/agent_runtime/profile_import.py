"""AI-assisted PDF resume parsing into an editable candidate-profile draft."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.pdf_text import extract_pdf_text
from app.ports.model import ModelPort, ModelRequest

PROFILE_IMPORT_PROMPT_VERSION = "profile-import-v1"

# Bounded ingestion for the full text-layer of a real resume. 32_768 is the
# ModelRequest input ceiling; 26_000 text characters keep the adapter's
# conservative token estimate below that ceiling (≈32.1k) even for dense
# line-oriented extraction, so the preflight never trips for a human resume.
PROFILE_IMPORT_MAX_INPUT_TOKENS = 32_768
PROFILE_IMPORT_MAX_TEXT_CHARS = 26_000


class _Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = ""


class _OptionalFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None = None


class _BoolFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: bool = False


class _ListFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: list[str] = Field(default_factory=list, max_length=50)


class _DateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: date | None = None


class _YearsFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float | None = Field(default=None, ge=0, le=100)


class _Basic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: _Fact = _Fact()
    current_location: _Fact = _Fact()


class _Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_locations: _ListFact = _ListFact()
    accepts_remote: _BoolFact = _BoolFact()
    target_roles: _ListFact = _ListFact()


class _Education(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    school: _Fact = _Fact()
    degree: _Fact = _Fact()
    major: _Fact = _Fact()
    start_date: _DateFact = _DateFact()
    end_date: _DateFact = _DateFact()


class _Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    company: _Fact = _Fact()
    job_title: _Fact = _Fact()
    start_date: _DateFact = _DateFact()
    end_date: _DateFact = _DateFact()
    responsibilities: _ListFact = _ListFact()
    achievements: _ListFact = _ListFact()


class _Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    name: _Fact = _Fact()
    proficiency: _OptionalFact = _OptionalFact()
    years: _YearsFact = _YearsFact()


class ProfileImportOutput(BaseModel):
    """Model output schema; facts are deliberately converted to unconfirmed input."""

    model_config = ConfigDict(extra="forbid")
    basic_information: _Basic = _Basic()
    preferences: _Preferences = _Preferences()
    education: list[_Education] = Field(default_factory=list, max_length=50)
    experiences: list[_Experience] = Field(default_factory=list, max_length=50)
    skills: list[_Skill] = Field(default_factory=list, max_length=100)


class ProfileImportAgent:
    def __init__(self, model: ModelPort) -> None:
        self._model = model

    async def run(self, pdf: bytes) -> dict[str, object]:
        text = extract_pdf_text(pdf, max_chars=PROFILE_IMPORT_MAX_TEXT_CHARS)
        request = ModelRequest(
            system_prompt=(
                "你是 Nora 的简历解析助手。只从简历原文提取事实，不得猜测或补全；"
                "返回主档草稿 JSON。未知字符串填空字符串，未知列表为空，未知日期和年限为 null，"
                "接受远程只有原文明确表达时才为 true。保留完整职责和成果。"
            ),
            user_input=f"以下是 PDF 简历提取文本，请解析为主档候选字段：\n\n{text}",
            prompt_version=PROFILE_IMPORT_PROMPT_VERSION,
            max_input_tokens=PROFILE_IMPORT_MAX_INPUT_TOKENS,
            max_output_tokens=8_192,
            temperature=0.0,
        )
        output = await self._model.generate_structured(request, ProfileImportOutput)
        return _to_profile_input(output)


def _fact(value: object) -> dict[str, object]:
    return {"value": value, "confirmation_status": "unconfirmed"}


def _to_profile_input(output: ProfileImportOutput) -> dict[str, object]:
    used: set[UUID] = set()

    def identifier(value: UUID) -> str:
        if value in used:
            value = uuid4()
        used.add(value)
        return str(value)

    return {
        "basic_information": {
            "display_name": _fact(output.basic_information.display_name.value.strip()),
            "current_location": _fact(output.basic_information.current_location.value.strip()),
        },
        "preferences": {
            "target_locations": _fact(output.preferences.target_locations.value),
            "accepts_remote": _fact(output.preferences.accepts_remote.value),
            "target_roles": _fact(output.preferences.target_roles.value),
        },
        "education": [
            {
                "id": identifier(item.id),
                "school": _fact(item.school.value.strip()),
                "degree": _fact(item.degree.value.strip()),
                "major": _fact(item.major.value.strip()),
                "start_date": _fact(item.start_date.value),
                "end_date": _fact(item.end_date.value),
            }
            for item in output.education
        ],
        "experiences": [
            {
                "id": identifier(item.id),
                "company": _fact(item.company.value.strip()),
                "job_title": _fact(item.job_title.value.strip()),
                "start_date": _fact(item.start_date.value),
                "end_date": _fact(item.end_date.value),
                "responsibilities": _fact(item.responsibilities.value),
                "achievements": _fact(item.achievements.value),
            }
            for item in output.experiences
        ],
        "skills": [
            {
                "id": identifier(item.id),
                "name": _fact(item.name.value.strip()),
                "proficiency": _fact(
                    item.proficiency.value.strip() if item.proficiency.value else None
                ),
                "years": _fact(item.years.value),
            }
            for item in output.skills
        ],
    }


__all__ = ("ProfileImportAgent", "ProfileImportOutput", "PROFILE_IMPORT_PROMPT_VERSION")
