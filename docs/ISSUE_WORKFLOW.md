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
中文优先 Commit 并推送
        ↓
创建唯一 PR，正文使用 Closes #<Issue>
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

## 标签、状态与 Milestone

- 每个 Issue 必须且只能具有一个 `type:*`、一个 `priority:*` 和至少一个 `area:*`。
- 创建状态只允许 `ready` 或 `blocked`；产生实质修改后为 `in-progress`；创建 PR 后为 `review`。
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
