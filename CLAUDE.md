# Nora — Claude 工作指南

## 项目概述

Nora（**N**avigate · **O**bserve · **R**eview · **A**gent）是一个面向求职决策的可审计多智能体平台。使用 Agentic RAG 组织企业背景、岗位匹配、面试准备、出行规划、风险研判和长期复盘，为用户生成附带证据引用的求职决策报告。

**当前状态**：规划/文档阶段，仓库包含协作规范、GitHub 模板、项目 Skill、流程校验和初版架构，尚无应用代码。

## 关键文档索引

开始任何工作前，优先阅读以下文档：

- `CONTRIBUTING.md` — 贡献指南与交付流程（9 步标准流程）
- `docs/WORKFLOW.md` — 完整开发交付流程（认领 Issue 到 PR 合并）
- `docs/ISSUE_WORKFLOW.md` — Issue 驱动工作流、类型、标签、验收门禁
- `docs/ARCHITECTURE.md` — 系统架构与技术决策（22 章）
- `docs/ROADMAP.md` — 里程碑路线图（M0-M5+ 交付组件、范围边界、验收条件）
- `docs/M0_PLAN.md` — M0 工程基础 Issue 拆分计划
- `docs/GLOSSARY.md` — 术语表
- `docs/DEVELOPMENT.md` — 开发指南（Docker 优先、命令参考）
- `README.md` — 项目核心原则
- `AGENTS.md` — 给 LLM Agent 的指令清单

### 项目 Skill（`.codex/skills/`）

- `nora-create-issue` — 创建 Issue 时必须使用，包含标签校验脚本
- `nora-issue-pr-workflow` — 交付工作流（分支、Commit、验收门禁）

## 核心原则

1. **事实、推断和建议必须明确区分**，关键结论保留来源与版本。
2. **Agent 只编排确定的应用用例**，不直接成为业务事实来源。
3. **不可信输入** — 网页、文档、模型输出和外部回调均视为不可信。
4. **外部写默认关闭**，受审批、幂等、审计和安全边界约束。
5. **一 Issue、一 `nora/` 分支、一 PR**；合并后再开始下一项。
6. **Commit、PR 和文档首选中文**，技术标识保持行业标准写法。

## 代码规范

### 分支命名

```
nora/<type>-<subject>
```

- `type` 使用标准 Commit 类型
- `subject` 使用小写英文、数字和连字符

示例：`nora/feat-user-identity`、`nora/docs-architecture`

### Commit 格式

```
<type>(<optional-scope>): <中文 subject>
```

- subject 是冒号后的真实结果摘要，使用中文动宾短语
- 不超过约 72 个字符，不以句号结尾

| type | 含义 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `docs` | 仅文档变更 |
| `refactor` | 重构 |
| `test` | 新增或修改测试 |
| `chore` | 维护和辅助工具 |
| `ci` | CI 配置变更 |

Commit 正文按需解释原因，使用 `Refs #<Issue>`。Issue 只在 PR 正文中通过 `Closes #<Issue>` 自动关闭。

### PR 要求

- 正文必须包含 `Closes #<Issue>`（原则上只关闭一个 Issue）
- 包含：背景与目标、真实变更、明确未包含、影响分析、验证结果
- 禁止使用 `[Roadmap]`、`[Phase]` 等固定标题前缀
- main 禁止直接推送和 force-push，只通过 Squash Merge 合并

## 工作流程

### 标准交付流程（9 步）

1. 搜索现有 Issue 和 PR，避免重复
2. 创建或认领可验收的 Issue（写明范围、非目标、验收条件）
3. 确认前置 Issue 已合并，从最新 `origin/main` 创建唯一分支
4. 只实现该 Issue 的范围，同步测试和文档
5. 执行本地门禁，如实记录结果
6. 使用中文 Conventional Commit，形成本地待验收版本
7. **提交人工验收清单 → 停止 → 等待用户明确授权**
8. 用户授权后推送分支、创建 PR，等待 CI 和审查
9. PR 合并后删除分支，再开始下一项

### ⚠️ 人工验收门禁（强制）

- 本地实现完成后**不允许直接推送**
- 必须向用户提交验收清单：Issue 编号、分支、Commit、变更摘要、验证结果、验收步骤
- 只有用户明确说"可以推送"后，才能执行 `git push`
- 授权后发生实质修改 → 授权自动失效 → 必须重新验收
- 推送授权不包含合并授权，PR 仍需 CI + 审查 + 显式合并

### Issue 类型

Architecture / Epic / Implementation / Bug / Documentation

### 标签规则

- 每个 Issue 必须且只能有一个 `type:*`、一个 `priority:*`、至少一个 `area:*`
- 状态（写在正文中）：`ready` → `in-progress` → `acceptance` → `review`
- 标签真源为 `.github/labels.json`

## 架构要点

### 依赖方向（强制）

```
Apps/Adapters → Application → Domain
```

- Domain 只使用 Python 标准库和领域自身类型
- Domain 不导入 FastAPI、SQLAlchemy、LangGraph 等任何外部框架

### 领域上下文（7 个）

Identity & Preferences / Career Profile / Opportunity Intelligence / Interview Journey / Decision & Reporting / Knowledge & Evidence / Automation & Governance

详见 `docs/ARCHITECTURE.md §7`。

### 技术栈（M0/M1）

| 组件 | 选型 |
|------|------|
| 语言 | Python >=3.11 |
| 包管理 | `uv` |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL + pgvector |
| ORM | SQLAlchemy（异步） |
| 异步任务 | Celery + Redis（M4 引入） |
| 对象存储 | MinIO/S3（开发可用文件系统替代） |
| Agent 编排 | LangGraph Adapter |
| 模型网关 | Provider-neutral Model Gateway |
| 测试 | pytest |
| 代码质量 | ruff（lint + format）、pyright/mypy（type check） |

### 架构形态

- **模块化单体**：独立 API/Worker 进程，共享领域模型
- 不提前引入微服务、Kubernetes、服务网格
- 向量索引先使用 pgvector，达到触发条件后再评估 Milvus

### 关键架构原则

- **业务事实优先**：PostgreSQL 是事实源；缓存、向量索引、Agent State 不能成为第二事实源
- **Evidence First**：关键结论必须引用可定位 Evidence
- **模型输出不可信**：必须经过 Schema、归属、版本和策略校验
- **Agent 只做编排**：不直接访问 ORM、数据库或外部 SDK
- **可替换基础设施**：Domain 和 Application 不依赖具体框架或 SDK

### 数据所有权简表

| 数据 | 权威存储 | 性质 |
|------|---------|------|
| 用户、画像、岗位、面试、报告 | PostgreSQL | 业务事实 |
| Run、Approval、Audit | PostgreSQL | 治理事实（追加式） |
| 原始简历、附件 | Object Storage | 不可变对象 |
| Chunk、Embedding | pgvector（可重建） | 派生数据 |
| 缓存、锁、限流 | Redis | 临时状态（有 TTL） |

### 测试策略（6 层）

Unit → Architecture → Contract → Integration → E2E → Dynamic

详见 `docs/ARCHITECTURE.md §17`。

### 安全注意事项

- 身份来自认证上下文，不信任请求正文中的 `user_id`
- 日志不记录简历正文、面试回答、Token、Cookie、完整 Prompt
- URL Fetch 必须限制协议、域名、重定向、大小和超时（防 SSRF）
- Tool 参数只来自受控 Schema，不从网页文本动态生成动作

## 实施路线

```
M0: 工程基础与 CI 门禁（详见 docs/M0_PLAN.md、docs/ROADMAP.md）
M1: Identity + 岗位快照纵向切片
M2: 简历管理 + RAG 基础
M3: 最小化 Demo（Gradio 可演示）
M4: 可选中间件与生产准备（Redis/Celery）
M5+: 专项 Agent + 服务拆分评估
```
