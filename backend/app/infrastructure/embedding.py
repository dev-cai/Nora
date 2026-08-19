"""Deterministic local embedding adapter used until a reviewed remote adapter is enabled."""

import hashlib
import math


class DeterministicEmbeddingAdapter:
    """Stable dense vectors make the RAG path testable without external credentials."""

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


__all__ = ("DeterministicEmbeddingAdapter",)
