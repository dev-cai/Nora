#!/usr/bin/env python3
"""Unit tests for Nora Issue helper scripts."""

from __future__ import annotations

import unittest
from pathlib import Path

from sync_labels import drift
from validate_issue import REQUIRED_HEADINGS, validate


ROOT = Path(__file__).resolve().parents[4]


def docs_body(state: str = "ready") -> str:
    headings = [
        "状态",
        "背景",
        "目标",
        "修改范围",
        "验收标准",
        "Parent Epic",
        "依赖",
        "边界",
        "影响范围",
        "验证",
    ]
    sections = []
    for heading in headings:
        content = f"`{state}`" if heading == "状态" else "- 内容"
        if heading == "验收标准":
            content = "- [ ] 可验证条件"
        sections.append(f"## {heading}\n\n{content}")
    return "\n\n".join(sections)


def body_for(issue_type: str, state: str = "ready") -> str:
    sections = []
    for heading in REQUIRED_HEADINGS[issue_type]:
        content = f"`{state}`" if heading == "状态" else "- 内容"
        if heading in {"验收标准", "Epic 退出条件"}:
            content = "- [ ] 可验证条件"
        sections.append(f"## {heading}\n\n{content}")
    return "\n\n".join(sections)


class ValidateIssueTests(unittest.TestCase):
    def test_accepts_all_supported_issue_types(self) -> None:
        areas = {
            "type:architecture": "area:architecture",
            "type:epic": "area:architecture",
            "type:task": "area:backend",
            "type:bug": "area:backend",
            "type:docs": "area:docs",
        }
        for issue_type, area in areas.items():
            with self.subTest(issue_type=issue_type):
                payload = {
                    "title": "建立可验证的项目交付边界",
                    "body": body_for(issue_type),
                    "labels": [issue_type, "priority:p1", area],
                    "milestone": "M0 — Architecture Foundation",
                }
                self.assertEqual(validate(payload, ROOT), [])

    def test_accepts_valid_documentation_issue(self) -> None:
        payload = {
            "title": "建立带标签的 Issue 创建流程",
            "body": docs_body(),
            "labels": ["type:docs", "priority:p0", "area:docs"],
            "milestone": "M0 — Architecture Foundation",
        }
        self.assertEqual(validate(payload, ROOT), [])

    def test_rejects_invalid_state_and_label_counts(self) -> None:
        payload = {
            "title": "[Phase 1] 建立流程",
            "body": docs_body("review"),
            "labels": ["type:docs", "type:task", "area:docs"],
        }
        errors = validate(payload, ROOT)
        self.assertTrue(any("固定前缀" in error for error in errors))
        self.assertTrue(any("一个 type" in error for error in errors))
        self.assertTrue(any("一个 priority" in error for error in errors))
        self.assertTrue(any("ready 或 blocked" in error for error in errors))


class LabelDriftTests(unittest.TestCase):
    def test_detects_missing_drift_and_forbidden_labels(self) -> None:
        config = {
            "labels": [
                {"name": "type:docs", "color": "d4c5f9", "description": "文档"},
                {"name": "priority:p0", "color": "b60205", "description": "阻塞"},
            ],
            "forbidden_labels": ["documentation"],
        }
        actual = {
            "type:docs": {
                "name": "type:docs",
                "color": "ffffff",
                "description": "文档",
            },
            "documentation": {
                "name": "documentation",
                "color": "0075ca",
                "description": "",
            },
        }
        self.assertEqual(
            drift(config, actual),
            ["drift: type:docs", "missing: priority:p0", "forbidden: documentation"],
        )


if __name__ == "__main__":
    unittest.main()
