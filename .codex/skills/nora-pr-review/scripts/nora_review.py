#!/usr/bin/env python3
"""Nora PR 自动审核助手：渲染审核指令、解析 Codex 结论并发布正式 GitHub Review。

审核智能由 Codex 应用提供（不启动浏览器、不需要 API Key 或 session cookie）。本脚本只做三件事：

1. `--prepare`：收集 PR 上下文（diff、标题、CI、Issue 验收条件），渲染成审核指令文件供 Codex 阅读；
2. `--submit`：读取 Codex 按指令格式产出的回复文件，解析「通过/不通过」结论；
3. 发布：渲染固定模板并 `gh pr review --approve / --request-changes`。

结论只有「通过 / 不通过」两种；不通过必须带修改建议。中间产物只写系统临时目录，不写入仓库工作树。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROMPT_TEMPLATE_PATH = SCRIPT_DIR / "review_prompt_template.md"
REVIEW_TEMPLATE_PATH = SCRIPT_DIR / "review_template.md"
DIFF_TRUNCATE_CHARS = 120_000
VALID_SEVERITIES = frozenset({"blocker", "major", "minor", "nit"})


class ReviewError(Exception):
    """审核流程中的可预期失败。"""


@dataclass(frozen=True, slots=True)
class Suggestion:
    severity: str
    file: str
    line: str
    problem: str
    fix: str


@dataclass(frozen=True, slots=True)
class Verdict:
    conclusion: str  # "pass" | "fail"
    conclusion_note: str = ""
    approved_items: tuple[str, ...] = ()
    suggestions: tuple[Suggestion, ...] = ()


@dataclass(frozen=True, slots=True)
class PrContext:
    number: int
    title: str
    body: str
    url: str
    additions: int
    deletions: int
    changed_files: int
    head: str
    base: str
    checks: str
    diff: str
    issue_acceptance: str = ""


# ---------- 外部命令 ----------


def _run(cmd: Sequence[str]) -> str:
    try:
        result = subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReviewError(f"命令不可用：{cmd[0]}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ReviewError(f"命令失败：{' '.join(cmd)}\n{detail}")
    return result.stdout.strip()


def _run_soft(cmd: Sequence[str]) -> str:
    """容忍非零退出码的命令（如 `gh pr checks` 在有失败检查时返回 1）。"""
    try:
        result = subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


# ---------- 结论解析（纯函数） ----------


def parse_reply(reply: str) -> Verdict:
    """从 Codex 回复解析审核结论。

    优先解析 HTML 注释包裹的 JSON 块；兜底解析首行「审核结论」与建议表格。
    无法确定结论时抛 ReviewError，绝不猜测。
    """
    json_match = re.search(r"<!--\s*review-json\s*-->(.*?)<!--\s*/review-json\s*-->", reply, re.S)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _verdict_from_json(data)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            pass  # 落到文本兜底

    head = re.search(r"审核结论\s*[:：]\s*(通过|不通过)", reply)
    if head is None:
        raise ReviewError("无法解析审核结论，请检查 reply 文件是否按指令格式输出")
    conclusion = "pass" if head.group(1) == "通过" else "fail"
    return Verdict(conclusion=conclusion, suggestions=_parse_suggestion_rows(reply))


def _verdict_from_json(data: dict[str, Any]) -> Verdict:
    conclusion = str(data.get("conclusion", "")).strip().lower()
    if conclusion not in {"pass", "fail"}:
        raise ValueError("conclusion 必须是 pass 或 fail")
    approved_items = tuple(str(item) for item in data.get("approved_items", []) if item)
    suggestions = tuple(
        Suggestion(
            severity=_validate_severity(str(s.get("severity", "minor"))),
            file=str(s.get("file", "")),
            line=str(s.get("line", "")),
            problem=str(s.get("problem", "")),
            fix=str(s.get("fix", "")),
        )
        for s in data.get("suggestions", [])
        if isinstance(s, dict)
    )
    return Verdict(
        conclusion=conclusion,
        conclusion_note=str(data.get("conclusion_note", "")),
        approved_items=approved_items,
        suggestions=suggestions,
    )


def _validate_severity(severity: str) -> str:
    normalized = severity.strip().lower()
    if normalized not in VALID_SEVERITIES:
        normalized = "minor"
    return normalized


def _parse_suggestion_rows(reply: str) -> tuple[Suggestion, ...]:
    rows: list[Suggestion] = []
    pattern = r"^\|\s*(blocker|major|minor|nit)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$"
    for match in re.finditer(pattern, reply, re.M):
        severity, location, problem, fix = match.groups()
        file, sep, line = location.partition(":")
        rows.append(
            Suggestion(
                severity=_validate_severity(severity),
                file=file.strip(),
                line=line.strip() if sep else "",
                problem=problem,
                fix=fix,
            )
        )
    return tuple(rows)


# ---------- 模板渲染（纯函数） ----------


def render_template(template: str, context: dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def build_prompt(context: PrContext) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    fields = {
        "PR": str(context.number),
        "TITLE": context.title,
        "HEAD": context.head,
        "BASE": context.base,
        "URL": context.url,
        "ADDITIONS": str(context.additions),
        "DELETIONS": str(context.deletions),
        "CHANGED_FILES": str(context.changed_files),
        "CHECKS": context.checks or "n/a",
        "BODY": context.body or "（无）",
        "ISSUE_ACCEPTANCE": context.issue_acceptance or "（无）",
        "DIFF": context.diff,
    }
    return render_template(template, fields)


def render_review(verdict: Verdict, context: PrContext) -> str:
    template = REVIEW_TEMPLATE_PATH.read_text(encoding="utf-8")
    suggestion_rows = "\n".join(
        f"| {s.severity} | `{s.file}:{s.line}` | {s.problem} | {s.fix} |"
        for s in verdict.suggestions
    ) or "| — | — | 无 | 无需修改 |"
    approved_items = "\n".join(f"- [x] {item}" for item in verdict.approved_items) or "—"
    fields = {
        "PR": str(context.number),
        "TITLE": context.title,
        "HEAD": context.head,
        "BASE": context.base,
        "ADDITIONS": str(context.additions),
        "DELETIONS": str(context.deletions),
        "CHANGED_FILES": str(context.changed_files),
        "CHECKS": context.checks or "n/a",
        "CONCLUSION": "通过" if verdict.conclusion == "pass" else "不通过",
        "VERDICT": "PASS" if verdict.conclusion == "pass" else "FAIL",
        "APPROVED_ITEMS": approved_items,
        "SUGGESTIONS_ROWS": suggestion_rows,
        "CONCLUSION_NOTE": verdict.conclusion_note or "—",
    }
    return render_template(template, fields)


# ---------- 上下文收集 ----------


def resolve_pr_number(pr: int | None, head: str | None) -> int:
    if pr is not None:
        return pr
    branch = head or _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    listing = _run(
        ["gh", "pr", "list", "--head", branch, "--json", "number", "--jq", ".[0].number"]
    )
    if not listing or listing == "null":
        raise ReviewError(f"分支 {branch} 没有对应 PR")
    return int(listing)


def collect_context(pr: int) -> PrContext:
    meta_raw = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr),
            "--json",
            "title,body,url,additions,deletions,changedFiles,headRefName,baseRefName",
        ]
    )
    meta = json.loads(meta_raw)
    diff = _run(["gh", "pr", "diff", str(pr)])
    truncated = ""
    if len(diff) > DIFF_TRUNCATE_CHARS:
        truncated = (
            f"\n[DIFF 过长已截断，仅保留前 {DIFF_TRUNCATE_CHARS} 字符；其余见 PR 文件统计]\n"
        )
        diff = diff[:DIFF_TRUNCATE_CHARS]
    checks = _run_soft(["gh", "pr", "checks", str(pr)])
    issue_acceptance = _load_issue_acceptance(meta.get("body", ""))
    return PrContext(
        number=pr,
        title=str(meta.get("title", "")),
        body=str(meta.get("body", "")),
        url=str(meta.get("url", "")),
        additions=int(meta.get("additions", 0) or 0),
        deletions=int(meta.get("deletions", 0) or 0),
        changed_files=int(meta.get("changedFiles", 0) or 0),
        head=str(meta.get("headRefName", "")),
        base=str(meta.get("baseRefName", "")),
        checks=checks,
        diff=truncated + diff,
        issue_acceptance=issue_acceptance,
    )


def _load_issue_acceptance(pr_body: str) -> str:
    match = re.search(r"Closes\s+#(\d+)", pr_body)
    if match is None:
        return ""
    issue_body = _run_soft(["gh", "issue", "view", match.group(1), "--json", "body", "--jq", ".body"])
    if not issue_body:
        return ""
    section = re.search(r"##\s*验收条件(.*?)(?=\n##\s|\Z)", issue_body, re.S)
    return section.group(1).strip() if section else issue_body[:2000]


# ---------- 发布 ----------


def _existing_review_authors(pr: int) -> tuple[str, ...]:
    raw = _run_soft(
        ["gh", "pr", "view", str(pr), "--json", "reviews", "--jq", "[.reviews[].author.login]"]
    )
    if not raw or raw == "[]":
        return ()
    try:
        return tuple(json.loads(raw))
    except json.JSONDecodeError:
        return ()


def post_review(pr: int, verdict: Verdict, review_path: Path, force: bool) -> str:
    authors = _existing_review_authors(pr)
    current_author = _run_soft(["gh", "api", "user", "--jq", ".login"])
    if current_author in authors and not force:
        print("[warn] 该 PR 已存在当前用户的 Review；如需覆盖请加 --force", file=sys.stderr)
    event = "approve" if verdict.conclusion == "pass" else "request-changes"
    _run(["gh", "pr", "review", str(pr), f"--{event}", "--body-file", str(review_path)])
    return event


# ---------- CLI ----------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nora PR 自动审核助手（模板渲染 + GitHub Review 发布；审核智能由 Codex 提供）"
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--pr", type=int, help="PR 编号")
    target.add_argument("--head", type=str, help="来源分支（默认当前分支）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="收集上下文并生成审核指令文件（供 Codex 阅读产出结论）")
    mode.add_argument("--submit", action="store_true", help="读取 Codex 的回复文件，解析并发布 PR Review")
    parser.add_argument("--no-post", action="store_true", help="submit 时渲染 review body 但不发布")
    parser.add_argument("--output-dir", type=str, help="prompt/回复/模板输出目录（默认系统临时目录）")
    parser.add_argument("--reply-file", type=str, help="submit 时使用的回复文件（默认 <output-dir>/reply-<PR>.md）")
    parser.add_argument("--force", action="store_true", help="已存在同作者 Review 时仍重新发布")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    pr = resolve_pr_number(args.pr, args.head)
    output_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.prepare:
        context = collect_context(pr)
        prompt = build_prompt(context)
        prompt_path = output_dir / f"prompt-{pr}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        reply_path = output_dir / f"reply-{pr}.md"
        print(f"[prepare] PR #{pr}：{context.title}")
        print(f"[prepare] 审核指令已生成：{prompt_path}")
        print(f"[prepare] 请让 Codex 阅读该文件并按其中「输出格式」产出结论，保存为：{reply_path}")
        print(f"[prepare] 然后运行：nora_review.py --submit --pr {pr}")
        return 0

    context = collect_context(pr)
    reply_path = (
        Path(args.reply_file) if args.reply_file else output_dir / f"reply-{pr}.md"
    )
    if not reply_path.exists():
        raise ReviewError(f"未找到回复文件：{reply_path}，请先运行 --prepare 并让 Codex 产出结论")

    reply = reply_path.read_text(encoding="utf-8")
    verdict = parse_reply(reply)
    review_body = render_review(verdict, context)
    review_path = output_dir / f"review-{pr}.md"
    review_path.write_text(review_body, encoding="utf-8")
    print(f"[submit] 结论：{verdict.conclusion}（{len(verdict.suggestions)} 条建议）")
    print(f"[submit] review body 已生成：{review_path}")

    if args.no_post:
        print("[no-post] 未发布 Review")
        return 0

    event = post_review(pr, verdict, review_path, args.force)
    print(f"[posted] {event} review 已发布到 PR #{pr}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReviewError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
