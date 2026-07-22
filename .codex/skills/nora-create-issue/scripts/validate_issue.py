#!/usr/bin/env python3
"""Validate a Nora Issue payload before creation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_STATES = {"ready", "blocked"}
FORBIDDEN_TITLE = re.compile(
    r"^\s*(?:\[(?:roadmap|phase|architecture|implementation|bug|docs?)[^\]]*\]|#\d+)",
    re.I,
)
CHINESE = re.compile(r"[\u3400-\u9fff]")
STATUS = re.compile(r"(?ms)^## 状态\s+`([^`]+)`\s*$")
REQUIRED_HEADINGS = {
    "type:architecture": [
        "状态",
        "背景",
        "决策目标",
        "已知约束",
        "候选方案与取舍",
        "决策输出",
        "验收标准",
        "Parent Epic",
        "依赖",
        "边界",
        "影响范围",
        "验证",
    ],
    "type:epic": [
        "状态",
        "背景",
        "目标",
        "子任务",
        "外部依赖",
        "Epic 退出条件",
        "边界",
        "影响范围",
        "验证",
    ],
    "type:task": [
        "状态",
        "背景",
        "目标",
        "技术范围",
        "验收标准",
        "Parent Epic",
        "依赖",
        "边界",
        "影响范围",
        "验证",
    ],
    "type:bug": [
        "状态",
        "背景",
        "复现步骤",
        "实际行为",
        "预期行为",
        "当前证据",
        "验收标准",
        "依赖",
        "边界",
        "影响范围",
        "验证",
    ],
    "type:docs": [
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
    ],
}


def load_config(root: Path) -> dict[str, Any]:
    return json.loads((root / ".github" / "labels.json").read_text(encoding="utf-8"))


def validate(payload: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    labels = payload.get("labels", [])
    milestone = payload.get("milestone")
    if not title or not CHINESE.search(title):
        errors.append("标题必须包含自然中文")
    if FORBIDDEN_TITLE.search(title):
        errors.append("标题不得包含固定前缀、流水线编号或 Issue 编号")
    if not isinstance(labels, list) or not all(
        isinstance(item, str) for item in labels
    ):
        return [*errors, "labels 必须是字符串数组"]

    config_names = {item["name"] for item in load_config(root)["labels"]}
    unknown = sorted(set(labels) - config_names)
    if unknown:
        errors.append(f"存在未配置标签：{', '.join(unknown)}")
    type_labels = [item for item in labels if item.startswith("type:")]
    priority_labels = [item for item in labels if item.startswith("priority:")]
    area_labels = [item for item in labels if item.startswith("area:")]
    if len(type_labels) != 1:
        errors.append("必须且只能包含一个 type:* 标签")
    if len(priority_labels) != 1:
        errors.append("必须且只能包含一个 priority:* 标签")
    if not area_labels:
        errors.append("必须至少包含一个 area:* 标签")
    if len(area_labels) > 2:
        errors.append("area:* 超过两个，应优先拆分 Issue")

    issue_type = type_labels[0] if len(type_labels) == 1 else ""
    for heading in REQUIRED_HEADINGS.get(issue_type, []):
        if not re.search(rf"(?m)^## {re.escape(heading)}\s*$", body):
            errors.append(f"缺少章节：## {heading}")
    status_match = STATUS.search(body)
    if not status_match or status_match.group(1) not in ALLOWED_STATES:
        errors.append("创建状态必须是 ready 或 blocked")
    if issue_type in {"type:architecture", "type:epic", "type:task"} and not milestone:
        errors.append("Architecture、Epic 和 Task 必须设置 Milestone")
    if "- [ ]" not in body:
        errors.append("正文必须包含可勾选的验收条件")
    return errors


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON file path or - for stdin")
    args = parser.parse_args()
    raw = (
        sys.stdin.read()
        if args.input == "-"
        else Path(args.input).read_text(encoding="utf-8")
    )
    payload = json.loads(raw)
    errors = validate(payload, repository_root())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Issue payload is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
