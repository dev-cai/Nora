# Nora Agent Instructions

在本仓库执行 Issue 选择、实现、修复、文档、测试、Commit、Push 或 Pull Request 工作时，必须先读取并遵循：

- `.codex/skills/nora-create-issue/SKILL.md`（创建、拆分、标记或规划 Issue 时）
- `.codex/skills/nora-issue-pr-workflow/SKILL.md`
- `.codex/skills/nora-pr-review/SKILL.md`（触发或处理 PR 自动审核时）
- `CONTRIBUTING.md`
- `docs/ISSUE_WORKFLOW.md`

仓库初始化提交之后，严格执行“一分支、一 PR；合并后再开始下一项”。Issue 可选：关联时 PR 用
`Closes #<编号>` 关闭，一个 PR 最多关闭一个 Issue。新分支统一使用 `nora/<type>-<subject>`。
未经 Architecture Issue 和审查，不得提前创建应用目录、选择运行时依赖或实现业务代码。
Issue 标题使用自然中文，可选择性添加 `M<n>` 或 `M<n>.<n>` Milestone 前缀；不得使用类型方括号、
`Roadmap`/`Phase` 固定前缀或 Issue 编号前缀。

实现与本地验证完成后，直接推送分支、创建唯一 PR 并触发自动审核（`.codex/skills/nora-pr-review`）。自动审核不通过时
按建议修改并重新推送重审；自动审核通过不代表合并授权，PR 合并仍需用户显式授权。
