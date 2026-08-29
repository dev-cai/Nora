"""Deterministic retrieval policies shared by offline evaluation and RAG."""

from collections import Counter
from typing import Callable, TypeVar

Candidate = TypeVar("Candidate")

UNKNOWN_SCORE_THRESHOLD = 0.35
RRF_CONSTANT = 60


def tokenize(value: str) -> Counter[str]:
    """Tokenize English/alphanumeric terms and contiguous CJK runs."""

    import re

    return Counter(token.lower() for token in re.findall(r"[A-Za-z0-9_]+|[\u3400-\u9fff]+", value))


def lexical_score(query: Counter[str], text: Counter[str]) -> float:
    if not query or not text:
        return 0.0
    overlap = sum(min(query[token], text[token]) for token in query.keys() & text.keys())
    return overlap / sum(query.values())


def eligible(
    ranked: list[tuple[Candidate, float]],
    *,
    threshold: float = UNKNOWN_SCORE_THRESHOLD,
) -> list[tuple[Candidate, float]]:
    """Keep only candidates with retriever evidence above the unknown threshold."""

    return [(item, score) for item, score in ranked if score >= threshold]


def reciprocal_rank_fusion(
    ranked_lists: tuple[list[tuple[Candidate, float]], ...],
    *,
    item_key: Callable[[Candidate], object],
    constant: int = RRF_CONSTANT,
) -> list[tuple[Candidate, float]]:
    """Fuse eligible rankings; scores are used only for deterministic ordering."""

    scores: dict[object, float] = {}
    items: dict[object, Candidate] = {}
    for ranked in ranked_lists:
        for rank, (item, _score) in enumerate(ranked, start=1):
            item_id = item_key(item)
            items[item_id] = item
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (constant + rank)
    return sorted(
        ((items[item_id], score) for item_id, score in scores.items()),
        key=lambda pair: (-pair[1], str(item_key(pair[0]))),
    )


__all__ = (
    "RRF_CONSTANT",
    "UNKNOWN_SCORE_THRESHOLD",
    "eligible",
    "lexical_score",
    "reciprocal_rank_fusion",
    "tokenize",
)
