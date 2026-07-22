---
name: nora-issue-pr-workflow
description: Execute Nora repository delivery through its mandatory Issue, nora-prefixed branch, Chinese-first Conventional Commit, Pull Request, CI, review, and merge gates. Use whenever selecting, implementing, fixing, documenting, testing, committing, pushing, opening a PR, or reporting completion for work in the Nora repository.
---

# Nora Issue 与 PR 流程

始终保持“一 Issue、一分支、一 PR；合并后再开始下一项”。仓库首次治理初始化提交是唯一例外。

## 开始门禁

1. 读取 `AGENTS.md`、`CONTRIBUTING.md` 和 `docs/ISSUE_WORKFLOW.md`。
2. 检查工作树、当前分支、远端、已有 Issue 和 PR；不得覆盖用户修改或混入其他 Issue。
3. 实现前必须存在真实、可验收且前置依赖已合并的 Issue。
4. 已有尚未合并的交付项时继续该项，不开始下一个依赖项。

## Issue 与分支

Issue 标题直接描述真实问题，不加 Roadmap、Phase、序号或类型方括号前缀。正文包含背景、范围、非目标、验收和验证计划。

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
- 按当前技术栈执行静态、格式、类型、单元/契约测试和 `git diff --check`。
- 按 Issue 执行集成测试；外部服务不可用时完成其余检查并记录跳过原因。
- 不把未执行的检查写成通过，不用构建通过替代行为与安全审查。

## Pull Request

- 推送唯一 `nora/` 分支并创建唯一 PR。
- 标题使用 `<type>(<optional-scope>): <中文 subject>`。
- 正文恰好包含一个 `Closes #<Issue>`，并写明背景、实际变更、非目标、风险、验证和审查提示。
- 等待 CI 最终结果。除非用户明确授权，不擅自合并。

PR 未合并时只报告 PR 和 CI 状态，不称 Issue 或功能已完成。合并关闭 Issue 后才开始下一项。
