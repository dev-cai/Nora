"""DeepSeek OpenAI-compatible adapter for structured Chat Completions."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Iterable
from decimal import Decimal
from re import fullmatch
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from pydantic.errors import PydanticUserError

from app.domain.base.exceptions import ERROR_CATEGORY_BY_CODE, ErrorCode
from app.infrastructure.config import Settings
from app.infrastructure.logging import get_logger
from app.ports.model import ModelError, ModelOutputT, ModelPort, ModelRequest

DEEPSEEK_CHAT_MODEL = "deepseek-v4-flash"
DEEPSEEK_PROVIDER = "deepseek"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_MAX_ATTEMPTS = 2
_MIN_INPUT_PRICE = Decimal("12")
_MIN_OUTPUT_PRICE = Decimal("36")
_MAX_REQUEST_BUDGET = Decimal("0.50")


class DeepSeekChatAdapter(ModelPort):
    """Call the architecture-approved model and validate its JSON response locally."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        input_price_cny_per_million_tokens: Decimal,
        output_price_cny_per_million_tokens: Decimal,
        request_budget_cny: Decimal,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_base_delay_seconds: float = 0.2,
    ) -> None:
        self._api_key = api_key
        if base_url != DEEPSEEK_BASE_URL:
            raise ValueError("base_url must be https://api.deepseek.com")
        if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model) is None:
            raise ValueError("model must be a stable model identifier")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0 and 60")
        if (
            not input_price_cny_per_million_tokens.is_finite()
            or input_price_cny_per_million_tokens < _MIN_INPUT_PRICE
        ):
            raise ValueError("input price must not be below the reviewed price")
        if (
            not output_price_cny_per_million_tokens.is_finite()
            or output_price_cny_per_million_tokens < _MIN_OUTPUT_PRICE
        ):
            raise ValueError("output price must not be below the reviewed price")
        if not request_budget_cny.is_finite() or not 0 < request_budget_cny <= _MAX_REQUEST_BUDGET:
            raise ValueError("request budget must be between 0 and 0.50 CNY")
        if retry_base_delay_seconds < 0:
            raise ValueError("retry delay must not be negative")
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._input_price = input_price_cny_per_million_tokens
        self._output_price = output_price_cny_per_million_tokens
        self._request_budget = request_budget_cny
        self._transport = transport
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._logger = get_logger(__name__)

    @property
    def provider(self) -> str:
        return DEEPSEEK_PROVIDER

    @property
    def model(self) -> str:
        return self._model

    async def generate_structured(
        self,
        request: ModelRequest,
        output_type: type[ModelOutputT],
    ) -> ModelOutputT:
        started_at = perf_counter()
        try:
            self._validate_output_type(output_type)
            request_payload = _chat_payload(request, output_type, self._model)
            self._validate_preflight(request, request_payload)
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    payload = await self._request_with_retry(request_payload)
            except TimeoutError:
                raise ModelError(
                    "Model provider timed out",
                    ErrorCode.MODEL_TIMEOUT,
                ) from None
            result = self._validated_output(payload, output_type)
        except ModelError as exc:
            self._log_result(
                started_at,
                success=False,
                error_category=ERROR_CATEGORY_BY_CODE[exc.error_code].value,
            )
            raise
        self._log_result(started_at, success=True, error_category=None)
        return result

    def _validate_output_type(self, output_type: type[ModelOutputT]) -> None:
        if not isinstance(output_type, type) or not issubclass(output_type, BaseModel):
            raise ModelError(
                "Structured output type is invalid",
                ErrorCode.MODEL_OUTPUT_INVALID,
            )

    def _validate_preflight(
        self,
        request: ModelRequest,
        request_payload: dict[str, Any],
    ) -> None:
        if not self._api_key:
            raise ModelError(
                "Model provider is not configured",
                ErrorCode.MODEL_NOT_CONFIGURED,
            )
        estimated_tokens = _conservative_token_estimate(
            json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
        )
        if estimated_tokens > request.max_input_tokens:
            raise ModelError(
                "Model input exceeds its declared token budget",
                ErrorCode.MODEL_BUDGET_EXCEEDED,
            )
        estimated_cost = (
            Decimal(request.max_input_tokens) * self._input_price
            + Decimal(request.max_output_tokens) * self._output_price
        ) / Decimal(1_000_000)
        if estimated_cost > self._request_budget:
            raise ModelError(
                "Model request exceeds the configured cost budget",
                ErrorCode.MODEL_BUDGET_EXCEEDED,
            )

    async def _request_with_retry(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout_seconds,
            trust_env=False,
        ) as client:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    response = await client.post(
                        _chat_completions_url(self._base_url),
                        headers=headers,
                        json=request_payload,
                    )
                except (TimeoutError, httpx.TimeoutException):
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Model provider timed out",
                        ErrorCode.MODEL_TIMEOUT,
                    ) from None
                except httpx.RequestError:
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Model provider is unavailable",
                        ErrorCode.MODEL_PROVIDER_UNAVAILABLE,
                    ) from None

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Model provider is unavailable",
                        ErrorCode.MODEL_PROVIDER_UNAVAILABLE,
                    )
                if response.status_code >= 400:
                    raise ModelError(
                        "Model provider rejected the request",
                        ErrorCode.MODEL_PROVIDER_FAILED,
                    )
                try:
                    payload = response.json()
                except ValueError:
                    raise ModelError(
                        "Model provider returned an invalid response",
                        ErrorCode.MODEL_OUTPUT_INVALID,
                    ) from None
                if not isinstance(payload, dict):
                    raise ModelError(
                        "Model provider returned an invalid response",
                        ErrorCode.MODEL_OUTPUT_INVALID,
                    )
                return payload
        raise AssertionError("model retry loop must return or raise")

    async def _retry_delay(self) -> None:
        if self._retry_base_delay_seconds <= 0:
            return
        jitter = random.uniform(0.5, 1.5)
        await asyncio.sleep(self._retry_base_delay_seconds * jitter)

    def _validated_output(
        self,
        payload: dict[str, Any],
        output_type: type[ModelOutputT],
    ) -> ModelOutputT:
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            return output_type.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValidationError, ValueError):
            raise ModelError(
                "Model provider returned output that failed schema validation",
                ErrorCode.MODEL_OUTPUT_INVALID,
            ) from None

    def _log_result(
        self,
        started_at: float,
        *,
        success: bool,
        error_category: str | None,
    ) -> None:
        self._logger.info(
            "model generation completed",
            provider=DEEPSEEK_PROVIDER,
            model=self._model,
            duration_ms=round((perf_counter() - started_at) * 1000),
            success=success,
            error_category=error_category,
        )


class FakeModelAdapter(ModelPort):
    """Deterministic adapter for application tests without network or credentials."""

    def __init__(self, responses: Iterable[BaseModel | dict[str, Any]]) -> None:
        self._responses = iter(responses)
        self.requests: list[ModelRequest] = []

    @property
    def provider(self) -> str:
        return DEEPSEEK_PROVIDER

    @property
    def model(self) -> str:
        return DEEPSEEK_CHAT_MODEL

    async def generate_structured(
        self,
        request: ModelRequest,
        output_type: type[ModelOutputT],
    ) -> ModelOutputT:
        self.requests.append(request)
        try:
            response = next(self._responses)
        except StopIteration:
            raise ModelError(
                "Fake model has no recorded response",
                ErrorCode.MODEL_PROVIDER_FAILED,
            ) from None
        try:
            if isinstance(response, BaseModel):
                response = response.model_dump()
            return output_type.model_validate(response)
        except ValidationError:
            raise ModelError(
                "Fake model output failed schema validation",
                ErrorCode.MODEL_OUTPUT_INVALID,
            ) from None


def create_deepseek_chat_adapter(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_base_delay_seconds: float = 0.2,
) -> DeepSeekChatAdapter:
    """Compose the real adapter exclusively from validated runtime settings."""

    return DeepSeekChatAdapter(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_chat_model,
        timeout_seconds=settings.deepseek_chat_timeout_seconds,
        input_price_cny_per_million_tokens=(
            settings.deepseek_chat_input_price_cny_per_million_tokens
        ),
        output_price_cny_per_million_tokens=(
            settings.deepseek_chat_output_price_cny_per_million_tokens
        ),
        request_budget_cny=settings.deepseek_chat_request_budget_cny,
        transport=transport,
        retry_base_delay_seconds=retry_base_delay_seconds,
    )


def create_model_adapter(settings: Settings) -> ModelPort:
    """Create the approved production adapter from validated settings."""

    return create_deepseek_chat_adapter(settings)


def _chat_payload(
    request: ModelRequest,
    output_type: type[ModelOutputT],
    model: str,
) -> dict[str, Any]:
    try:
        schema = output_type.model_json_schema()
    except (AttributeError, PydanticUserError, TypeError, ValueError):
        raise ModelError(
            "Structured output schema could not be generated",
            ErrorCode.MODEL_OUTPUT_INVALID,
        ) from None
    schema_name = output_type.__name__
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_input},
        ],
        "temperature": request.temperature,
        "max_tokens": request.max_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
    }


def _conservative_token_estimate(value: str) -> int:
    """Bound mixed Chinese/Latin input without logging or retaining its content."""

    return max(len(value), (len(value.encode("utf-8")) + 3) // 4)


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url}/v1/chat/completions"


__all__ = (
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_CHAT_MODEL",
    "DEEPSEEK_PROVIDER",
    "DeepSeekChatAdapter",
    "FakeModelAdapter",
    "create_model_adapter",
    "create_deepseek_chat_adapter",
)
