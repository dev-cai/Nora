# Nora 术语表

> 按类别组织。括号中的 **En** 为英文对应词，便于代码和配置中统一使用。

---

## 项目与角色

### Nora
**Navigate · Observe · Review · Agent** 的缩写。一个面向求职决策的可审计多智能体平台。

### Agent（智能体）
由 LangGraph 编排的专业任务执行单元，如投递决策 Agent、面试准备 Agent。Agent **只做编排**，不直接访问 ORM、数据库或外部 SDK，也不拥有业务事实。

### 求职用户
Nora 系统的最终使用者。通过 Gradio/Web 客户端与系统交互，拥有独立的身份、偏好和数据隔离空间。

---

## 架构概念

### 模块化单体（Modular Monolith）
Nora 初期的架构形态。一个代码仓库、一个部署单元，但内部按领域上下文划分为独立模块，模块间依赖方向严格受控。不提前引入微服务分布式复杂度。

### 依赖方向（Dependency Direction）
```
Apps/Adapters → Application → Domain
```
内层（Domain）不导入外层（FastAPI、SQLAlchemy、LangGraph、SDK 等）的任何类型。违反该方向的代码在架构测试中被阻断。

### Domain（领域层）
最内层，只包含业务规则、状态机和 Policy，仅依赖 Python 标准库。不导入 Web 框架、ORM、Agent SDK 或任何外部库。

### Application（应用层）
编排层，负责接收外部的 Command/Query，调用 Domain 规则，通过 Port 委托 Infrastructure 执行。不依赖具体 Adapter 实现。

### Port（端口）
Application 层定义的接口抽象，如 `Repository[T]`、`ModelGateway`、`ObjectStorage`。Infrastructure 层通过实现 Port 来接入具体技术。

### Infrastructure Adapter（基础设施适配器）
Port 的具体实现，如 `SqlAlchemyRepository`、`S3ObjectStorage`、`CeleryTaskQueue`。可以被替换而不影响内层。

### Application Core（应用核心）
Domain + Application + Port 的统称。不依赖任何外部框架、数据库驱动或 SDK。

---

## 领域上下文（Domain Context）

业务能力的逻辑分区。Nora 包含 7 个 Context：

| Context | 职责 |
|---------|------|
| **Identity & Preferences** | 用户身份、租户映射、时区、语言、隐私与出行偏好 |
| **Career Profile** | 简历版本、已确认经历、技能和能力证据 |
| **Opportunity Intelligence** | 公司与岗位快照、风险证据、人岗分析 |
| **Interview Journey** | 面试计划、准备材料、出行方案和复盘 |
| **Decision & Reporting** | 汇总经校验的分析结果，生成版本化决策报告 |
| **Knowledge & Evidence** | 来源快照、文档版本、Chunk、检索索引 |
| **Automation & Governance** | Run、Task、Approval、审计和幂等 |

---

## 进程与运行时

### API Process
Nora 的 HTTP 服务进程。负责认证、输入校验、Use Case 编排和稳定错误映射。不执行长时间模型调用或浏览器动作。

### Worker Process
异步任务执行进程。负责数据导入、Embedding、检索构建、分析生成等后台任务。通过 Celery 接收任务消息。

### Agent Runtime
LangGraph 管理的多智能体运行环境。初期作为 Worker 内的逻辑模块运行。管理运行图、暂停、恢复和 Checkpoint，不拥有业务事实。

### Browser/Connector Runtime（延后引入）
独立受限进程，负责浏览器自动化或外部连接器。只读采集与外部写动作分离；遇到验证码或不确定状态立即转人工。

### Model Gateway（模型网关）
Provider 无关的模型访问层。负责请求路由、Prompt 版本管理、成本预算和响应校验。DeepSeek 等 Provider 由配置选择。

---

## RAG 与 Evidence

### Source Snapshot（来源快照）
外部来源（网页、文档、API）在某一时刻的不可变快照。包含来源 URL/标识、获取时间、许可说明和内容摘要。所有外部数据必须先形成 Source Snapshot 才能进入后续分析。

### Chunk（文档切片）
对 Source Snapshot 进行解析和分片后得到的版本化文本片段。每个 Chunk 引用其来源的 Artifact 版本。

### Embedding
将 Chunk 转化为向量表示的过程。M2 使用 BGE-M3 模型，向量存储于 pgvector。

### pgvector
PostgreSQL 的向量检索扩展。M0/M1 作为向量索引的主要存储，是可重建的派生数据。

### Hybrid Retrieve（混合检索）
同时使用向量相似度（语义）和关键词匹配（BM25 等）进行检索，再融合结果。比单一检索方式更全面。

### Reranker（重排器）
对检索结果进行精排的模型。接收 Hybrid Retrieve 的候选列表，重新计算相关性分数，提升顶部结果质量。

### Evidence Pack（证据包）
不可变的检索结果包。包含检索到的 Chunk、来源版本、生成器版本、检索参数。模型只能基于 Evidence Pack 中的内容作答，不得包装外部知识作为来源事实。

### Evidence（证据）
Evidence Pack 中的最小单元，包含：
- `source_id` 与来源/Artifact 版本
- 可定位的 locator（页码、段落、字段路径）
- 内容摘要与采集/生成时间
- 来源类型、可信级别和许可说明
- 生成器、Embedding、Reranker、检索参数的版本

### Versioned Decision Report（版本化决策报告）
最终输出给用户的求职决策报告。每个版本包含所引用的所有 Evidence 版本，确保结论可追溯。

---

## 外部写与审批

### ProposedAction（提议动作）
外部写操作前的不可变快照。包含用户、Run、Tool、目标、预览、内容摘要、风险等级、版本和失效时间。修改内容必须生成新的 ProposedAction，不能复用旧批准。

### Approval（审批）
用户对 ProposedAction 的审批结果。状态机：`Proposed → Approved/Rejected/Expired → Executing → Succeeded/Failed/Cancelled`。

### 幂等键（Idempotency Key）
由服务端根据用户、动作、目标、内容摘要和版本生成的唯一键。同键同内容重放首次结果；同键不同内容返回冲突。

### 外部写默认关闭
所有外部副作用（投递、发送消息、修改资料等）默认不允许执行，必须经过审批、幂等和审计。

---

## 治理与工作流

### Issue（问题/任务）
Nora 所有变更的驱动单元。共 5 种类型：

| 类型 | 用途 |
|------|------|
| **Architecture** | 修改系统边界、数据所有权、依赖方向或技术决策 |
| **Epic** | 包含多个原子 Task 的父级目标，不直接承载实现 |
| **Implementation** | 交付进入真实调用路径、可运行且可测试的纵向切片 |
| **Bug** | 修复已存在且可复现的错误行为 |
| **Documentation** | 只修改文档或协作规范 |

### 门禁（Gate）
流程中的强制检查点，未通过则禁止进入下一步。Nora 定义了两道核心门禁：

**人工验收门禁**：本地实现完成后，必须向用户提交验收清单，**用户明确授权后**才能推送。授权只对当前待验收版本有效，后续修改使授权自动失效。

### Milestone（里程碑）
一组 Issue 的集合，代表一个可交付的阶段。Architecture、Epic 和 Implementation 必须归入 Milestone。Nora 的里程碑规划：M0 → M1 → M2 → M3 → M4 → M5+。

### 状态（Status）
Issue 的生命周期状态，记录在 Issue 正文中（不使用 `status:*` 标签）：
- `ready` — 可开始实施
- `blocked` — 等待前置依赖
- `in-progress` — 已创建分支，正在实施
- `acceptance` — 本地待验收版本完成，等待用户确认
- `review` — 已推送并创建 PR，等待 CI 和审查

### nora/ 分支
所有工作分支统一前缀。格式：`nora/<type>-<subject>`，如 `nora/feat-job-posting-api`。禁止使用 `codex/`、`agent/`、`roadmap`、`phase` 等前缀。

### Conventional Commit（约定式提交）
Nora 使用中文化版本：`<type>(<scope>): <中文 subject>`。scope 可选。类型包括 feat、fix、docs、refactor、test、chore、ci 等。

### Squash Merge
Nora 推荐的 GitHub 合并策略。将一个 PR 的所有 Commit 压缩为一条 Commit 合并到 main，以 PR 标题作为 Commit 标题。

### Skill（技能）
位于 `.codex/skills/` 下的可执行工作流定义，指导 LLM Agent 完成特定任务（如创建 Issue、交付 PR）。

### CODEOWNERS
GitHub 的代码所有者机制。Nora 的 CODEOWNERS 指向 `@dev-cai`，所有 PR 必须经其审查。

---

## 基础设施

| 术语 | 说明 |
|------|------|
| **FastAPI** | Python Web 框架，用于构建 API Process |
| **SQLAlchemy** | Python ORM，使用异步模式访问 PostgreSQL |
| **Alembic** | 数据库 Schema 迁移管理工具 |
| **Celery** | 分布式任务队列，用于 Worker Process 的异步任务（M4 引入） |
| **Redis** | 缓存、任务队列 Broker、锁和限流 |
| **MinIO / S3** | 对象存储，用于保存原始简历、附件等不可变文件（开发可用文件系统替代） |
| **pgvector** | PostgreSQL 向量检索扩展，M0/M1 的向量存储方案 |
| **Milvus / Zilliz** | 专用向量数据库，作为 pgvector 的演进选项（达到触发条件后评估） |
| **LangGraph** | LLM Agent 编排框架，用于构建和管理多智能体运行图 |
| **BGE-M3** | 嵌入模型，用于将 Chunk 向量化 |
| **pytest** | Python 测试框架 |
| **ruff** | Python 代码检查和格式化工具 |
| **uv** | Python 包管理器，替代 pip/poetry |

---

## 测试

| 术语 | 说明 |
|------|------|
| **Unit Test** | 验证领域规则、状态机、Policy、纯函数。无外部依赖。 |
| **Architecture Test** | 验证依赖方向、禁止导入、模块所有权。无外部依赖。 |
| **Contract Test** | 验证 Port、API、DTO、Adapter 契约。使用 Fake 或 Recorded 数据。 |
| **Integration Test** | 验证 PostgreSQL、pgvector、Redis、对象存储等外部服务的协作。需专用本地/CI 服务。 |
| **E2E Test** | 验证用户主路径、权限、异步恢复和报告。需隔离环境。 |
| **Dynamic Test** | 使用真实模型、地图、天气等外部服务。需要显式凭据与人工授权，不进入普通 CI。 |

---

## 标签体系

Nora 使用三层标签分类（真源为 `.github/labels.json`）：

| 类别 | 标签 | 说明 |
|------|------|------|
| **type** | `type:architecture`、`type:epic`、`type:task`、`type:bug`、`type:docs` | Issue 类型，每 Issue 必选且唯一 |
| **priority** | `priority:p0` ~ `priority:p3` | 优先级，每 Issue 必选且唯一 |
| **area** | `area:architecture`、`area:backend`、`area:frontend`、`area:agent`、`area:rag`、`area:data`、`area:infra`、`area:security`、`area:docs` | 所属领域，每 Issue 至少选一个 |

---

## 延后事项

以下术语在初版架构中明确延后，不纳入当前讨论：

- 微服务 / Kubernetes / 服务网格
- 多租户企业权限、计费、生产级高可用
- 自动投递 / 自动发送招聘消息 / 无人值守浏览器写操作
- 模型私有 chain-of-thought 存储
- 飞书 Base 作为业务事实源
