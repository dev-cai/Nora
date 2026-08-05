---
name: nora-issue-pr-workflow
description: Execute Nora repository delivery through its mandatory Issue, nora-prefixed branch, Chinese-first Conventional Commit, local verification, automatic push and Pull Request, automated review, CI, and merge gates. Use whenever selecting, implementing, fixing, documenting, testing, committing, pushing, opening a PR, triggering automated review, or reporting completion for work in the Nora repository.
---

# Nora Issue 与 PR 流程

始终保持“一分支、一 PR；合并后再开始下一项”。Issue 可选：关联时 PR 用 `Closes #<编号>` 关闭。仓库首次治理初始化提交是唯一例外。

## 开始门禁

1. 读取 `AGENTS.md`、`CONTRIBUTING.md` 和 `docs/ISSUE_WORKFLOW.md`。
2. 检查工作树、当前分支、远端、已有 Issue 和 PR；不得覆盖用户修改或混入其他 Issue。
3. 实现前范围必须明确；如有关联前置依赖 Issue，需已合并（Issue 可选）。
4. 已有尚未合并的交付项时继续该项，不开始下一个依赖项。

## Issue 与分支

Issue 标题直接描述真实问题，允许可选 `M<n>` 或 `M<n>.<n>` Milestone 前缀；禁止 Roadmap/Phase 固定前缀、
类型方括号和 Issue 编号前缀。正文包含背景、范围、非目标、验收和验证计划。

从最新 `origin/main` 创建：

```text
nora/<type>-<english-subject>
```

例如 `nora/feat-user-identity`、`nora/docs-architecture-decisions`。禁止为新分支使用 `codex/` 或 `agent/`。

## Commit

```text
<type>(<optional-scope>): <中文 subject>

<可选正文：原因、边界与兼容性影响>

Refs #<Issue>
```

标准 type：

- `feat`：新功能。
- `fix`：修复缺陷。
- `docs`：仅文档变更。
- `style`：不影响逻辑的格式调整。
- `refactor`：不新增功能也不修复缺陷的重构。
- `perf`：性能优化。
- `test`：新增或修改测试。
- `chore`：维护和辅助工具调整。
- `build`：构建系统或外部依赖变更。
- `ci`：持续集成配置或脚本变更。
- `revert`：回滚提交。

`subject` 是冒号后的摘要，使用中文动宾短语描述真实结果，不以句号结尾。Issue 只在 PR 正文使用 `Closes`；Commit 使用 `Refs`。

## 实现与验证

- 只修改 Issue 范围，同步适用测试和文档。
- 代码、配置或工作流变化时，读取 `docs/docs-contract.toml` 中命中的规范文档；Current 能力及证据只更新
  `docs/current-capabilities.toml`，不在长期文档中另建并行台账。
- 推送前运行 `python scripts/docs/check_impact.py --base origin/main`。PR 正文必须完整填写“文档影响”结构化字段；无需更新文档时写明
  具体原因，不机械修改无关文档。
- 按当前技术栈执行静态、格式、类型、单元/契约测试和 `git diff --check`。
- 按 Issue 执行集成测试；外部服务不可用时完成其余检查并记录跳过原因。
- 不把未执行的检查写成通过，不用构建通过替代行为与安全审查。

## 推送与自动审核

本地实现、验证和 Commit 完成后，不请求人工验收，直接：

1. 将 Issue 正文状态更新为 `review`；
2. 推送唯一 `nora/` 分支；
3. 创建唯一 PR（正文包含唯一 `Closes #<Issue>`，使用 UTF-8 无 BOM 文件 + `--body-file`，见下方「GitHub 正文写入安全」）；
4. 调用 `.codex/skills/nora-pr-review/scripts/nora_review.py --pr <N>` 触发自动审核，结论通过 `gh pr review` 正式发布。

自动审核不通过（REQUEST_CHANGES）时：将 Issue 状态改回 `in-progress`，按审核建议修改、验证、Commit 并重新推送，再次
触发自动审核。审核通过（APPROVE）不代表合并授权，PR 合并仍需用户显式授权。

## Pull Request

- 本地验证完成后，推送唯一 `nora/` 分支并创建唯一 PR。
- 标题使用 `<type>(<optional-scope>): <中文 subject>`。
- 如关联 Issue，正文恰好包含一个 `Closes #<Issue>`；无论是否关联 Issue，均写明背景、实际变更、非目标、风险、验证和审查提示。
- 正文包含结构化“文档影响”章节，列明受影响事实、已更新事实源或无文档变更的具体理由。
- 等待 CI 与自动审核。除非用户明确授权，不擅自合并。

PR 未合并时只报告 PR、CI 和自动审核状态，不称 Issue 或功能已完成。合并关闭 Issue 后才开始下一项。

## GitHub 正文写入安全

多行中文 Issue/PR 正文的 UTF-8 写入、回读与临时文件清理规则，见 `docs/ISSUE_WORKFLOW.md`「GitHub 多行正文写入」。
写入后必须立即回读线上正文，检查中文、章节换行、列表、复选框、代码块、状态和 Issue 关闭关键字，完成后删除临时文件。
