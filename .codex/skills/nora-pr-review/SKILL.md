---
name: nora-pr-review
description: Review one Nora Pull Request with the OpenAI ChatGPT web session via local Playwright automation, and publish the verdict as a formal GitHub PR review (approve or request-changes with suggestions) using a fixed template. Use whenever a PR for a Nora delivery branch needs automated review, or a REQUEST_CHANGES review requires re-review after fixes.
---

# Nora PR 自动审核流程

一次审核一个 PR。读取 `docs/ARCHITECTURE.md`、Issue 验收条件与 PR diff，给出「通过 / 不通过」结论，并通过 GitHub
**PR Review 正式审核**发布（通过 = APPROVE；不通过 = REQUEST_CHANGES + 修改建议）。结论只有两种，review body 使用固定模板。

## 审核门禁

1. 确认 `gh auth status` 已登录，仓库远端可访问。
2. 确认目标 PR 存在，来源分支为 `nora/`，且正文包含唯一 `Closes #<Issue>`。
3. 确认 Playwright 与 Chromium 已按 `docs/DEVELOPMENT.md` 安装；ChatGPT 登录会话可用（否则先执行 `--login`）。
4. 不把浏览器 profile、Cookie、ChatGPT 回复原文或 prompt 写入仓库工作树（一律走系统临时目录）。

## 读取范围

- `gh pr view --json title,body,url,additions,deletions,changedFiles,headRefName,baseRefName`
- `gh pr diff <n>`
- `gh pr checks <n>`
- 关联 Issue 正文与验收条件（`gh issue view <n> --json body`）
- `docs/ARCHITECTURE.md` 依赖方向与边界（Domain 不得导入 FastAPI/SQLAlchemy/LangGraph）

## 审核步骤

1. 推导 PR 编号：显式 `--pr <n>`，或 `gh pr list --head <当前分支> --json number --jq '.[0].number'`。
2. 收集上下文，组装固定 prompt（`scripts/review_prompt_template.md` + 上下文 + diff）。
3. 调用 `python .codex/skills/nora-pr-review/scripts/nora_review.py`（参数见脚本 CLI）。
4. 解析结论：通过 → `gh pr review --approve`；不通过 → `--request-changes`，建议填入 `scripts/review_template.md`。
5. 发布后回读 `gh pr view <n> --json reviews` 确认结论与正文完整；删除临时文件。

## 判定标准（不通过至少满足其一）

- 破坏依赖方向或架构边界；
- 缺测试，或测试与契约不符，或测试跳过未记录原因；
- 引入密钥/凭据、敏感数据或未经审批的外部写；
- 混入 Issue 范围外变更；
- 文档未同步，或验收条件未满足。

## 失败降级

- ChatGPT 选择器失效或未登录 → `--manual` 模式：生成 prompt 文件，等用户粘贴回复后解析发布。
- 审核结论无法解析 → 报错并给出 `--manual` 指引，不猜测结论，不发布 Review。
