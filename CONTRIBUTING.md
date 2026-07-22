# 贡献指南

Nora 采用 Issue 驱动开发。除仓库首次治理初始化外，所有变更必须遵循“一 Issue、一分支、一 PR；合并后再开始下一项”。

## 标准交付流程

1. 搜索现有 Issue 和 PR，避免重复工作。
2. 创建或认领一个真实、可验收的 Issue，写明背景、范围、非目标、验收条件和验证计划。
3. 确认前置 Issue 已合并，从最新 `origin/main` 创建唯一分支。
4. 只实现该 Issue 的范围，并同步适用测试和文档。
5. 执行本地门禁，如实记录命令、结果和跳过原因。
6. 使用中文优先的 Conventional Commit，推送当前分支。
7. 创建一个关联该 Issue 的 PR，等待 CI 和审查。
8. PR 合并并关闭 Issue 后，删除分支，再开始下一项。

## Issue 标签与状态

每个 Issue 必须且只能具有一个 `type:*`、一个 `priority:*`，并至少具有一个 `area:*`。跨越三个以上
area 通常意味着范围过大，应优先拆分。标签真源为 `.github/labels.json`。

创建时正文状态只使用 `ready` 或 `blocked`；创建分支并产生实质修改后更新为 `in-progress`，创建 PR 后更新为
`review`。不创建重复的 `status:*` 标签。Parent Epic 只表示层级归属，真正阻塞执行的内容单独写入“依赖”。

## 分支格式

```text
nora/<type>-<subject>
```

- `type` 使用下方标准 Commit 类型。
- `subject` 使用小写英文、数字和连字符，直接概括交付内容。
- 禁止使用 `codex/`、`agent/`、Roadmap、Phase 或 Issue 标题全文作为新分支前缀。

示例：

```text
nora/feat-user-identity
nora/fix-request-timeout
nora/docs-architecture-decisions
nora/ci-pr-conventions
```

## Commit 与 PR 标题

```text
<type>(<optional-scope>): <中文 subject>
```

`subject` 是冒号后的真实结果摘要，使用中文动宾短语，不超过约 72 个字符，不以句号结尾。

| type | 含义 | 示例 |
| :--- | :--- | :--- |
| `feat` | 新功能 | `feat: 增加用户注册功能` |
| `fix` | 修复缺陷 | `fix: 修复登录页面崩溃问题` |
| `docs` | 仅文档变更 | `docs: 更新架构说明` |
| `style` | 不影响逻辑的格式、标点或空白调整 | `style: 删除多余空行` |
| `refactor` | 既不新增功能也不修复缺陷的代码重构 | `refactor: 重构用户验证逻辑` |
| `perf` | 性能优化 | `perf: 优化检索响应时间` |
| `test` | 新增或修改测试 | `test: 增加用户模块单元测试` |
| `chore` | 构建过程以外的维护和辅助工具调整 | `chore: 更新开发工具配置` |
| `build` | 构建系统或外部依赖变更 | `build: 升级构建依赖` |
| `ci` | 持续集成配置或脚本变更 | `ci: 调整 GitHub Actions 配置` |
| `revert` | 回滚之前的提交 | `revert: 回滚用户注册功能` |

Commit 正文按需解释原因、边界与兼容性影响，并使用 `Refs #<Issue>`。Issue 只在 PR 正文中通过
`Closes #<Issue>` 自动关闭。

## Pull Request 正文

PR 必须包含：

- `Closes #<Issue>`，原则上只关闭一个 Issue；
- 背景与目标；
- 基于真实 diff 的实际变更；
- 明确未包含；
- 配置、数据、兼容性、安全、隐私和外部写影响；
- 实际执行的验证命令与结果；
- 未执行检查及原因；
- 审查者需要重点查看的边界或决策。

禁止使用 `[Roadmap]`、`[Phase]`、`[Implementation]` 等固定标题前缀，也禁止“完善相关功能”之类无法核验的描述。

## GitHub 合并策略

- `main` 禁止直接推送和 force-push。
- 只允许通过 PR 合并。
- 推荐只启用 Squash Merge，以 PR 标题作为 `main` 的 Commit 标题。
- 必须通过所需 CI 并解决全部审查意见。
- 合并后自动删除来源分支。

## 安全与边界

- 不提交 `.env`、密钥、Cookie、浏览器会话、真实简历或其他个人数据。
- 未经 Architecture Issue，不新增应用目录、运行时依赖、数据所有权或外部写能力。
- 外部系统不可用时，应完成本地静态、单元和契约检查，并明确记录跳过原因。
- 构建或测试通过不能替代安全和真实调用链审查。
