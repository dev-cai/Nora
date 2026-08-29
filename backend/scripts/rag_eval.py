#!/usr/bin/env python3
"""Run the frozen, offline RAG retrieval baseline without external services."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.application.knowledge.retrieval import (  # noqa: E402
    RRF_CONSTANT,
    UNKNOWN_SCORE_THRESHOLD,
    eligible,
    lexical_score,
    reciprocal_rank_fusion,
    tokenize,
)

FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "rag_eval_v1.json"
DEFAULT_OUTPUT = ROOT / "backend" / "tests" / "fixtures" / "rag_eval_v1.results.json"


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _tokens(value: str) -> Counter[str]:
    return tokenize(value)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    denominator = math.sqrt(
        sum(value * value for value in left) * sum(value * value for value in right)
    )
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0
    )


def _lexical(query: Counter[str], text: Counter[str]) -> float:
    return lexical_score(query, text)


def _rrf(
    vector_ranked: list[tuple[dict[str, Any], float]],
    lexical_ranked: list[tuple[dict[str, Any], float]],
    *,
    constant: int = RRF_CONSTANT,
) -> list[tuple[dict[str, Any], float]]:
    """Fuse two deterministic eligible rankings for offline evaluation."""
    vector_ranked = eligible(vector_ranked)
    lexical_ranked = eligible(lexical_ranked)
    fused = reciprocal_rank_fusion(
        (vector_ranked, lexical_ranked), item_key=lambda item: item["id"], constant=constant
    )
    return sorted(fused, key=lambda pair: (-pair[1], pair[0]["ordinal"], pair[0]["id"]))


async def evaluate(fixture: dict[str, Any]) -> dict[str, Any]:
    from app.infrastructure.embedding import DeterministicEmbeddingAdapter

    adapter = DeterministicEmbeddingAdapter()
    chunks = fixture["chunks"]
    chunk_embeddings = {item["id"]: await adapter.embed(item["text"]) for item in chunks}
    chunk_tokens = {item["id"]: _tokens(item["text"]) for item in chunks}
    ks = tuple(fixture["parameters"]["ks"])
    threshold = float(fixture["parameters"]["unknown_score_threshold"])
    if threshold != UNKNOWN_SCORE_THRESHOLD:
        raise ValueError("fixture threshold must match the controlled retrieval policy")
    rows: list[dict[str, Any]] = []
    for query in fixture["queries"]:
        candidates = [
            item
            for item in chunks
            if item["owner"] == query["owner"]
            and not item["deleted"]
            and (
                query.get("source_id_filter") is None
                or item["source_id"] == query["source_id_filter"]
            )
            and (
                query.get("source_version_filter") is None
                or item["source_version"] == query["source_version_filter"]
            )
        ]
        started = time.perf_counter_ns()
        vector_query = await adapter.embed(query["query"])
        vector_ranked = sorted(
            ((item, _cosine(vector_query, chunk_embeddings[item["id"]])) for item in candidates),
            key=lambda pair: (-pair[1], pair[0]["ordinal"], pair[0]["id"]),
        )
        vector_elapsed_us = (time.perf_counter_ns() - started) / 1000
        started = time.perf_counter_ns()
        lexical_query = _tokens(query["query"])
        lexical_ranked = sorted(
            ((item, _lexical(lexical_query, chunk_tokens[item["id"]])) for item in candidates),
            key=lambda pair: (-pair[1], pair[0]["ordinal"], pair[0]["id"]),
        )
        lexical_elapsed_us = (time.perf_counter_ns() - started) / 1000
        vector_eligible = eligible(vector_ranked, threshold=threshold)
        lexical_eligible = eligible(lexical_ranked, threshold=threshold)
        started = time.perf_counter_ns()
        hybrid_ranked = _rrf(vector_eligible, lexical_eligible, constant=RRF_CONSTANT)
        fusion_elapsed_us = (time.perf_counter_ns() - started) / 1000
        hybrid_elapsed_us = vector_elapsed_us + lexical_elapsed_us + fusion_elapsed_us
        relevant = set(query["relevant_chunk_ids"])
        row: dict[str, Any] = {
            "id": query["id"],
            "expected_unknown": bool(query.get("expected_unknown", not relevant)),
            "relevant_chunk_ids": sorted(relevant),
            "filters": {
                "owner": query["owner"],
                "source_id": query.get("source_id_filter"),
                "source_version": query.get("source_version_filter"),
            },
            "vector": {
                "latency_us": round(vector_elapsed_us, 2),
                "top": [
                    {"chunk_id": item["id"], "score": round(score, 6)}
                    for item, score in vector_ranked[: max(ks)]
                ],
            },
            "lexical": {
                "latency_us": round(lexical_elapsed_us, 2),
                "top": [
                    {"chunk_id": item["id"], "score": round(score, 6)}
                    for item, score in lexical_ranked[: max(ks)]
                ],
            },
            "hybrid": {
                "latency_us": round(hybrid_elapsed_us, 2),
                "top": [
                    {"chunk_id": item["id"], "score": round(score, 6)}
                    for item, score in hybrid_ranked[: max(ks)]
                ],
            },
        }
        rows.append(row)

    metrics: dict[str, Any] = {}
    for name in ("vector", "lexical", "hybrid"):
        method_metrics: dict[str, Any] = {}
        for k in ks:
            hits = []
            recalls = []
            precisions = []
            for row in rows:
                relevant = set(row["relevant_chunk_ids"])
                top = [
                    item["chunk_id"]
                    for item in row[name]["top"][:k]
                    if name == "hybrid" or item["score"] >= threshold
                ]
                if not relevant:
                    continue
                overlap = relevant & set(top)
                hits.append(bool(overlap))
                recalls.append(len(overlap) / len(relevant))
                precisions.append(len(overlap) / len(top) if top else 0.0)
            method_metrics[f"hit@{k}"] = round(sum(hits) / len(hits), 4) if hits else 0.0
            method_metrics[f"recall@{k}"] = (
                round(sum(recalls) / len(recalls), 4) if recalls else 0.0
            )
            method_metrics[f"citation_precision@{k}"] = (
                round(sum(precisions) / len(precisions), 4) if precisions else 0.0
            )
        unknown_rows = [row for row in rows if row["expected_unknown"]]
        false_positives = sum(
            bool(
                [
                    item
                    for item in row[name]["top"]
                    if name == "hybrid" or item["score"] >= threshold
                ]
            )
            for row in unknown_rows
        )
        method_metrics["unknown_false_positive_rate"] = round(
            false_positives / len(unknown_rows), 4
        )
        method_metrics["mean_latency_us"] = round(
            sum(row[name]["latency_us"] for row in rows) / len(rows), 2
        )
        method_metrics["cost_usd"] = 0.0
        method_metrics["cost_assumption"] = (
            "deterministic local computation; no external provider cost"
        )
        method_metrics["failure_cases"] = [
            row["id"]
            for row in rows
            if row["relevant_chunk_ids"]
            and not set(row["relevant_chunk_ids"])
            & {
                item["chunk_id"]
                for item in row[name]["top"][:5]
                if name == "hybrid" or item["score"] >= threshold
            }
        ]
        metrics[name] = method_metrics

    vector = metrics["vector"]
    hybrid = metrics["hybrid"]
    vector_passes = vector["hit@5"] >= 0.8 and vector["unknown_false_positive_rate"] <= 0.1
    hybrid_passes = hybrid["hit@5"] >= 0.8 and hybrid["unknown_false_positive_rate"] <= 0.1
    lexical_complement = sum(
        1
        for row in rows
        if set(item["chunk_id"] for item in row["lexical"]["top"][:5] if item["score"] >= threshold)
        & set(row["relevant_chunk_ids"])
        and not set(
            item["chunk_id"] for item in row["vector"]["top"][:5] if item["score"] >= threshold
        )
        & set(row["relevant_chunk_ids"])
    )
    evaluation_candidate = (
        "Vector-only" if vector_passes else ("Hybrid" if lexical_complement else "none")
    )
    return {
        "schema_version": fixture["schema_version"],
        "dataset_version": fixture["dataset_version"],
        "embedding": fixture["embedding"],
        "parameters": fixture["parameters"],
        "query_count": len(rows),
        "positive_query_count": sum(bool(row["relevant_chunk_ids"]) for row in rows),
        "negative_query_count": sum(not bool(row["relevant_chunk_ids"]) for row in rows),
        "metrics": metrics,
        "decision": {
            "evaluation_candidate": evaluation_candidate,
            "vector_passes_threshold": vector_passes,
            "hybrid_passes_threshold": hybrid_passes,
            "hybrid_admission": "PASS" if hybrid_passes else "FAIL",
            "online": "not shipped" if not hybrid_passes else "eligible for controlled review",
            "lexical_complementary_positive_queries": lexical_complement,
            "reranker": "not evaluated; out of scope for A-04",
        },
        "failures": [
            {
                "query_id": row["id"],
                "expected": row["relevant_chunk_ids"],
                "vector_top5": row["vector"]["top"][:5],
                "lexical_top5": row["lexical"]["top"][:5],
            }
            for row in rows
            if row["relevant_chunk_ids"]
            and not set(row["relevant_chunk_ids"])
            & {item["chunk_id"] for item in row["vector"]["top"][:5] if item["score"] >= threshold}
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    import asyncio

    result = asyncio.run(evaluate(load_fixture(args.fixture)))
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["decision"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
