"""Minimal application path proving provider-neutral structured generation."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ports.model import ModelPort, ModelRequest

MODEL_PROBE_PROMPT_VERSION = "model-probe-v1"
JOB_FIT_PROMPT_VERSION = "job-fit-v1"


class StructuredModelProbe(BaseModel):
    """Locally validated result used only by the explicit provider smoke."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    provider: Literal["dashscope-cn-beijing"]
    model: Literal["qwen3.8-max"]


class StructuredJobFitCitation(BaseModel):
    """One model-selected pointer copied from the fixed evidence catalog."""

    model_config = ConfigDict(extra="forbid")

    citation_id: Annotated[str, Field(min_length=1, max_length=100)]
    source: Literal[
        "candidate_profile",
        "resume_version",
        "job_posting",
        "job_requirement_snapshot",
        "decision_report",
        "company_snapshot",
    ]
    object_id: UUID
    version: Annotated[int, Field(ge=1)]
    field_path: Annotated[str, Field(min_length=1, max_length=500)]


class StructuredJobFitInsight(BaseModel):
    """A model inference or recommendation that must carry fixed-input citations."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=1_000)]
    citation_ids: Annotated[list[str], Field(min_length=1, max_length=20)]


class StructuredJobFitAnalysis(BaseModel):
    """Strict model output; it cannot represent or overwrite confirmed facts."""

    model_config = ConfigDict(extra="forbid")

    overall_fit: Literal["strong", "moderate", "weak", "unknown"]
    overall_fit_reason: StructuredJobFitInsight
    strong_matches: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    transferable_evidence: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    critical_gaps: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    non_blocking_gaps: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    resume_actions: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    project_deep_dive_risks: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    interview_focus: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    unknowns: Annotated[list[StructuredJobFitInsight], Field(max_length=20)]
    citations: Annotated[list[StructuredJobFitCitation], Field(min_length=1, max_length=100)]


class VerifyStructuredModelUseCase:
    """Execute one fixed, non-sensitive structured request without business writes."""

    def __init__(self, model: ModelPort) -> None:
        self._model = model

    async def execute(self) -> StructuredModelProbe:
        request = ModelRequest(
            system_prompt=(
                "You are a connectivity probe. Return the requested schema exactly. "
                "Do not add commentary."
            ),
            user_input=(
                "Return status ready, provider dashscope-cn-beijing, and model qwen3.8-max."
            ),
            prompt_version=MODEL_PROBE_PROMPT_VERSION,
            max_input_tokens=1_024,
            max_output_tokens=64,
            temperature=0,
        )
        return await self._model.generate_structured(request, StructuredModelProbe)


__all__ = (
    "JOB_FIT_PROMPT_VERSION",
    "MODEL_PROBE_PROMPT_VERSION",
    "StructuredJobFitAnalysis",
    "StructuredJobFitCitation",
    "StructuredJobFitInsight",
    "StructuredModelProbe",
    "VerifyStructuredModelUseCase",
)
