"""Offline OpenAPI export contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.export_openapi import GENERATED_NOTICE, export_openapi


def test_openapi_export_is_offline_deterministic_and_representative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")
    monkeypatch.setenv("AUTH_SECRET_KEY", "not-a-valid-secret")
    output = tmp_path / "openapi.json"

    first = export_openapi(output)
    second = export_openapi(output)

    assert first == second == output.read_bytes()
    assert first.endswith(b"\n")
    document = json.loads(first)
    assert document["openapi"] == "3.1.0"
    assert document["x-generated-notice"] == GENERATED_NOTICE
    assert document["components"]["schemas"]["ApplicationDecisionStatus"]["enum"] == [
        "apply",
        "skip",
    ]
    nullable_size = document["components"]["schemas"]["AppendCompanySnapshotRequest"]["properties"][
        "size"
    ]
    assert {option.get("type") for option in nullable_size["anyOf"]} == {"string", "null"}
    create_posting = document["paths"]["/job-postings"]["post"]
    assert create_posting["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateJobPostingRequest"
    }
    assert "201" in create_posting["responses"]
