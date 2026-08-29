import httpx
import pytest
from app.domain.base.exceptions import ErrorCode
from app.infrastructure.embedding import (
    QWEN_EMBEDDING_DIMENSION,
    QWEN_EMBEDDING_MODEL,
    QWEN_EMBEDDING_REGION,
    QwenEmbeddingAdapter,
)
from app.ports.model import ModelError


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_qwen_adapter_posts_fixed_contract_and_validates_vector() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["json"] = request.read().decode()
        return httpx.Response(200, json={"data": [{"embedding": [0.5] * QWEN_EMBEDDING_DIMENSION}]})

    adapter = QwenEmbeddingAdapter(
        api_key="secret-value",
        workspace_id="workspace",
        timeout_seconds=5,
        transport=_transport(handler),
        retry_base_delay_seconds=0,
    )
    vector = await adapter.embed("query text")
    assert len(vector) == QWEN_EMBEDDING_DIMENSION
    assert QWEN_EMBEDDING_MODEL in seen["json"]
    assert seen["url"].endswith(
        f".{QWEN_EMBEDDING_REGION}.maas.aliyuncs.com/compatible-mode/v1/embeddings"
    )
    assert seen["auth"] == "Bearer secret-value"
    assert "query text" in seen["json"]


@pytest.mark.asyncio
async def test_qwen_adapter_missing_secret_is_stable_failure() -> None:
    adapter = QwenEmbeddingAdapter(api_key="", workspace_id="workspace", timeout_seconds=5)
    with pytest.raises(ModelError) as error:
        await adapter.embed("text")
    assert error.value.error_code is ErrorCode.MODEL_NOT_CONFIGURED


@pytest.mark.asyncio
@pytest.mark.parametrize("embedding", ([0.1], [float("nan")] * QWEN_EMBEDDING_DIMENSION))
async def test_qwen_adapter_rejects_invalid_shape_or_non_finite_values(embedding) -> None:
    adapter = QwenEmbeddingAdapter(
        api_key="key",
        workspace_id="workspace",
        timeout_seconds=5,
        transport=_transport(
            lambda _request: httpx.Response(
                200, json={"data": [{"embedding": [0.1] * QWEN_EMBEDDING_DIMENSION}]}
            )
        ),
        retry_base_delay_seconds=0,
    )
    with pytest.raises(ModelError) as error:
        adapter._validated_vector({"data": [{"embedding": embedding}]})
    assert error.value.error_code is ErrorCode.MODEL_OUTPUT_INVALID


@pytest.mark.asyncio
async def test_qwen_adapter_retries_server_failure_once() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return (
            httpx.Response(503)
            if calls == 1
            else httpx.Response(
                200, json={"data": [{"embedding": [0.1] * QWEN_EMBEDDING_DIMENSION}]}
            )
        )

    adapter = QwenEmbeddingAdapter(
        api_key="key",
        workspace_id="workspace",
        timeout_seconds=5,
        transport=_transport(handler),
        retry_base_delay_seconds=0,
    )
    await adapter.embed("text")
    assert calls == 2
