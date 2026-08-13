<p align="center">
<pre>
███╗   ██╗ ██████╗ ██████╗  █████╗
████╗  ██║██╔═══██╗██╔══██╗██╔══██╗
██╔██╗ ██║██║   ██║██████╔╝███████║
██║╚██╗██║██║   ██║██╔══██╗██╔══██║
██║ ╚████║╚██████╔╝██║  ██║██║  ██║
╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
</pre>
</p>

<p align="center"><strong>Navigate</strong> · <strong>Observe</strong> · <strong>Review</strong> · <strong>Agent</strong></p>

<p align="center">面向软件工程校招应届生的可审计求职决策系统</p>

<p align="center">
  <img src="https://img.shields.io/badge/NORA-0d1117?style=flat-square&labelColor=0d1117&color=22d3ee" alt="NORA">
  <img src="https://img.shields.io/badge/License-Apache%202.0-0d1117?style=flat-square&labelColor=0d1117&color=22d3ee" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/Python-3.11-0d1117?style=flat-square&labelColor=0d1117&logo=python&logoColor=22d3ee&color=22d3ee" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-0d1117?style=flat-square&labelColor=0d1117&logo=fastapi&logoColor=22d3ee&color=22d3ee" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue%203-0d1117?style=flat-square&labelColor=0d1117&logo=vuedotjs&logoColor=22d3ee&color=22d3ee" alt="Vue 3">
  <img src="https://img.shields.io/badge/PostgreSQL%2016-0d1117?style=flat-square&labelColor=0d1117&logo=postgresql&logoColor=22d3ee&color=22d3ee" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/Docker-0d1117?style=flat-square&labelColor=0d1117&logo=docker&logoColor=22d3ee&color=22d3ee" alt="Docker">
  <img src="https://img.shields.io/badge/Status-M0~M3%20done%20%7C%20M4-22d3ee?style=flat-square&labelColor=0d1117&color=4ade80" alt="M0–M3 已完成，M4 进行中">
</p>

---

## 系统定位

Nora 将求职中高度分散的信息——岗位 JD、公司公开资料、个人主档与简历、历史复盘——组织为可追溯、版本化的 **Decision Report**，回答「投不投、准备什么、何时出发、如何复盘」。

区别于把简历全文塞进向量库的检索式工具，Nora 的核心是一条由用户确认的证据链：

```text
CandidateProfile → OpportunityCase → DecisionReport → ApplicationDecision
```

每个结论都可定位到**来源**、**规则**或**模型推断**，而非不可解释的黑盒输出。产品愿景与能力边界见 [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md)。

## 核心设计

- **Evidence First** —— 关键结论必须引用可定位的证据；无证据内容只能保持候选、推断或未知状态。
- **确定性优先，模型后置增强** —— 规则引擎先行；RAG / LLM 仅在受控 Evidence Pack 上增强表达与推理。
- **模型输出不可信** —— 所有 LLM / Embedding / Reranker 输出必经 Schema 与策略校验。
- **业务事实只在 PostgreSQL** —— 缓存、向量索引与 Agent State 均为可重建的派生状态，不能成为第二事实源。
- **外部写默认关闭** —— 任何外部副作用需审批、幂等与审计。

## 技术架构

当前可运行的边界（Redis 仍为条件组件；MinIO 已进入 Artifact/Source 路径）：

```text
   [ Vue 3 工作台 :5173 ]
        │  /api 代理
        ▼
   [ FastAPI API :8000 ]
        │
        ├──────────────►  PostgreSQL 16   ← 业务事实唯一
        │
        ├──────────────►  私有 MinIO      ← Artifact/Source 原始字节
        └─ ─ ─ ─ ─ ─ ─►  Redis           ← 条件组件 · 未接入业务路径
```

| 层 | 技术选型 |
|------|----------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy（异步） · Alembic |
| 前端 | Vue 3 · Vite · TypeScript · Pinia |
| 数据 | PostgreSQL 16 · pgvector（M5 规划，模型维度确认后引入） |
| 工程 | Docker Compose · ruff · mypy · pytest · GitHub Actions |
| 治理 | 一 PR 一分支 · Issue 可选 · Codex 自动审核门禁 |

分层遵循 `Apps/Adapters → Application → Domain`，Domain 不依赖任何外部框架。模块边界、数据所有权与依赖方向的权威定义见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 里程碑

| 里程碑 | 交付物 | 状态 |
|--------|--------|------|
| **M0** | 工程骨架 · CI 门禁 · Docker Compose | ![已完成](https://img.shields.io/badge/-done-4ade80?style=flat-square&labelColor=0d1117) |
| **M1** | 本地认证 · 岗位快照 · 幂等 · 审计 | ![已完成](https://img.shields.io/badge/-done-4ade80?style=flat-square&labelColor=0d1117) |
| **M2** | 可确认的岗位要求 · OCR/链接输入 · 分析就绪 E2E | ![已完成](https://img.shields.io/badge/-done-4ade80?style=flat-square&labelColor=0d1117) |
| **M3** | 确定性决策报告 · apply/skip（无模型密钥可运行） | ![已完成](https://img.shields.io/badge/-done-4ade80?style=flat-square&labelColor=0d1117) |
| **M4** | 定制材料 · 手工投递/面试记录 · 可部署 Beta | ![进行中](https://img.shields.io/badge/-building-22d3ee?style=flat-square&labelColor=0d1117) |
| **M5** | Evidence · 检索 · 可选 AI 与指标触发的规模化 | ![规划中](https://img.shields.io/badge/-planned-64748b?style=flat-square&labelColor=0d1117) |

> 规划状态以 GitHub Milestone 与 [`docs/ROADMAP.md`](docs/ROADMAP.md) 为准；当前可运行能力、代码路径与合并证据只见 [`docs/current-capabilities.toml`](docs/current-capabilities.toml)，不要从路线图反推已交付能力。

## 快速开始

前置：Windows + WSL2 Ubuntu + Docker Desktop（WSL2 backend），宿主无需安装 Python 或 uv。

```bash
cp backend/.env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
```

验证：

```bash
curl http://localhost:8000/health   # {"status":"healthy"}
# 前端工作台：http://localhost:5173
```

数据保存在 Docker 命名卷中；`docker compose down -v` 会清空。完整的环境、测试、迁移与排障指南见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。

## 协作流程

1. 阅读 [架构文档](docs/ARCHITECTURE.md) 与 [工作流](docs/WORKFLOW.md)
2. 确定一个范围明确、可独立验收的交付项，按需创建或关联 [Issue](https://github.com/dev-cai/Nora/issues)
3. 从最新 `main` 创建 `nora/<type>-<subject>` 分支
4. 实现并测试，通过本地门禁
5. 推送 → 创建 PR → Codex 自动审核 → CI → Squash Merge

## 文档

### 按角色快速定位

| 角色 | 必读 |
| :--- | :--- |
| 产品 / 用户 | [`PRODUCT_VISION.md`](docs/PRODUCT_VISION.md) · [`BUSINESS_FLOW.md`](docs/BUSINESS_FLOW.md) · [`USER_EXPERIENCE.md`](docs/USER_EXPERIENCE.md) |
| 后端开发 | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`DEVELOPMENT.md`](docs/DEVELOPMENT.md) · [`WORKFLOW.md`](docs/WORKFLOW.md) · [`ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md) |
| 前端开发 | [`FRONTEND.md`](docs/FRONTEND.md) · [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`DEVELOPMENT.md`](docs/DEVELOPMENT.md) |
| 规划与治理 | [`ROADMAP.md`](docs/ROADMAP.md) · [`MILESTONE_PLAN.md`](docs/MILESTONE_PLAN.md) · [`ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md) · [`WORKFLOW.md`](docs/WORKFLOW.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| 安全 | [`SECURITY.md`](SECURITY.md) · [`JD_INPUT_SECURITY.md`](docs/JD_INPUT_SECURITY.md) |

### 完整文档索引

| 文档 | 说明 |
|------|------|
| [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md) | 产品愿景、用户旅程与能力状态 |
| [`docs/BUSINESS_FLOW.md`](docs/BUSINESS_FLOW.md) | 已确认业务流程与技术决策基线 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 架构边界、数据所有权与依赖方向 |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 里程碑范围与验收条件 |
| [`docs/MILESTONE_PLAN.md`](docs/MILESTONE_PLAN.md) | 里程碑原子交付执行计划 |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 环境、测试、迁移与排障 |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | 前端技术与 HTTP 集成契约 |
| [`docs/USER_EXPERIENCE.md`](docs/USER_EXPERIENCE.md) | 用户体验场景与交互目标 |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | 领域术语索引 |
| [`docs/ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md) | Issue 类型、标签、状态与关系 |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | 开发交付工作流 |
| [`docs/JD_INPUT_SECURITY.md`](docs/JD_INPUT_SECURITY.md) | JD 输入安全边界与 Adapter 审查清单 |
| [`docs/docs-contract.toml`](docs/docs-contract.toml) | 文档分类、事实所有权与代码路径影响规则 |
| [`docs/current-capabilities.toml`](docs/current-capabilities.toml) | 当前已交付能力、代码路径与 PR 证据 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献规则与协作约定 |

## 许可证

[Apache License 2.0](LICENSE) · 安全问题请按 [`SECURITY.md`](SECURITY.md) 通过私密渠道报告。
