"""Provider-neutral structured model generation contract."""

from dataclasses import dataclass
from re import fullmatch
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.domain.base.exceptions import ErrorCode, NoraError

MAX_MODEL_PROMPT_CHARS = 100_000
MAX_MODEL_INPUT_TOKENS = 32_768
MAX_MODEL_OUTPUT_TOKENS = 8_192

ModelOutputT = TypeVar("ModelOutputT", bound=BaseModel)


class ModelError(NoraError):
    """Stable failure raised before a model result can enter application logic."""

    def __init__(self, message: str, error_code: ErrorCode) -> None:
        super().__init__(message, error_code=error_code)


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Versioned prompt and bounded model parameters owned by an application use case."""

    system_prompt: str
    user_input: str
    prompt_version: str
    max_input_tokens: int
    max_output_tokens: int
    temperature: float = 0.0

    def __post_init__(self) -> None:
        system_prompt = self.system_prompt.strip()
        user_input = self.user_input.strip()
        prompt_version = self.prompt_version.strip()
        if not system_prompt or not user_input:
            raise ValueError("model prompts must not be empty")
        if len(system_prompt) + len(user_input) > MAX_MODEL_PROMPT_CHARS:
            raise ValueError("model prompts exceed the application limit")
        if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", prompt_version) is None:
            raise ValueError("prompt_version must be a stable 1-64 character identifier")
        if not 1 <= self.max_input_tokens <= MAX_MODEL_INPUT_TOKENS:
            raise ValueError("max_input_tokens is outside the supported range")
        if not 1 <= self.max_output_tokens <= MAX_MODEL_OUTPUT_TOKENS:
            raise ValueError("max_output_tokens is outside the supported range")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(self, "user_input", user_input)
        object.__setattr__(self, "prompt_version", prompt_version)


@runtime_checkable
class ModelPort(Protocol):
    """Minimal structured-output model boundary used by application services."""

    async def generate_structured(
        self,
        request: ModelRequest,
        output_type: type[ModelOutputT],
    ) -> ModelOutputT: ...


__all__ = ("ModelError", "ModelOutputT", "ModelPort", "ModelRequest")
