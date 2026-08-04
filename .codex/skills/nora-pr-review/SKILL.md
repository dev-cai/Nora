---
name: nora-pr-review
description: Review one Nora Pull Request by having Codex itself read the rendered review instruction and produce a verdict, then publish it as a formal GitHub PR review (approve or request-changes with suggestions) using a fixed template. Requires no browser, no API key, and no session token. Use whenever a PR for a Nora delivery branch needs automated review, or a REQUEST_CHANGES review requires re-review after fixes.
---

# Nora PR 自动审核流程

一次审核一个 PR。审核智能由 **Codex 应用自身**提供（不启动浏览器、不需要 API Key 或 session token）：脚本只负责渲染
审核指令、解析结论并发布。结论只有「通过 / 不通过」两种，通过 GitHub **PR Review 正式审核**发布（通过 = APPROVE；
不通过 = REQUEST_CHANGES + 修改建议），review body 使用固定模板。

## 审核门禁

1. 确认 `gh auth status` 已登录，仓库远端可访问。
2. 确认目标 PR 存在，来源分支为 `nora/`，且正文包含唯一 `Closes #<Issue>`。
3. 审核由 Codex 自身完成，不依赖浏览器、API Key 或 session token。
4. 不把 prompt、回复原文或 review body 写入仓库工作树（一律走系统临时目录）。

## 读取范围

- `gh pr view --json title,body,url,additions,deletions,changedFiles,headRefName,baseRefName`
- `gh pr diff <n>`
- `gh pr checks <n>`
- 关联 Issue 正文与验收条件（`gh issue view <n> --json body`）
- `docs/ARCHITECTURE.md` 依赖方向与边界（Domain 不得导入 FastAPI/SQLAlchemy/LangGraph）

## 审核步骤

1. 推导 PR 编号：显式 `--pr <n>`，或 `gh pr list --head <当前分支> --json number --jq '.[0].number'`。
2. 运行 `python .codex/skills/nora-pr-review/scripts/nora_review.py --prepare --pr <n>`，生成审核指令文件
   （含 PR 上下文、diff、判定标准与输出格式），路径会打印到输出。
3. 阅读该指令文件，按其「输出格式」严格产出结论（首行「审核结论：通过/不通过」+ `<!-- review-json -->` 包裹的 JSON 块），
   保存到 `<输出目录>/reply-<n>.md`。
4. 运行 `python .codex/skills/nora-pr-review/scripts/nora_review.py --submit --pr <n>`，解析结论并发布 PR Review。
5. 发布后回读 `gh pr view <n> --json reviews` 确认结论与正文完整；删除临时文件。

## 判定标准（不通过至少满足其一）

- 破坏依赖方向或架构边界；
- 缺测试，或测试与契约不符，或测试跳过未记录原因；
- 引入密钥/凭据、敏感数据或未经审批的外部写；
- 混入 Issue 范围外变更；
- 文档未同步，或验收条件未满足。

## 失败降级

- 结论无法解析（reply 未按格式输出）→ 修正 reply 文件后重跑 `--submit`；不猜测结论、不发布 Review。
- `gh` 命令失败或网络不可用 → 先解决环境问题再重试；必要时改用 `--no-post` 只生成 review body 供人工发布。
