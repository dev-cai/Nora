<p align="center">
  <img src="https://img.shields.io/badge/AI-工作指南-8A2BE2?style=flat-square" alt="AI 工作指南">
  <img src="https://img.shields.io/badge/status-planning-yellow?style=flat-square" alt="状态">
</p>

# Nora — Claude 工作指南

---

## 项目概述

```
  Nora（Navigate · Observe · Review · Agent）
  面向求职决策的可审计多智能体平台。
  Agentic RAG 驱动的求职决策报告系统。
```

**当前阶段：** 规划与文档阶段。仓库包含协作规范、GitHub 模板、项目 Skill、流程校验脚本和初版架构。**尚无应用代码。**

---

## 关键文档索引

开始任何工作前，优先阅读以下文档：

| 文档 | 说明 |
|------|------|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献指南与交付流程 |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | 完整交付操作手册（12 步） |
| [`docs/ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md) | Issue 类型、标签、状态规则 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 系统架构（22 章节） |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 里程碑计划与验收条件 |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | 领域术语表 |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Docker 优先开发指南 |
| [`docs/M0_PLAN.md`](docs/M0_PLAN.md) | M0 工程基础 Issue 拆分 |

### 项目 Skill（`.codex/skills/`）

- `nora-create-issue` — Issue 创建工作流（新建 Issue 时必须使用）
- `nora-issue-pr-workflow` — PR 交付工作流

---

## 核心原则

- **Evidence First** — 关键结论必须引用可定位证据
- **业务事实在 PostgreSQL** — 缓存、向量、Agent State 不是事实源
- **模型输出不可信** — 必须经过 Schema + 策略校验
- **Agent 只做编排** — 不直接访问 ORM、数据库或外部 SDK
- **外部写默认关闭** — 需审批、幂等、审计
- **一 Issue 一 PR** — `nora/` 分支只对应一个 Issue，合并后再开始下一项
- **中文优先** — Commit、PR、文档用中文，代码标识用英文

---

## 代码规范

### 分支命名

```
  nora/<type>-<subject>

  示例：
  nora/feat-user-identity      新功能
  nora/fix-request-timeout      修复缺陷
  nora/docs-architecture       文档变更
  nora/ci-pr-conventions        CI 配置
```

### Commit 格式

```
  <type>(<optional-scope>): <中文 subject，不超过 72 字符>

  示例：
  feat(api): 实现岗位快照创建接口
  docs(architecture): 更新数据所有权章节
```

| type | 使用场景 |
|------|---------|
| `feat` | 新功能、新接口、新模块 |
| `fix` | 修复缺陷 |
| `docs` | 文档、注释变更 |
| `refactor` | 重构（不新增功能也不修 Bug） |
| `test` | 新增或修改测试 |
| `chore` | 工具配置、依赖维护 |
| `ci` | CI 配置变更 |

Commit 正文按需解释原因，引用 Issue：`Refs #<编号>`。

### PR 要求

- 正文必须以 `Closes #<编号>` 开头
- 包含：背景与目标、实际变更、明确未包含、影响分析、验证结果
- 禁止使用 `[Roadmap]`、`[Phase]`、`[Implementation]` 前缀
- main 禁止直接推送和 force-push，Squash Merge 合并

---

## 工作流程

### 10 步交付

```
  创建/搜索 Issue -> 认领 -> 从 main 分支 -> 编码 + 测试
  -> Commit -> 用户人工验收 -> 推送 + PR -> CI -> 合并 -> 关闭 Issue
```

### 人工验收门禁（强制）

```
  本地实现完成 ≠ 可以推送。

  必须提交的验收清单：
    Issue 编号与链接
    分支名与本地 Commit
    基于真实 diff 的变更摘要
    已执行验证与实际结果
    未执行检查及原因
    用户可直接操作的验收步骤

  只有用户明确说"可以推送"后才能执行 git push。
  授权只对当前版本有效，修改后授权自动失效。
  推送授权不包含合并授权，PR 仍需 CI + 审查 + 显式合并。
```

### Issue 状态

```
  ready ──> in-progress ──> acceptance ──> review
    │                          │
    └── blocked                └── in-progress（用户要求修改）
```

---

## 架构要点

### 依赖方向（架构测试强制验证）

```
  Apps/Adapters → Application → Domain
```

**Domain** 只使用 Python 标准库。导入 FastAPI、SQLAlchemy、LangGraph 在 CI 中被阻断。

### 7 个领域上下文

```
  Identity & Preferences    身份、偏好、隐私
  Career Profile            简历版本、已确认经历
  Opportunity Intelligence  公司岗位快照、风险证据
  Interview Journey         面试计划、准备、出行、复盘
  Decision & Reporting      决策分析与报告生成
  Knowledge & Evidence      来源快照、Chunk、检索、证据
  Automation & Governance   Agent 运行、审批、审计
```

### 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python >=3.11 |
| 包管理 | uv（`UV_SYSTEM_PYTHON=1`，无虚拟环境） |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL + pgvector |
| ORM | SQLAlchemy（异步） |
| 异步任务 | Celery + Redis（M4 引入） |
| 对象存储 | MinIO / S3 |
| Agent 框架 | LangGraph Adapter |
| 模型网关 | Provider-neutral |
| 测试 | pytest |
| 代码质量 | ruff + mypy（严格模式） |

### 开发环境

- **Docker 优先** — 所有开发、测试、代码检查在容器中运行
- 宿主机只需 Docker 和 Docker Compose，无需 Python、pip、`.venv`
- 源码通过 volume 挂载，修改即时生效（uvicorn `--reload`）
- 工具缓存存储在容器内，不写入项目目录
- 详见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)

### 数据所有权

| 数据 | 权威存储 | 性质 |
|------|---------|------|
| 用户、画像、岗位、面试、报告 | PostgreSQL | 业务事实 |
| Agent 运行、审批、审计 | PostgreSQL | 治理事实（追加式） |
| 原始简历、附件 | Object Storage | 不可变对象 |
| Chunk、Embedding | pgvector（可重建） | 派生数据 |
| 缓存、锁、限流 | Redis | 临时状态（TTL） |

### 测试策略

```
  Unit -> Architecture -> Contract -> Integration -> E2E -> Dynamic
```

### 安全注意事项

- 身份来自认证上下文，不信任请求正文中的 `user_id`
- 日志不记录简历正文、面试回答、Token、Cookie、完整 Prompt
- URL 获取限制协议、域名、重定向、大小和超时（防 SSRF）
- Tool 参数只来自受控 Schema，不从网页文本动态生成动作

---

## 里程碑路线

```
  M0: 工程基础与 CI 门禁     包骨架、FastAPI、PostgreSQL、Docker、CI
  M1: Identity + 岗位快照   认证、岗位 CRUD、幂等、审计
  M2: 简历 + RAG 基础       简历、Source->Chunk->检索、Evidence Pack
  M3: 最小化 Demo           决策报告、Gradio 演示
  M4: 中间件 + 生产准备      Redis/Celery、安全扫描、部署文档
  M5+: 专项 Agent + 拆分     Agent Runtime、Milvus 评估
```

详见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。
