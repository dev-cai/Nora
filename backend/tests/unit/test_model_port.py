"""ModelPort, DeepSeek adapter, token limit, retry and redaction tests."""

import asyncio
import json
from collections.abc import Callable
from io import StringIO

import httpx
import pytest
from app.application.model import (
    MODEL_PROBE_PROMPT_VERSION,
    StructuredModelProbe,
    VerifyStructuredModelUseCase,
)
from app.domain.base.exceptions import ErrorCode
from app.infrastructure.config import LogFormat, Settings
from app.infrastructure.logging import configure_logging
from app.infrastructure.model import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    DeepSeekChatAdapter,
    FakeModelAdapter,
    create_deepseek_chat_adapter,
)
from app.ports.model import ModelError, ModelRequest
from pydantic import BaseModel, ConfigDict

API_KEY = "deepseek-test-secret"


class SkillExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[str]


class InvalidSchemaOutput(BaseModel):
    callback: Callable[[int], int]


def _request(**overrides: object) -> ModelRequest:
    values: dict[str, object] = {
        "system_prompt": "Extract only skills from the supplied data.",
        "user_input": "Python and FastAPI",
        "prompt_version": "skill-extraction-v1",
        "max_input_tokens": 1_024,
        "max_output_tokens": 64,
        "temperature": 0,
    }
    values.update(overrides)
    return ModelRequest(**values)  # type: ignore[arg-type]


def _adapter(
    handler,
    *,
    api_key: str = API_KEY,
    timeout_seconds: float = 1,
) -> DeepSeekChatAdapter:
    return DeepSeekChatAdapter(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_CHAT_MODEL,
        timeout_seconds=timeout_seconds,
        transport=httpx.MockTransport(handler),
        retry_base_delay_seconds=0,
    )


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"skills":["Python"]}'}}]},
    )


@pytest.mark.asyncio
async def test_fake_adapter_runs_versioned_application_probe() -> None:
    adapter = FakeModelAdapter(
        [
            {
                "status": "ready",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
            }
        ]
    )

    result = await VerifyStructuredModelUseCase(adapter).execute()

    assert result.status == "ready"
    assert adapter.requests[0].prompt_version == MODEL_PROBE_PROMPT_VERSION
    assert adapter.requests[0].temperature == 0


@pytest.mark.asyncio
async def test_adapter_sends_openai_compatible_json_schema_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return _success_response()

    result = await _adapter(handler).generate_structured(_request(), SkillExtraction)

    assert result == SkillExtraction(skills=["Python"])
    assert captured["authorization"] == f"Bearer {API_KEY}"
    assert captured["url"] == ("https://api.deepseek.com/v1/chat/completions")
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == DEEPSEEK_CHAT_MODEL
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"]["type"] == "json_object"  # type: ignore[index]
    assert "JSON Schema" in payload["messages"][0]["content"]  # type: ignore[index]
    assert payload["messages"][0]["role"] == "system"  # type: ignore[index]
    assert payload["messages"][1]["role"] == "user"  # type: ignore[index]


@pytest.mark.asyncio
async def test_adapter_retries_one_transient_failure_then_succeeds() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return _success_response()

    result = await _adapter(handler).generate_structured(_request(), SkillExtraction)

    assert result.skills == ["Python"]
    assert attempts == 2


@pytest.mark.asyncio
async def test_adapter_retries_timeout_only_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("sensitive upstream detail", request=request)

    with pytest.raises(ModelError) as error:
        await _adapter(handler).generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_TIMEOUT
    assert attempts == 2
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_adapter_timeout_is_one_wall_clock_budget_across_retries() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.07)
        if attempts == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return _success_response()

    with pytest.raises(ModelError) as error:
        await _adapter(handler, timeout_seconds=0.1).generate_structured(
            _request(), SkillExtraction
        )

    assert error.value.error_code is ErrorCode.MODEL_TIMEOUT
    assert attempts == 2


@pytest.mark.asyncio
async def test_adapter_does_not_retry_non_transient_provider_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": f"rejected {API_KEY}"})

    with pytest.raises(ModelError) as error:
        await _adapter(handler).generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_PROVIDER_FAILED
    assert attempts == 1
    assert API_KEY not in error.value.message


@pytest.mark.asyncio
async def test_adapter_rejects_invalid_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"unknown":true}'}}]},
        )

    with pytest.raises(ModelError) as error:
        await _adapter(handler).generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_OUTPUT_INVALID


@pytest.mark.asyncio
async def test_adapter_rejects_missing_credentials_before_network() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    with pytest.raises(ModelError) as error:
        await _adapter(handler, api_key="").generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_NOT_CONFIGURED
    assert called is False


@pytest.mark.asyncio
async def test_adapter_rejects_missing_api_key_before_network() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    adapter = DeepSeekChatAdapter(
        api_key="",
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_CHAT_MODEL,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
        retry_base_delay_seconds=0,
    )
    with pytest.raises(ModelError) as error:
        await adapter.generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_NOT_CONFIGURED
    assert called is False


def test_adapter_rejects_base_url_that_could_change_endpoint() -> None:
    with pytest.raises(ValueError, match="base_url"):
        DeepSeekChatAdapter(
            api_key=API_KEY,
            base_url="https://attacker.example/path",
            model=DEEPSEEK_CHAT_MODEL,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_adapter_maps_unrepresentable_schema_without_network() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    with pytest.raises(ModelError) as error:
        await _adapter(handler).generate_structured(_request(), InvalidSchemaOutput)

    assert error.value.error_code is ErrorCode.MODEL_OUTPUT_INVALID
    assert called is False


@pytest.mark.asyncio
async def test_adapter_rejects_input_larger_than_declared_token_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response()

    with pytest.raises(ModelError) as error:
        await _adapter(handler).generate_structured(
            _request(user_input="敏感正文" * 100, max_input_tokens=16),
            SkillExtraction,
        )

    assert error.value.error_code is ErrorCode.MODEL_BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_model_logs_never_include_secret_or_prompt_content() -> None:
    stream = StringIO()
    configure_logging(Settings(log_format=LogFormat.JSON, _env_file=None), stream=stream)
    sensitive_prompt = "private-candidate-content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": f"{API_KEY} {sensitive_prompt}"})

    with pytest.raises(ModelError):
        await _adapter(handler).generate_structured(
            _request(user_input=sensitive_prompt),
            SkillExtraction,
        )

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.startswith("{")]
    assert records[-1]["provider"] == "deepseek"
    assert records[-1]["model"] == DEEPSEEK_CHAT_MODEL
    assert records[-1]["success"] is False
    assert API_KEY not in stream.getvalue()
    assert sensitive_prompt not in stream.getvalue()


def test_factory_uses_validated_settings_without_requiring_model_configuration() -> None:
    settings = Settings(_env_file=None)

    adapter = create_deepseek_chat_adapter(settings)

    assert isinstance(adapter, DeepSeekChatAdapter)
    assert adapter.model == settings.deepseek_chat_model


@pytest.mark.asyncio
async def test_adapter_no_longer_applies_cost_preflight() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    # A request at the model input/output ceiling would previously have exceeded
    # the reviewed 0.50 CNY per-request cost precheck; the cost check is removed.
    result = await _adapter(handler).generate_structured(
        _request(max_input_tokens=32_768, max_output_tokens=8_192),
        SkillExtraction,
    )

    assert result == SkillExtraction(skills=["Python"])
    assert called is True


def test_model_request_rejects_unversioned_or_unbounded_inputs() -> None:
    with pytest.raises(ValueError, match="prompt_version"):
        _request(prompt_version="invalid version")
    with pytest.raises(ValueError, match="max_output_tokens"):
        _request(max_output_tokens=0)


@pytest.mark.asyncio
async def test_fake_adapter_validates_recorded_output_schema() -> None:
    adapter = FakeModelAdapter([{"unexpected": True}])

    with pytest.raises(ModelError) as error:
        await adapter.generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_OUTPUT_INVALID


def test_probe_schema_is_strict() -> None:
    with pytest.raises(Exception):
        StructuredModelProbe.model_validate(
            {
                "status": "ready",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "unexpected": True,
            }
        )
