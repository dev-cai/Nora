#!/usr/bin/env python3
"""Load and validate Nora's machine-readable documentation contract."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from pathlib import Path
from typing import Any

PR_URL = re.compile(r"https://github\.com/dev-cai/Nora/pull/[1-9][0-9]*$")
MILESTONE_HEADING = re.compile(r"^(?:\d+\.\s+)?(M\d+\+?)(?:[：:]|\s|$)")


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


def _level2_headings(path: Path) -> list[str]:
    """Return level-two Markdown heading text without the marker."""
    return [
        line[3:].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    ]


def _validate_planning_baseline(
    root: Path,
    planning: object,
    document_paths: dict[str, str],
) -> list[str]:
    """Validate canonical planning headings and retired milestone boundaries."""
    prefix = "docs-contract.toml: planning_baseline"
    if not isinstance(planning, dict):
        return [f"{prefix} must be a table"]

    errors: list[str] = []
    active = planning.get("active_milestones")
    retired = planning.get("retired_milestones")
    if not _string_list(active):
        errors.append(f"{prefix}.active_milestones must be a non-empty string list")
        active = []
    if not _string_list(retired):
        errors.append(f"{prefix}.retired_milestones must be a non-empty string list")
        retired = []
    if set(active) & set(retired):
        errors.append(f"{prefix} active and retired milestones must not overlap")

    planning_documents = planning.get("documents")
    if not isinstance(planning_documents, list) or not planning_documents:
        return [*errors, f"{prefix}.documents must be a non-empty table array"]

    seen_ids: set[str] = set()
    for index, entry in enumerate(planning_documents, start=1):
        entry_prefix = f"{prefix}.documents[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{entry_prefix} must be a table")
            continue
        document_id = entry.get("id")
        expected = entry.get("level2_headings")
        if not isinstance(document_id, str) or not document_id:
            errors.append(f"{entry_prefix}.id must be a non-empty string")
            continue
        if document_id in seen_ids:
            errors.append(f"{entry_prefix}.id is duplicated: {document_id}")
            continue
        seen_ids.add(document_id)
        if document_id not in document_paths:
            errors.append(f"{entry_prefix} references unknown document: {document_id}")
            continue
        if not _string_list(expected):
            errors.append(f"{entry_prefix}.level2_headings must be a non-empty string list")
            continue

        expected_milestones = {
            match.group(1)
            for heading in expected
            if (match := MILESTONE_HEADING.match(heading)) is not None
        }
        if expected_milestones != set(active):
            errors.append(
                f"{entry_prefix}.level2_headings must declare exactly the active milestones: "
                f"{', '.join(active)}"
            )

        path = root / document_paths[document_id]
        if not path.is_file():
            continue
        try:
            actual = _level2_headings(path)
        except (OSError, UnicodeError) as error:
            errors.append(f"{entry_prefix} cannot read {path.relative_to(root)}: {error}")
            continue
        for heading in expected:
            count = actual.count(heading)
            if count != 1:
                errors.append(
                    f"{path.relative_to(root)}: expected level-two heading exactly once: "
                    f"{heading} (found {count})"
                )
        for heading in actual:
            match = MILESTONE_HEADING.match(heading)
            if match is not None and match.group(1) in retired:
                errors.append(
                    f"{path.relative_to(root)}: retired milestone must not be a "
                    f"level-two heading: {heading}"
                )
    return errors


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
        return [
            *errors,
            "docs-contract.toml: documents must be a non-empty table array",
        ]

    document_ids: set[str] = set()
    document_paths_by_id: dict[str, str] = {}
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
            if isinstance(document_id, str) and document_id:
                document_paths_by_id[document_id] = path
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

    errors += _validate_planning_baseline(
        root,
        contract.get("planning_baseline"),
        document_paths_by_id,
    )

    rules = contract.get("impact_rules")
    if not isinstance(rules, list) or not rules:
        return [
            *errors,
            "docs-contract.toml: impact_rules must be a non-empty table array",
        ]
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
