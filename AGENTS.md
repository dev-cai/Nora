# Nora Agent Instructions

在本仓库执行 Issue 选择、实现、修复、文档、测试、Commit、Push 或 Pull Request 工作时，必须先读取并遵循：

- `.codex/skills/nora-create-issue/SKILL.md`（创建、拆分、标记或规划 Issue 时）
- `.codex/skills/nora-issue-pr-workflow/SKILL.md`
- `CONTRIBUTING.md`
- `docs/ISSUE_WORKFLOW.md`

仓库初始化提交之后，严格执行“一 Issue、一分支、一 PR；合并后再开始下一项”。新分支统一使用
`nora/<type>-<subject>`。未经 Architecture Issue 和审查，不得提前创建应用目录、选择运行时依赖或实现业务代码。

实现与本地验证完成后，必须先提交给用户手动验收。未经用户针对当前待验收版本明确授权，不得执行 `git push`、
创建 PR 或进行任何依赖远端分支的操作；发生实质修改后，之前的推送授权自动失效，必须重新验收。
