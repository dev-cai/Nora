---
name: nora-create-issue
description: Draft, validate, preview, and create one Nora GitHub Issue with the required type, priority, area labels, lifecycle status, dependencies, milestone, boundaries, acceptance criteria, and verification plan. Use whenever a user asks to create, draft, plan, split, label, prioritize, or inspect a Nora Issue, Epic, architecture decision, bug report, or documentation task.
---

# Nora Issue 创建流程

一次只创建一个真实、可验收的 Issue。读取 `AGENTS.md`、`docs/ISSUE_WORKFLOW.md`、`.github/labels.json` 和适用的 `.github/ISSUE_TEMPLATE/`。

## 创建门禁

1. 检查 `git status --short --branch`、远端、全部打开的 Issues 和 PRs。
2. 用标题、领域、目标和影响范围搜索重复项；存在重复项时报告并停止创建。
3. 已有尚未合并的主线 Issue/PR 时，不创建下一个依赖任务；允许创建用于解除当前阻塞的明确 Issue。
4. 安全漏洞、密钥、个人数据或利用细节转到 Private vulnerability reporting，不创建公开 Issue。
5. 依据真实仓库证据写内容；不把路线图、计划或未验证技术选择描述为已实现事实。

## 类型选择

- `type:architecture`：架构、数据所有权、边界或技术决策。
- `type:epic`：跨多个原子 Task 的父级目标；Epic 不直接承载生产实现。
- `type:task`：一个主要模块、一个主要交付物的原子实现或维护任务。
- `type:bug`：已存在、可稳定复现且偏离已确认契约的缺陷。
- `type:docs`：仅文档、模板、Skill 或治理变更。

每个 Issue 必须且只能包含一个 `type:*`、一个 `priority:*` 和至少一个 `area:*`。超过两个 area 时优先拆分 Issue。

## 状态与关系

创建时状态只允许：

- `ready`：依赖和决策均满足，可开始实施。
- `blocked`：存在明确未满足依赖或缺失决策。

创建分支并产生实质修改后更新为 `in-progress`；本地待验收版本完成后更新为 `acceptance`；用户授权推送并创建 PR 后更新为
`review`。用户要求修改时从 `acceptance` 返回 `in-progress`。不创建重复的 `status:*` 标签。

`Parent Epic` 只表达层级归属；`依赖` 只列真正阻塞执行的 Issue、Contract、环境或生成物。无内容时写 `—`，不得混用。

Architecture、Epic 和 Task 必须进入真实 Milestone。Bug 与 Documentation 在影响当前 Milestone 时也应归入；不得为单个 Issue 临时编造阶段。

## 标题与正文

标题使用自然中文，直接描述问题或结果；不添加 `[Roadmap]`、`[Phase]`、类型方括号、流水线编号或 Issue 编号。

正文严格使用对应模板的章节。验收条件必须可客观判断；验证部分列出具体检查、预期证据和不可执行项的报告方式。

## 预览与验证

除非用户明确说“直接创建”，先展示：标题、类型、优先级、领域、Milestone、Assignee 和完整正文。用户确认后再创建。

将最终载荷保存为 JSON 或通过标准输入传给：

```powershell
python .codex/skills/nora-create-issue/scripts/validate_issue.py --input -
python .codex/skills/nora-create-issue/scripts/sync_labels.py --check
```

任一检查失败时修正草稿，不绕过验证。

## 创建与回读

使用 UTF-8 JSON 调用 GitHub API 创建 Issue，显式传入标题、正文、Labels、Milestone 和 Assignee。创建后重新读取线上 Issue，确认：

- 标题与正文无乱码；
- 标签数量和类别正确；
- Milestone 与 Assignee 正确；
- 状态、Parent Epic 和依赖与预览一致。

最终返回 Issue 编号、URL、标签、Milestone、状态和下一步门禁，不自动创建分支或开始实现。
