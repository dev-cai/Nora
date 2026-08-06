#!/usr/bin/env python3
"""Check whether a change updates or explicitly exempts impacted documentation."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contract import load_toml, matches_path, validate_contract

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "docs-contract.toml"
SECTION = re.compile(r"(?ms)^## 文档影响\s*$\n(.*?)(?=^## |\Z)")
FIELD = re.compile(r"(?m)^- (影响事实|更新事实源|无文档变更理由)[：:]\s*(.+?)\s*$")
PLACEHOLDERS = {
    "",
    "-",
    "—",
    "无",
    "none",
    "n/a",
    "不适用",
    "<!-- 必填 -->",
}


@dataclass(frozen=True)
class ImpactDeclaration:
    affected_facts: str
    updated_sources: str
    no_docs_reason: str


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def parse_declaration(body: str) -> tuple[ImpactDeclaration | None, list[str]]:
    """Parse the exact structured PR section used by the template."""
    section_match = SECTION.search(body)
    if section_match is None:
        return None, ["PR body is missing the '## 文档影响' section"]
    values = {name: value.strip() for name, value in FIELD.findall(section_match.group(1))}
    missing = [name for name in ("影响事实", "更新事实源", "无文档变更理由") if name not in values]
    if missing:
        return None, [f"Docs Impact is missing field: {name}" for name in missing]
    declaration = ImpactDeclaration(
        affected_facts=values["影响事实"],
        updated_sources=values["更新事实源"],
        no_docs_reason=values["无文档变更理由"],
    )
    return declaration, []


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in PLACEHOLDERS or "<!--" in normalized


def _valid_reason(value: str) -> bool:
    return not _is_placeholder(value) and len(value.strip()) >= 12


def document_paths(contract: dict[str, Any]) -> dict[str, str]:
    return {item["id"]: item["path"] for item in contract["documents"]}


def evaluate_impact(
    changed_files: set[str],
    contract: dict[str, Any],
    declaration: ImpactDeclaration | None,
    *,
    require_declaration: bool,
) -> tuple[list[str], list[str]]:
    """Return errors and a human-readable matched-rule report."""
    normalized_files = {normalize_path(path) for path in changed_files}
    paths_by_id = document_paths(contract)
    missing_by_rule: dict[str, list[str]] = {}
    report: list[str] = []

    for rule in contract["impact_rules"]:
        matched = sorted(
            path
            for path in normalized_files
            if any(matches_path(path, pattern) for pattern in rule["patterns"])
        )
        if not matched:
            continue
        required_paths = [paths_by_id[document_id] for document_id in rule["required_docs"]]
        missing = [path for path in required_paths if path not in normalized_files]
        report.append(f"{rule['id']}: {', '.join(matched)} -> {', '.join(required_paths)}")
        if missing:
            missing_by_rule[rule["id"]] = missing

    errors: list[str] = []
    if require_declaration:
        if declaration is None:
            errors.append("A complete structured Docs Impact declaration is required")
        else:
            if _is_placeholder(declaration.affected_facts):
                errors.append("Docs Impact field '影响事实' must not be a placeholder")
            if _is_placeholder(declaration.updated_sources):
                errors.append("Docs Impact field '更新事实源' must not be a placeholder")

    if missing_by_rule:
        if declaration is None or not _valid_reason(declaration.no_docs_reason):
            for rule_id, missing in missing_by_rule.items():
                errors.append(
                    f"{rule_id}: update {', '.join(missing)} or provide a concrete "
                    "'无文档变更理由' (at least 12 characters)"
                )
    elif require_declaration and not report:
        if declaration is None or not _valid_reason(declaration.no_docs_reason):
            errors.append(
                "No impact rule matched; provide a concrete '无文档变更理由' "
                "(at least 12 characters)"
            )

    return errors, report


def git_changed_files(base: str, *, root: Path = ROOT) -> set[str]:
    """Collect committed, staged, and unstaged changes relative to base."""
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB"],
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"{' '.join(command)} failed")
        changed.update(normalize_path(line) for line in result.stdout.splitlines() if line)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument("--pr-body-env", default="PR_BODY")
    parser.add_argument("--require-declaration", action="store_true")
    args = parser.parse_args()

    contract = load_toml(CONTRACT_PATH)
    contract_errors = validate_contract(ROOT, contract)
    if contract_errors:
        for error in contract_errors:
            print(error, file=sys.stderr)
        return 1

    try:
        changed_files = (
            {normalize_path(path) for path in args.changed_file}
            if args.changed_file
            else git_changed_files(args.base)
        )
    except RuntimeError as error:
        print(f"Unable to collect changed files: {error}", file=sys.stderr)
        return 1

    body = ""
    if args.pr_body_file:
        body = args.pr_body_file.read_text(encoding="utf-8")
    elif args.pr_body_env:
        body = os.environ.get(args.pr_body_env, "")
    declaration, declaration_errors = parse_declaration(body) if body else (None, [])
    errors, report = evaluate_impact(
        changed_files,
        contract,
        declaration,
        require_declaration=args.require_declaration,
    )
    if args.require_declaration:
        errors = [*declaration_errors, *errors]

    print(f"Changed files: {len(changed_files)}")
    if report:
        print("Matched documentation impact rules:")
        for item in report:
            print(f"- {item}")
    else:
        print("No documentation impact rule matched.")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Documentation impact declaration is consistent with the contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
