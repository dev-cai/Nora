import json
from pathlib import Path

import pytest
from scripts.rag_eval import _rrf, evaluate, load_fixture

FIXTURE = Path(__file__).parents[1] / "fixtures" / "rag_eval_v1.json"
RESULTS = FIXTURE.with_name("rag_eval_v1.results.json")


def test_frozen_fixture_is_synthetic_and_has_positive_and_negative_queries() -> None:
    fixture = load_fixture(FIXTURE)
    assert fixture["schema_version"] == "nora-rag-eval-v1"
    assert fixture["license"] == "synthetic"
    assert 20 <= len(fixture["chunks"]) <= 30
    assert 20 <= len(fixture["queries"]) <= 30
    assert any(query["relevant_chunk_ids"] for query in fixture["queries"])
    assert any(not query["relevant_chunk_ids"] for query in fixture["queries"])


@pytest.mark.asyncio
async def test_evaluation_is_repeatable_and_preserves_negative_filters() -> None:
    fixture = load_fixture(FIXTURE)
    first = await evaluate(fixture)
    second = await evaluate(fixture)
    assert first["schema_version"] == second["schema_version"]
    assert first["dataset_version"] == second["dataset_version"]
    for method in ("vector", "lexical"):
        first_metrics = {
            key: value
            for key, value in first["metrics"][method].items()
            if key != "mean_latency_us"
        }
        second_metrics = {
            key: value
            for key, value in second["metrics"][method].items()
            if key != "mean_latency_us"
        }
        assert first_metrics == second_metrics
    assert first["query_count"] == 28
    assert first["negative_query_count"] == 4
    assert first["decision"]["reranker"].startswith("not evaluated")
    assert first["metrics"]["vector"]["cost_usd"] == 0.0
    assert any(row["id"] == "q-go-cross-owner" for row in fixture["queries"])


def test_fixture_is_valid_json() -> None:
    json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rrf_is_deterministic_and_keeps_both_rankings() -> None:
    vector = [({"id": "a", "ordinal": 0}, 0.9), ({"id": "b", "ordinal": 1}, 0.8)]
    lexical = [({"id": "b", "ordinal": 1}, 0.7), ({"id": "c", "ordinal": 2}, 0.6)]
    fused = _rrf(vector, lexical)
    assert [item["id"] for item, _score in fused] == ["b", "a", "c"]


def test_checked_in_result_snapshot_records_the_baseline_decision() -> None:
    result = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert result["schema_version"] == "nora-rag-eval-v1"
    assert result["dataset_version"] == "2026-08-20"
    assert result["query_count"] == 28
    assert result["positive_query_count"] == 24
    assert result["negative_query_count"] == 4
    assert result["decision"]["selected"] == "Hybrid"
    assert result["decision"]["lexical_complementary_positive_queries"] == 14
    assert result["decision"]["reranker"].startswith("not evaluated")
