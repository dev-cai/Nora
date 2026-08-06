from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DOCS_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCS_SCRIPTS))

from check_impact import (  # noqa: E402
    ImpactDeclaration,
    evaluate_impact,
    git_changed_files,
    parse_declaration,
)
from contract import validate_capabilities, validate_contract  # noqa: E402


def sample_contract() -> dict[str, object]:
    return {
        "version": 1,
        "categories": ["reference"],
        "documents": [
            {
                "id": "ledger",
                "path": "docs/ledger.toml",
                "category": "reference",
                "reviewer": "area:docs",
                "owns": ["current facts"],
                "allowed_summaries": [],
            }
        ],
        "impact_rules": [
            {
                "id": "api",
                "description": "API facts",
                "patterns": ["backend/api/**"],
                "required_docs": ["ledger"],
            }
        ],
    }


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


class ContractValidationTests(unittest.TestCase):
    def test_contract_accepts_existing_document_and_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "ledger.toml").write_text("version = 1\n", encoding="utf-8")
            self.assertEqual(validate_contract(root, sample_contract()), [])

    def test_capability_rejects_missing_code_evidence(self) -> None:
        ledger = {
            "version": 1,
            "status": "current-only",
            "capabilities": [
                {
                    "id": "auth",
                    "name": "Auth",
                    "milestone": "M1",
                    "status": "current",
                    "summary": "Available",
                    "code_paths": ["backend/auth.py"],
                    "evidence": ["https://github.com/dev-cai/Nora/pull/47"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            errors = validate_capabilities(Path(directory), ledger)
        self.assertTrue(any("has no match" in error for error in errors))


class ImpactTests(unittest.TestCase):
    def test_collects_committed_staged_and_unstaged_deletions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route = root / "backend" / "api" / "routes.py"
            route.parent.mkdir(parents=True)
            route.write_text("route = True\n", encoding="utf-8")
            run_git(root, "init")
            run_git(root, "config", "user.email", "test@example.com")
            run_git(root, "config", "user.name", "Nora Docs Test")
            run_git(root, "add", ".")
            run_git(root, "commit", "-m", "baseline")
            base = run_git(root, "rev-parse", "HEAD")

            route.unlink()
            self.assertIn("backend/api/routes.py", git_changed_files(base, root=root))

            run_git(root, "add", "-A")
            self.assertIn("backend/api/routes.py", git_changed_files(base, root=root))

            run_git(root, "commit", "-m", "delete route")
            self.assertIn("backend/api/routes.py", git_changed_files(base, root=root))

    def test_parse_complete_declaration(self) -> None:
        body = """## 文档影响

- 影响事实：公开 API 路由
- 更新事实源：docs/ledger.toml
- 无文档变更理由：不适用，已经更新上述规范事实源

## 验证结果
"""
        declaration, errors = parse_declaration(body)
        self.assertEqual(errors, [])
        self.assertIsNotNone(declaration)
        assert declaration is not None
        self.assertEqual(declaration.updated_sources, "docs/ledger.toml")

    def test_missing_canonical_document_is_blocked(self) -> None:
        errors, _ = evaluate_impact(
            {"backend/api/routes.py"},
            sample_contract(),
            None,
            require_declaration=False,
        )
        self.assertTrue(any("docs/ledger.toml" in error for error in errors))

    def test_updated_canonical_document_passes(self) -> None:
        errors, _ = evaluate_impact(
            {"backend/api/routes.py", "docs/ledger.toml"},
            sample_contract(),
            None,
            require_declaration=False,
        )
        self.assertEqual(errors, [])

    def test_concrete_exemption_passes(self) -> None:
        declaration = ImpactDeclaration(
            affected_facts="内部重命名，不改变公开 API",
            updated_sources="无，规范事实没有变化",
            no_docs_reason="仅重命名内部测试夹具，公开 API 和运行方式均未变化",
        )
        errors, _ = evaluate_impact(
            {"backend/api/routes.py"},
            sample_contract(),
            declaration,
            require_declaration=True,
        )
        self.assertEqual(errors, [])

    def test_placeholder_exemption_is_blocked(self) -> None:
        declaration = ImpactDeclaration(
            affected_facts="公开 API",
            updated_sources="无",
            no_docs_reason="不适用",
        )
        errors, _ = evaluate_impact(
            {"backend/api/routes.py"},
            sample_contract(),
            declaration,
            require_declaration=True,
        )
        self.assertTrue(any("更新事实源" in error for error in errors))
        self.assertTrue(any("无文档变更理由" in error for error in errors))

    def test_no_matching_rule_requires_concrete_reason(self) -> None:
        declaration = ImpactDeclaration(
            affected_facts="无公开事实变化",
            updated_sources="无，规范事实没有变化",
            no_docs_reason="不适用",
        )
        errors, _ = evaluate_impact(
            {"tests/unit/test_internal.py"},
            sample_contract(),
            declaration,
            require_declaration=True,
        )
        self.assertTrue(any("No impact rule matched" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
