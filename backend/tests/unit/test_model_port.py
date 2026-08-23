"""ModelPort, DashScope adapter, budget, retry and redaction tests."""

import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
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
    DASHSCOPE_CHAT_MODEL,
    DashScopeChatAdapter,
    FakeModelAdapter,
    create_dashscope_chat_adapter,
    create_model_adapter,
)
from app.ports.model import ModelError, ModelRequest
from pydantic import BaseModel, ConfigDict

API_KEY = "dashscope-test-secret"
WORKSPACE_ID = "ws-test123"


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
    request_budget: Decimal = Decimal("0.50"),
    timeout_seconds: float = 1,
) -> DashScopeChatAdapter:
    return DashScopeChatAdapter(
        api_key=api_key,
        workspace_id=WORKSPACE_ID,
        timeout_seconds=timeout_seconds,
        input_price_cny_per_million_tokens=Decimal("12"),
        output_price_cny_per_million_tokens=Decimal("36"),
        request_budget_cny=request_budget,
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
                "provider": "dashscope-cn-beijing",
                "model": "qwen3.8-max",
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
    assert captured["url"] == (
        f"https://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == DASHSCOPE_CHAT_MODEL
    assert payload["enable_thinking"] is False
    assert payload["response_format"]["type"] == "json_schema"  # type: ignore[index]
    assert payload["response_format"]["json_schema"]["strict"] is True  # type: ignore[index]
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
async def test_adapter_rejects_missing_workspace_before_network() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    adapter = DashScopeChatAdapter(
        api_key=API_KEY,
        workspace_id="",
        timeout_seconds=1,
        input_price_cny_per_million_tokens=Decimal("12"),
        output_price_cny_per_million_tokens=Decimal("36"),
        request_budget_cny=Decimal("0.50"),
        transport=httpx.MockTransport(handler),
        retry_base_delay_seconds=0,
    )
    with pytest.raises(ModelError) as error:
        await adapter.generate_structured(_request(), SkillExtraction)

    assert error.value.error_code is ErrorCode.MODEL_NOT_CONFIGURED
    assert called is False


def test_adapter_rejects_workspace_id_that_could_change_endpoint() -> None:
    with pytest.raises(ValueError, match="workspace_id"):
        DashScopeChatAdapter(
            api_key=API_KEY,
            workspace_id="attacker.example/path",
            timeout_seconds=1,
            input_price_cny_per_million_tokens=Decimal("12"),
            output_price_cny_per_million_tokens=Decimal("36"),
            request_budget_cny=Decimal("0.50"),
        )


def test_adapter_rejects_direct_budget_or_price_bypass() -> None:
    with pytest.raises(ValueError, match="input price"):
        DashScopeChatAdapter(
            api_key=API_KEY,
            workspace_id=WORKSPACE_ID,
            timeout_seconds=1,
            input_price_cny_per_million_tokens=Decimal("11.99"),
            output_price_cny_per_million_tokens=Decimal("36"),
            request_budget_cny=Decimal("0.50"),
        )
    with pytest.raises(ValueError, match="request budget"):
        DashScopeChatAdapter(
            api_key=API_KEY,
            workspace_id=WORKSPACE_ID,
            timeout_seconds=1,
            input_price_cny_per_million_tokens=Decimal("12"),
            output_price_cny_per_million_tokens=Decimal("36"),
            request_budget_cny=Decimal("0.51"),
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
async def test_adapter_rejects_cost_over_budget_before_network() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    with pytest.raises(ModelError) as error:
        await _adapter(handler, request_budget=Decimal("0.000001")).generate_structured(
            _request(), SkillExtraction
        )

    assert error.value.error_code is ErrorCode.MODEL_BUDGET_EXCEEDED
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
    assert records[-1]["provider"] == "dashscope-cn-beijing"
    assert records[-1]["model"] == DASHSCOPE_CHAT_MODEL
    assert records[-1]["success"] is False
    assert API_KEY not in stream.getvalue()
    assert sensitive_prompt not in stream.getvalue()


def test_factory_uses_validated_settings_without_requiring_model_configuration() -> None:
    settings = Settings(_env_file=None)

    adapter = create_dashscope_chat_adapter(settings)

    assert isinstance(adapter, DashScopeChatAdapter)


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
                "provider": "dashscope-cn-beijing",
                "model": "qwen3.8-max",
                "unexpected": True,
            }
        )
