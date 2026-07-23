<p align="center">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="欢迎 PR">
  <img src="https://img.shields.io/badge/conventional%20commits-1.0.0-FE5196?style=flat-square&logo=conventionalcommits" alt="Conventional Commits">
</p>

# 贡献指南

> **Issue 驱动开发。** 所有变更从 Issue 开始 — 一个 Issue、一个分支、一个 PR。
>
> 详细操作步骤见 [`docs/WORKFLOW.md`](docs/WORKFLOW.md)。<br>
> 环境搭建见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。

---

## 交付流水线

```
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ 1. 创建  │   │ 2. 认领  │   │ 3. 从    │   │ 4. 编码  │   │ 5. 本地  │
  │ 或搜索   │──>│ 或创建   │──>│ main     │──>│ + 测试   │──>│ 门禁    │
  │ Issue    │   │ Issue    │   │ 分支     │   │ + Commit │   │ 检查    │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
       │                                              │              │
       v                                              v              v
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ 6. 用户  │   │ 7. 推送  │   │ 8. CI   │   │ 9. 用户  │   │ 10. 完成 │
  │ 人工验收 │──>│ 分支     │──>│ 通过    │──>│ 合并授权 │──>│ Issue    │
  │          │   │ + 创建PR │   │         │   │ Squash  │   │ 关闭    │
  │          │   │         │   │         │   │ Merge   │   │ 分支删除 │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
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

### 状态流转

状态记录在 Issue 正文中，不使用 `status:*` 标签：

```
  ready  ──>  in-progress  ──>  acceptance  ──>  review
   │                               │
   └── blocked（等待前置依赖）      └── in-progress（用户要求修改）
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
  Closes #<编号>             #  一个 PR 只关闭一个 Issue
  背景与目标                  #  为什么现在需要这项变更
  实际变更                    #  基于真实 diff
  明确未包含                  #  非目标
  影响分析                    #  配置、数据、兼容性、安全、外部写
  验证结果                    #  执行的命令与实际结果
  未执行检查及原因             #  跳过项
  审查重点                    #  需要关注的边界或决策
```

**禁止使用：** `[Roadmap]`、`[Phase]`、`[Implementation]` 等固定方括号前缀。

---

## 人工验收门禁

> 本地实现完成 **不等于** 允许推送。

推送前必须向用户提交验收清单：

```
  Issue 编号与链接
  当前分支与本地 Commit
  基于真实 diff 的变更摘要
  已执行验证及其实际结果
  未执行检查及原因
  用户可直接操作的验收步骤
```

推送授权 **只对当前待验收版本有效**。授权后若发生实质修改，必须重新请求验收。该授权不包含合并授权，PR 仍需通过 CI、审查和显式合并。

---

## 合并策略

```
  main 分支     ───  禁止直接推送，禁止 force-push
  PR 合并       ───  仅 Squash Merge，PR 标题作为 main 的 Commit 标题
  CI 门禁       ───  必须通过全部检查
  审查          ───  所有意见必须解决后方可合并
  清理          ───  合并后自动删除来源分支
```

---

## 安全边界

- **不提交敏感信息。** 不提交 `.env`、密钥、Cookie、浏览器会话、真实简历或其他个人数据
- **不新增未审批的依赖。** 新增运行时依赖、数据所有权或外部写能力必须通过 Architecture Issue
- **优雅降级。** 外部系统不可用时，完成本地静态、单元和契约检查，并明确记录跳过原因
- **测试不等于安全。** 构建或测试通过不能替代安全和真实调用链审查
