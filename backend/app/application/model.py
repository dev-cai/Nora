"""Minimal application path proving provider-neutral structured generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ports.model import ModelPort, ModelRequest

MODEL_PROBE_PROMPT_VERSION = "model-probe-v1"


class StructuredModelProbe(BaseModel):
    """Locally validated result used only by the explicit provider smoke."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    provider: Literal["dashscope-cn-beijing"]
    model: Literal["qwen3.8-max"]


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
    "MODEL_PROBE_PROMPT_VERSION",
    "StructuredModelProbe",
    "VerifyStructuredModelUseCase",
)
