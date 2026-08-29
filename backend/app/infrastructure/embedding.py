"""Deterministic test fixture and reviewed Qwen embedding adapter."""

from __future__ import annotations

import asyncio
import hashlib
import math
import random
from re import fullmatch
from time import perf_counter
from typing import Any

import httpx

from app.domain.base.exceptions import ErrorCode
from app.infrastructure.config import Settings
from app.infrastructure.logging import get_logger
from app.ports.model import ModelError

QWEN_EMBEDDING_PROVIDER = "aliyun-bailian"
QWEN_EMBEDDING_MODEL = "qwen3.7-text-embedding"
QWEN_EMBEDDING_VERSION = "compatible-mode-v1"
QWEN_EMBEDDING_DIMENSION = 1024
QWEN_EMBEDDING_REGION = "cn-beijing"
_MAX_ATTEMPTS = 2


class DeterministicEmbeddingAdapter:
    """Stable dense vectors for tests and deterministic baseline evaluation only."""

    model = "nora-deterministic"
    version = "sha256-v1"
    dimension = 64

    async def embed(self, text: str) -> tuple[float, ...]:
        values: list[float] = []
        seed = text.encode("utf-8")
        for index in range(self.dimension):
            digest = hashlib.sha256(seed + index.to_bytes(2, "big")).digest()
            values.append((int.from_bytes(digest[:8], "big") / 2**63) - 1.0)
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)


class QwenEmbeddingAdapter:
    """Call the fixed Qwen embedding contract over the OpenAI-compatible API."""

    model = QWEN_EMBEDDING_MODEL
    version = QWEN_EMBEDDING_VERSION
    dimension = QWEN_EMBEDDING_DIMENSION

    def __init__(
        self,
        *,
        api_key: str,
        workspace_id: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_base_delay_seconds: float = 0.2,
    ) -> None:
        if workspace_id and fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", workspace_id) is None:
            raise ValueError("workspace_id must be a stable identifier")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0 and 60")
        if retry_base_delay_seconds < 0:
            raise ValueError("retry delay must not be negative")
        self._api_key = api_key
        self._workspace_id = workspace_id
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._logger = get_logger(__name__)

    @property
    def provider(self) -> str:
        return QWEN_EMBEDDING_PROVIDER

    @property
    def endpoint(self) -> str:
        return f"https://{self._workspace_id}.{QWEN_EMBEDDING_REGION}.maas.aliyuncs.com/compatible-mode/v1/embeddings"

    async def embed(self, text: str) -> tuple[float, ...]:
        normalized = text.strip()
        if not normalized:
            raise ModelError("Embedding input is empty", ErrorCode.EMPTY_CONTENT)
        if not self._api_key or not self._workspace_id:
            raise ModelError("Embedding provider is not configured", ErrorCode.MODEL_NOT_CONFIGURED)
        started_at = perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                payload = await self._request_with_retry(normalized)
            vector = self._validated_vector(payload)
        except TimeoutError:
            raise ModelError("Embedding provider timed out", ErrorCode.MODEL_TIMEOUT) from None
        self._logger.info(
            "embedding completed",
            provider=QWEN_EMBEDDING_PROVIDER,
            model=self.model,
            dimension=self.dimension,
            duration_ms=round((perf_counter() - started_at) * 1000),
            success=True,
            error_category=None,
        )
        return vector

    async def _request_with_retry(self, text: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        request_payload = {
            "model": self.model,
            "input": text,
            "dimensions": self.dimension,
            "encoding_format": "float",
        }
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout_seconds, trust_env=False
        ) as client:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    response = await client.post(
                        self.endpoint, headers=headers, json=request_payload
                    )
                except (TimeoutError, httpx.TimeoutException):
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Embedding provider timed out", ErrorCode.MODEL_TIMEOUT
                    ) from None
                except httpx.RequestError:
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Embedding provider is unavailable", ErrorCode.MODEL_PROVIDER_UNAVAILABLE
                    ) from None
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < _MAX_ATTEMPTS:
                        await self._retry_delay()
                        continue
                    raise ModelError(
                        "Embedding provider is unavailable", ErrorCode.MODEL_PROVIDER_UNAVAILABLE
                    )
                if response.status_code >= 400:
                    raise ModelError(
                        "Embedding provider rejected the request", ErrorCode.MODEL_PROVIDER_FAILED
                    )
                try:
                    payload = response.json()
                except ValueError:
                    raise ModelError(
                        "Embedding provider returned an invalid response",
                        ErrorCode.MODEL_OUTPUT_INVALID,
                    ) from None
                if not isinstance(payload, dict):
                    raise ModelError(
                        "Embedding provider returned an invalid response",
                        ErrorCode.MODEL_OUTPUT_INVALID,
                    )
                return payload
        raise AssertionError("embedding retry loop must return or raise")

    async def _retry_delay(self) -> None:
        if self._retry_base_delay_seconds > 0:
            await asyncio.sleep(self._retry_base_delay_seconds * random.uniform(0.5, 1.5))

    def _validated_vector(self, payload: dict[str, Any]) -> tuple[float, ...]:
        try:
            data = payload["data"]
            if not isinstance(data, list) or len(data) != 1:
                raise TypeError
            vector = data[0]["embedding"]
            if not isinstance(vector, list) or len(vector) != self.dimension:
                raise TypeError
            values = tuple(float(value) for value in vector)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            raise ModelError(
                "Embedding provider returned an invalid vector", ErrorCode.MODEL_OUTPUT_INVALID
            ) from None
        if not values or any(not math.isfinite(value) for value in values):
            raise ModelError(
                "Embedding provider returned an invalid vector", ErrorCode.MODEL_OUTPUT_INVALID
            )
        return values


def create_qwen_embedding_adapter(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    retry_base_delay_seconds: float = 0.2,
) -> QwenEmbeddingAdapter:
    return QwenEmbeddingAdapter(
        api_key=settings.embedding_api_key,
        workspace_id=settings.embedding_workspace_id,
        timeout_seconds=settings.embedding_timeout_seconds,
        transport=transport,
        retry_base_delay_seconds=retry_base_delay_seconds,
    )


__all__ = (
    "DeterministicEmbeddingAdapter",
    "QWEN_EMBEDDING_DIMENSION",
    "QWEN_EMBEDDING_MODEL",
    "QWEN_EMBEDDING_PROVIDER",
    "QWEN_EMBEDDING_REGION",
    "QWEN_EMBEDDING_VERSION",
    "QwenEmbeddingAdapter",
    "create_qwen_embedding_adapter",
)
