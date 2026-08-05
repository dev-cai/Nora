#!/usr/bin/env python3
"""Load and validate Nora's machine-readable documentation contract."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from pathlib import Path
from typing import Any

PR_URL = re.compile(r"https://github\.com/dev-cai/Nora/pull/[1-9][0-9]*$")


def load_toml(path: Path) -> dict[str, Any]:
    """Load one UTF-8 TOML document."""
    with path.open("rb") as file:
        return tomllib.load(file)


def matches_path(path: str, pattern: str) -> bool:
    """Match normalized repository paths against contract globs."""
    normalized = path.replace("\\", "/").lstrip("./")
    return fnmatch.fnmatchcase(normalized, pattern)


def resolve_matches(root: Path, pattern: str) -> list[Path]:
    """Return repository files matching a contract glob."""
    if not any(character in pattern for character in "*?["):
        candidate = root / pattern
        return [candidate] if candidate.is_file() else []
    return [path for path in root.glob(pattern) if path.is_file()]


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def validate_contract(root: Path, contract: dict[str, Any]) -> list[str]:
    """Validate document ownership and path-impact declarations."""
    errors: list[str] = []
    if contract.get("version") != 1:
        errors.append("docs-contract.toml: version must be 1")

    categories = contract.get("categories")
    if not _string_list(categories):
        errors.append("docs-contract.toml: categories must be a non-empty string list")
        categories = []
    category_set = set(categories)

    documents = contract.get("documents")
    if not isinstance(documents, list) or not documents:
        return [*errors, "docs-contract.toml: documents must be a non-empty table array"]

    document_ids: set[str] = set()
    document_paths: set[str] = set()
    for index, document in enumerate(documents, start=1):
        prefix = f"docs-contract.toml: documents[{index}]"
        if not isinstance(document, dict):
            errors.append(f"{prefix} must be a table")
            continue
        document_id = document.get("id")
        path = document.get("path")
        category = document.get("category")
        if not isinstance(document_id, str) or not document_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif document_id in document_ids:
            errors.append(f"{prefix}.id is duplicated: {document_id}")
        else:
            document_ids.add(document_id)
        if not isinstance(path, str) or not path:
            errors.append(f"{prefix}.path must be a non-empty string")
        elif path in document_paths:
            errors.append(f"{prefix}.path is duplicated: {path}")
        else:
            document_paths.add(path)
            if not (root / path).is_file():
                errors.append(f"{prefix}.path does not exist: {path}")
        if category not in category_set:
            errors.append(f"{prefix}.category is not declared: {category}")
        if not isinstance(document.get("reviewer"), str):
            errors.append(f"{prefix}.reviewer must be a string")
        if not _string_list(document.get("owns")):
            errors.append(f"{prefix}.owns must be a non-empty string list")
        summaries = document.get("allowed_summaries")
        if not isinstance(summaries, list) or not all(isinstance(item, str) for item in summaries):
            errors.append(f"{prefix}.allowed_summaries must be a string list")

    for index, document in enumerate(documents, start=1):
        if not isinstance(document, dict):
            continue
        for summary_id in document.get("allowed_summaries", []):
            if summary_id not in document_ids:
                errors.append(
                    f"docs-contract.toml: documents[{index}] references unknown summary: "
                    f"{summary_id}"
                )

    rules = contract.get("impact_rules")
    if not isinstance(rules, list) or not rules:
        return [*errors, "docs-contract.toml: impact_rules must be a non-empty table array"]
    rule_ids: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        prefix = f"docs-contract.toml: impact_rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be a table")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif rule_id in rule_ids:
            errors.append(f"{prefix}.id is duplicated: {rule_id}")
        else:
            rule_ids.add(rule_id)
        if not isinstance(rule.get("description"), str):
            errors.append(f"{prefix}.description must be a string")
        if not _string_list(rule.get("patterns")):
            errors.append(f"{prefix}.patterns must be a non-empty string list")
        if not _string_list(rule.get("required_docs")):
            errors.append(f"{prefix}.required_docs must be a non-empty string list")
        for document_id in rule.get("required_docs", []):
            if document_id not in document_ids:
                errors.append(f"{prefix} references unknown document: {document_id}")
    return errors


def validate_capabilities(root: Path, ledger: dict[str, Any]) -> list[str]:
    """Validate the Current-only capability ledger and its local evidence."""
    errors: list[str] = []
    if ledger.get("version") != 1:
        errors.append("current-capabilities.toml: version must be 1")
    if ledger.get("status") != "current-only":
        errors.append("current-capabilities.toml: status must be current-only")
    capabilities = ledger.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return [
            *errors,
            "current-capabilities.toml: capabilities must be a non-empty table array",
        ]

    capability_ids: set[str] = set()
    for index, capability in enumerate(capabilities, start=1):
        prefix = f"current-capabilities.toml: capabilities[{index}]"
        if not isinstance(capability, dict):
            errors.append(f"{prefix} must be a table")
            continue
        capability_id = capability.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif capability_id in capability_ids:
            errors.append(f"{prefix}.id is duplicated: {capability_id}")
        else:
            capability_ids.add(capability_id)
        for field in ("name", "milestone", "summary"):
            if not isinstance(capability.get(field), str) or not capability[field].strip():
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if capability.get("status") != "current":
            errors.append(f"{prefix}.status must be current")
        paths = capability.get("code_paths")
        if not _string_list(paths):
            errors.append(f"{prefix}.code_paths must be a non-empty string list")
        else:
            for pattern in paths:
                if not resolve_matches(root, pattern):
                    errors.append(f"{prefix}.code_paths has no match: {pattern}")
        evidence = capability.get("evidence")
        if not _string_list(evidence):
            errors.append(f"{prefix}.evidence must be a non-empty string list")
        else:
            for url in evidence:
                if PR_URL.fullmatch(url) is None:
                    errors.append(f"{prefix}.evidence is not a Nora PR URL: {url}")
    return errors
