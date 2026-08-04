#!/usr/bin/env python3
"""Nora PR 自动审核：本地 Playwright 驱动 chatgpt.com 审核 PR，并以正式 GitHub Review 发布结论。

结论只有「通过 / 不通过」两种：
- 通过   → `gh pr review <n> --approve`
- 不通过 → `gh pr review <n> --request-changes`（必须带修改建议）

浏览器 profile、Cookie、ChatGPT 回复与 prompt 只写系统临时目录，绝不写入仓库工作树。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROMPT_TEMPLATE_PATH = SCRIPT_DIR / "review_prompt_template.md"
REVIEW_TEMPLATE_PATH = SCRIPT_DIR / "review_template.md"
DIFF_TRUNCATE_CHARS = 120_000
VALID_SEVERITIES = frozenset({"blocker", "major", "minor", "nit"})

# ChatGPT web 页面选择器（多版本兜底，易变的 DOM）
PROMPT_SELECTORS = (
    "#prompt-textarea",
    "textarea[data-testid='prompt-textarea']",
    "div[contenteditable='true'].ProseMirror",
    "[id*='prompt'] textarea",
)
STOP_SELECTORS = (
    "button[data-testid='stop-button']",
    "[data-testid='stop']",
    "button[aria-label*='Stop' i]",
    "button[aria-label*='停止']",
)
ASSISTANT_SELECTOR = "div[data-message-author-role='assistant']"


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


# ---------- 结论解析（纯函数，可单测） ----------


def parse_reply(reply: str) -> Verdict:
    """从 ChatGPT 回复解析审核结论。

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
        raise ReviewError("无法解析审核结论，请使用 --manual 人工复核")
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


# ---------- 模板渲染（纯函数，可单测） ----------


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


# ---------- ChatGPT Web（Playwright 延迟导入） ----------


def _launch_context(playwright_module: Any, profile_dir: str, headed: bool) -> Any:
    channels = _channel_sequence()
    last_error: Exception | None = None
    for channel in channels:
        try:
            kwargs: dict[str, Any] = {"user_data_dir": profile_dir, "headless": not headed}
            if channel:
                kwargs["channel"] = channel
            return playwright_module.chromium.launch_persistent_context(**kwargs)
        except Exception as exc:  # noqa: BLE001 - 逐个通道尝试
            last_error = exc
    raise ReviewError(f"无法启动浏览器（尝试 {channels}）：{last_error}")


def _channel_sequence() -> tuple[str | None, ...]:
    env_channel = os.environ.get("NORA_CHATGPT_CHANNEL", "").strip()
    channels: list[str | None] = []
    if env_channel:
        channels.append(env_channel)
    channels.append("msedge")
    channels.append("chrome")
    channels.append(None)  # 默认 Chromium
    return tuple(channels)


def _fill_and_send(page: Any, prompt: str) -> None:
    box = None
    for selector in PROMPT_SELECTORS:
        locator = page.locator(selector).first
        if locator.count() > 0:
            box = locator
            break
    if box is None:
        raise ReviewError("未找到 ChatGPT 输入框（DOM 可能已变化），请使用 --manual 模式")
    try:
        box.fill(prompt)
    except Exception:  # noqa: BLE001 - contenteditable 元素 fill 不可用
        box.click()
        page.keyboard.insert_text(prompt)
    page.keyboard.press("Enter")


def _wait_for_completion(page: Any, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    stop_waited = _wait_stop_button(page, timeout)
    last_text = ""
    stable_ticks = 0
    while time.monotonic() < deadline:
        texts = page.locator(ASSISTANT_SELECTOR).all_inner_texts()
        current = texts[-1] if texts else ""
        if current and current == last_text:
            stable_ticks += 1
            if stable_ticks >= 5 or stop_waited:
                last_text = current
                break
        else:
            stable_ticks = 0
            last_text = current
        time.sleep(1)
    if not last_text:
        raise ReviewError("未获取到 ChatGPT 回复，请使用 --manual 模式")
    if time.monotonic() >= deadline:
        print("[warn] 到达超时上限，使用当前已生成文本继续", file=sys.stderr)
    return last_text


def _wait_stop_button(page: Any, timeout: int) -> bool:
    stop = None
    for selector in STOP_SELECTORS:
        locator = page.locator(selector).first
        if locator.count() > 0:
            stop = locator
            break
    if stop is None:
        return False
    try:
        stop.wait_for(state="visible", timeout=timeout * 1000)
    except Exception:  # noqa: BLE001
        pass
    try:
        stop.wait_for(state="detached", timeout=timeout * 1000)
        return True
    except Exception:  # noqa: BLE001
        return False


def _assert_logged_in(page: Any) -> None:
    if "/auth" in page.url:
        raise ReviewError("ChatGPT 未登录或登录态过期，请先执行 --login")
    try:
        if page.get_by_text("Sign in", exact=True).count() > 0:
            raise ReviewError("ChatGPT 页面要求登录，请先执行 --login")
    except Exception:  # noqa: BLE001 - 选择器兼容
        pass


def chatgpt_review(prompt: str, profile_dir: str, headed: bool, timeout: int) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ReviewError(
            "未安装 playwright，请按 docs/DEVELOPMENT.md「Codex 自动审核」章节安装"
        ) from exc
    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headed)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
            _assert_logged_in(page)
            _fill_and_send(page, prompt)
            return _wait_for_completion(page, timeout)
        finally:
            context.close()


def login(profile_dir: str) -> None:
    """一次性初始化专用浏览器 profile：打开 chatgpt.com 引导手动登录。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ReviewError(
            "未安装 playwright，请按 docs/DEVELOPMENT.md「Codex 自动审核」章节安装"
        ) from exc
    with sync_playwright() as playwright:
        context = _launch_context(playwright, profile_dir, headed=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        print("请在浏览器中登录 chatgpt.com；登录完成后回到本终端按 Enter 结束并保存会话。")
        input()
        context.close()


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


# ---------- 手动降级 ----------


def _read_reply_manual(pr: int, output_dir: Path) -> str:
    reply_path = output_dir / f"reply-{pr}.txt"
    if reply_path.exists():
        return reply_path.read_text(encoding="utf-8")
    print(f"请将 ChatGPT 回复保存到 {reply_path}，或直接粘贴回复内容（Windows 下粘贴后按 Ctrl+Z 回车结束）")
    return sys.stdin.read()


# ---------- CLI ----------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nora PR 自动审核（Playwright + ChatGPT Web）")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--pr", type=int, help="PR 编号")
    target.add_argument("--head", type=str, help="来源分支（默认当前分支）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只收集上下文并生成 prompt，不访问 ChatGPT、不发布")
    mode.add_argument("--no-post", action="store_true", help="完整走 ChatGPT，但解析后只打印，不发布 Review")
    mode.add_argument("--manual", action="store_true", help="降级：生成 prompt，等用户粘贴回复后解析发布")
    parser.add_argument("--login", action="store_true", help="打开浏览器引导登录 chatgpt.com 后退出（初始化专用 profile）")
    parser.add_argument("--profile-dir", type=str, default=os.environ.get("NORA_CHATGPT_PROFILE"), help="已登录 ChatGPT 的浏览器 profile（缺省读 $NORA_CHATGPT_PROFILE）")
    parser.add_argument("--headed", action="store_true", help="web 模式显示浏览器窗口（默认）")
    parser.add_argument("--headless", action="store_true", help="web 模式无头运行")
    parser.add_argument("--output-dir", type=str, help="prompt/模板/回复输出目录（默认系统临时目录）")
    parser.add_argument("--timeout", type=int, default=600, help="生成等待上限（秒）")
    parser.add_argument("--force", action="store_true", help="已存在同作者 Review 时仍重新发布")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.login:
        if not args.profile_dir:
            parser.error("--login 需要 --profile-dir 或 NORA_CHATGPT_PROFILE")
        login(args.profile_dir)
        print(f"[login] 会话已保存：{args.profile_dir}")
        return 0

    if args.headed and args.headless:
        parser.error("--headed 与 --headless 不能同时指定")

    pr = resolve_pr_number(args.pr, args.head)
    context = collect_context(pr)
    prompt = build_prompt(context)

    output_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / f"prompt-{pr}.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    if args.dry_run:
        print(f"[dry-run] PR #{pr}：{context.title}")
        print(f"[dry-run] 变更 +{context.additions}/-{context.deletions}，{context.changed_files} 文件，CI: {context.checks or 'n/a'}")
        print(f"[dry-run] prompt 已生成：{prompt_path}")
        return 0

    if args.manual:
        reply = _read_reply_manual(pr, output_dir)
    else:
        if not args.profile_dir:
            parser.error("web 模式需要 --profile-dir 或 NORA_CHATGPT_PROFILE")
        headed = not args.headless
        reply = chatgpt_review(prompt, args.profile_dir, headed, args.timeout)
        (output_dir / f"reply-{pr}.txt").write_text(reply, encoding="utf-8")

    verdict = parse_reply(reply)
    review_body = render_review(verdict, context)
    review_path = output_dir / f"review-{pr}.md"
    review_path.write_text(review_body, encoding="utf-8")
    print(f"[review] 结论：{verdict.conclusion}（{len(verdict.suggestions)} 条建议）")
    print(f"[review] review body 已生成：{review_path}")

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
