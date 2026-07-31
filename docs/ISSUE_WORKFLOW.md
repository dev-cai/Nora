# Issue 驱动实施流程

## 基本规则

仓库治理初始化提交是唯一可以没有 Issue 的提交。此后所有代码、文档、配置和模板变更都必须关联一个 Issue。

```text
创建或认领 Issue
        ↓
确认范围、非目标、验收与前置依赖
        ↓
从最新 main 创建 nora/<type>-<subject>
        ↓
实现、测试、文档与本地验证
        ↓
中文优先 Commit，形成本地待验收版本
        ↓
用户手动验收并明确授权当前版本
        ↓
推送唯一分支并创建唯一 PR，正文使用 Closes #<Issue>
        ↓
CI 与审查通过后 Squash Merge
        ↓
Issue 关闭并删除分支，再开始下一项
```

## Issue 类型

- Architecture：修改系统边界、数据所有权、依赖方向或技术决策。
- Epic：包含多个原子 Task 的父级目标，不直接承载生产实现。
- Implementation：交付一个进入真实调用路径、可运行且可测试的纵向切片。
- Bug：修复已经存在并可复现的错误行为。
- Documentation：只修改文档或协作规范。
- Security：敏感问题通过 `SECURITY.md` 的私密渠道处理。

## Issue 标题

标题使用自然中文直接描述问题或结果。可以不带阶段信息，也可以选择性添加 `M<n>` 或 `M<n>.<n>` Milestone 前缀，
例如 `建立岗位快照 API` 或 `M1.4 实现审计日志`。禁止类型方括号、`[Roadmap]`、`[Phase]` 和 `#59` 这类
Issue 编号前缀。Milestone 前缀只帮助阅读，不替代真实 Milestone 字段，也不表达依赖关系。

## 标签、状态与 Milestone

- 每个 Issue 必须且只能具有一个 `type:*`、一个 `priority:*` 和至少一个 `area:*`。
- 创建状态只允许 `ready` 或 `blocked`；产生实质修改后为 `in-progress`；本地待验收版本完成后为 `acceptance`；创建 PR 后为 `review`。
- 状态只记录在正文中，不使用 `status:*` 标签。
- Parent Epic 表示层级，依赖表示真正阻塞执行的条件，两者不得混用。
- Architecture、Epic 和 Implementation 必须进入真实 Milestone；Bug 和 Documentation 按影响范围决定。
- 标签定义以 `.github/labels.json` 为准，创建 Issue 时使用项目 Skill `nora-create-issue`。

## Issue 最低信息

- 背景与用户价值；
- 允许范围和明确非目标；
- 前置依赖及其合并状态；
- 对外契约、失败行为和安全边界；
- 可独立验证的验收条件；
- 静态、单元、契约、集成或动态测试计划；
- 文档更新范围。

## 完成边界

只有实现进入真实调用路径、适用测试覆盖契约、文档同步、CI 与审查通过且 PR 已合并，Issue 才能关闭。
单纯创建目录、类、接口、TODO、路线图或占位文件不算完成。

外部服务不可用时，不得伪造“通过”。应完成其余本地检查，并在 PR 中明确列出跳过的测试和原因。

## 推送前人工验收

本地实现、测试和 Commit 完成后，执行者必须停止并向用户提交验收清单。清单至少包含 Issue、分支、本地 Commit、真实变更、
验证结果、未执行检查及用户验收步骤。此时 Issue 状态为 `acceptance`，但分支仍只存在于本地。

未经用户针对当前待验收版本明确授权，不得执行 `git push`、创建 PR 或进行任何以远端分支为前提的操作。用户要求修改时，
Issue 状态返回 `in-progress`，继续在同一分支修正并重新提交验收。任何授权后的实质修改都会使原授权失效，必须再次验收。

用户授权推送不代表授权合并。推送和创建 PR 后，Issue 状态改为 `review`，继续等待 CI、审查和用户的显式合并授权。

## GitHub 多行正文写入

在 Windows PowerShell 中更新 Issue 或 Pull Request 正文时，禁止把 `gh issue view --jq .body`、
`gh pr view --jq .body` 或其他包含多行 Markdown 的命令输出存入普通 PowerShell 变量后直接写回。PowerShell 可能将输出按行
拆成数组并在字符串转换时用空格连接，导致标题、列表、复选框和代码块被压成一行。

多行中文正文必须先写入 UTF-8 无 BOM 文件，再通过 `gh issue edit --body-file <path>`、
`gh pr edit --body-file <path>` 或对应 API 的文件载荷提交。不得依赖 PowerShell 管道的默认编码传递中文 JSON 或 Markdown。

每次远端写入后必须立即回读并验证：

- 中文内容无乱码；
- Markdown 章节仍各自独占一行；
- 列表、复选框和代码块结构完整；
- 状态、Issue 关闭关键字及其他机器可读字段符合预期。

临时正文文件必须在验证完成后删除，并确认不会进入 Commit 或污染工作树。若回读发现格式损坏，应先使用已知正确的完整正文恢复，
不得继续基于损坏正文做字符串替换。
