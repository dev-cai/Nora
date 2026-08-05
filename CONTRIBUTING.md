<p align="center">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="欢迎 PR">
  <img src="https://img.shields.io/badge/conventional%20commits-1.0.0-FE5196?style=flat-square&logo=conventionalcommits" alt="Conventional Commits">
</p>

# 贡献指南

> **PR 驱动交付。** 一个 PR、一个分支；Issue 可选（关联时用 `Closes #<编号>` 关闭）。
>
> 详细操作步骤见 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)；Issue 类型、标签、状态见 [`docs/ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md)。<br>
> 环境搭建见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。

---

## 交付流水线

```
  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
  │ 1. 从      │   │ 2. 编码    │   │ 3. 本地    │   │ 4. 推送    │
  │ main       │──>│ + 测试     │──>│ 门禁       │──>│ 分支       │
  │ 建分支     │   │ + Commit   │   │ 检查       │   │ + 创建 PR  │
  └────────────┘   └────────────┘   └────────────┘   └────────────┘
        │                                                 │
        v                                                 v
  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
  │ 5. 自动    │   │ 6. 用户    │   │ 7. 关闭    │   │ 8. 删除    │
  │ 审核       │──>│ 合并授权   │──>│ 关联 Issue │──>│ 分支       │
  │ 通过       │   │ Squash     │   │（如有）    │   │            │
  └────────────┘   └────────────┘   └────────────┘   └────────────┘
```

---

## Issue 标签

每个 Issue 必须有且仅有一个 `type:*`、一个 `priority:*`、至少一个 `area:*`。

```
  类型（type）      ───  architecture | epic | task | bug | docs
  优先级（priority） ───  p0（阻塞） | p1（重要） | p2（一般） | p3（后续）
  领域（area）      ───  architecture | backend | frontend | agent | rag
                          data | infra | security | docs
```

标签真源为 `.github/labels.json`。

### Issue 标题

标题使用自然中文直接描述问题或结果，可选择性添加 `M<n>` 或 `M<n>.<n>` Milestone 前缀，例如
`M1.4 实现审计日志`。不得使用类型方括号、`[Roadmap]`、`[Phase]` 或 `#59` 这类 Issue 编号前缀。

### 状态流转

状态记录在 Issue 正文中，不使用 `status:*` 标签：

```
  ready  ──>  in-progress  ──>  review
   │                               │
   └── blocked（等待前置依赖）     └── in-progress（自动审核要求修改、PR 未合并）
```

---

## 分支规范

```
  nora/<type>-<subject>
```

| 部分 | 规则 |
|------|------|
| `type` | `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci` |
| `subject` | 小写英文、数字、连字符，概括交付内容 |

```
  nora/feat-user-identity        #  新功能
  nora/fix-request-timeout        #  修复缺陷
  nora/docs-architecture          #  文档变更
  nora/ci-pr-conventions          #  CI 配置
```

**禁止的前缀：** `codex/`、`agent/`、`roadmap`、`phase`、Issue 标题全文。

---

## Commit 格式

```
  <type>(<optional-scope>): <中文 subject，不超过 72 字符>
```

| type | 含义 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(api): 实现用户注册功能` |
| `fix` | 修复缺陷 | `fix: 修复登录页面崩溃问题` |
| `docs` | 仅文档变更 | `docs: 更新架构说明` |
| `style` | 格式调整 | `style: 删除多余空行` |
| `refactor` | 重构 | `refactor: 重构用户验证逻辑` |
| `perf` | 性能优化 | `perf: 优化检索响应时间` |
| `test` | 新增或修改测试 | `test: 增加用户模块单元测试` |
| `chore` | 维护工具 | `chore: 更新开发工具配置` |
| `build` | 构建系统 | `build: 升级 FastAPI 依赖` |
| `ci` | CI 配置 | `ci: 调整 GitHub Actions 配置` |
| `revert` | 回滚 | `revert: 回滚用户注册功能` |

Commit 正文按需解释原因、边界与兼容性影响，引用 Issue：`Refs #<编号>`。

---

## Pull Request

```yaml
title:   "<type>(<scope>): <中文 subject>"
body:
  Closes #<编号>（可选）      #  如有关联 Issue，一个 PR 最多关闭一个
  背景与目标                  #  为什么现在需要这项变更
  实际变更                    #  基于真实 diff
  明确未包含                  #  非目标
  影响分析                    #  配置、数据、兼容性、安全、外部写
  文档影响                    #  影响事实、更新事实源或具体豁免理由
  验证结果                    #  执行的命令与实际结果
  未执行检查及原因             #  跳过项
  审查重点                    #  需要关注的边界或决策
```

**禁止使用：** `[Roadmap]`、`[Phase]`、`[Implementation]` 等固定方括号前缀。

代码、配置或工作流变化时，以 [`docs/docs-contract.toml`](docs/docs-contract.toml) 计算受影响的规范文档。推送前运行
`python scripts/docs/check_impact.py --base origin/main`；事实未变化时可不修改文档，但必须在 PR 的“文档影响”章节给出具体理由。
当前已交付能力和证据以 [`docs/current-capabilities.toml`](docs/current-capabilities.toml) 为唯一台账。

---

## 自动审核门禁

> 本地实现完成并通过本地门禁后，直接推送并创建 PR。

推送后触发 Codex 自动审核（`.codex/skills/nora-pr-review`），结论只有「通过 / 不通过」：通过 → APPROVE；不通过 →
REQUEST_CHANGES + 修改建议。自动审核不通过时按建议修改、重新推送并再次触发审核。

自动审核通过 **不包含合并授权**。PR 合并仍需通过 CI、自动审核和用户显式合并授权。

---

## 合并策略

```
  main 分支     ───  禁止直接推送，禁止 force-push
  PR 合并       ───  仅 Squash Merge，PR 标题作为 main 的 Commit 标题
  CI 门禁       ───  必须通过全部检查
  自动审核       ───  必须通过（通过 = APPROVE）后方可合并
  清理          ───  合并后自动删除来源分支
```

---

## 安全边界

- **不提交敏感信息。** 不提交 `.env`、密钥、Cookie、浏览器会话、真实简历或其他个人数据
- **不新增未审批的依赖。** 新增运行时依赖、数据所有权或外部写能力必须通过 Architecture Issue
- **优雅降级。** 外部系统不可用时，完成本地静态、单元和契约检查，并明确记录跳过原因
- **测试不等于安全。** 构建或测试通过不能替代安全和真实调用链审查
