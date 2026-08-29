# Nora 产品愿景

本文定义 Nora 的产品目标、用户旅程和能力边界。它描述“为什么做、为谁做、最终希望交付什么”，不把路线图中的计划能力
描述为已实现事实。架构约束以 [`ARCHITECTURE.md`](ARCHITECTURE.md) 为准，交付阶段以
[`ROADMAP.md`](ROADMAP.md) 和 GitHub Milestone 为准。

## 1. N.O.R.A.

> **Nora — Navigate · Observe · Review · Agent**
>
> 面向软件工程应届生的 Agentic RAG 求职决策智能体

| 字母 | 单词 | 中文 | 产品含义 |
| :--- | :--- | :--- | :--- |
| **N** | Navigate | 导航 | 规划面试行程、时间、交通、天气和到场准备 |
| **O** | Observe | 洞察 | 理解公司、岗位、个人经历与风险 Evidence |
| **R** | Review | 复盘 | 复盘面试表现，把反馈沉淀为可确认的长期知识 |
| **A** | Agent | 智能体 | 在受控边界内编排检索、规则、模型与 Tool |

N.O.R.A. 是产品叙事，不是代码模块或固定 Agent 数量。领域上下文、进程和依赖方向由架构文档定义。

## 2. 产品问题

软件工程应届求职者的信息分散在技术岗位 JD、公司公开信息、个人简历与项目、在线评测（OA）、算法与系统设计题库、面试邀请、交通天气和历次复盘中。用户通常难以同时判断：

- 岗位是否值得投入时间，技能缺口是什么；
- 简历技术栈与岗位 JD 技能项的真实差距；
- 技术面试（算法、系统设计、CS 基础）该准备什么；
- 公司信息和风险结论是否有可追溯依据；
- 面试前应该准备什么、何时出发；
- 一次技术面试如何转化为下一次可复用的经验。

Nora 将这些输入组织为版本化的 **Decision Report**。报告必须说明证据来源、规则结果、模型推断、不确定性和建议动作，
而不是只给出不可解释的结论。

## 3. 目标用户旅程

初版目标用户是**软件工程专业应届生（以校招为主）**，产品围绕校招流程：在线评测（OA）、技术面
（算法 / 系统设计 / CS 基础）、HR 面与 Offer 决策。社招、管理岗或跨行业求职不是初版重点。

> 操作流程（JD 输入 → 适配分析 → 投不投 → 投递产物 → 面试出行）的权威定义见
> [`BUSINESS_FLOW.md`](BUSINESS_FLOW.md) §2；本章描述产品级用户旅程，不重述操作细节。

岗位信息优先从文本、截图或受控链接进入 JD 专用固定 Agent，经过正文清洗、结构化识别和校验后生成待确认的结构化候选；AI 不可用时，用户才可用完整手工字段作为最后兜底。
两种入口都以用户确认后的岗位事实作为后续分析输入。

1. 用户录入或导入技术岗位信息，并选择一份已确认的简历版本。
2. Nora 建立岗位、公司、简历和来源 Evidence 的版本化快照，并把 JD 技能项映射到简历技术栈。
3. 规则先形成可重复的分析基础；在 Evidence Pack 尚未交付前，AI JobFitAnalysis 只基于 DecisionCase 固定输入和字段级引用增强语义判断。
4. 用户查看包含“事实、规则结果、模型推断、建议、未知项”的 Decision Report，决定是否投递以及如何准备技术面试。
5. 收到面试邀请后，Nora 针对算法题、系统设计题和项目深挖生成准备清单、练习和出行方案。
6. 面试结束后，用户确认复盘内容；系统更新能力证据和长期记忆候选，供后续决策检索。

自动投递、自动发送招聘消息和无人值守浏览器写操作不属于初版目标。未来任何外部写都必须经过审批、幂等和审计。

### 3.1 个人定制闭环

Nora 的核心不是把简历全文塞进向量库，而是维护一份由用户确认的个人主档，并围绕每个机会建立可追溯的决策记录：

```text
CandidateProfile
  -> OpportunityCase
  -> DecisionReport
  -> ApplicationDecision
      -> skip -> OutcomeRecord -> MemoryCandidate
      -> apply -> ResumeVariant + MessageDraft
               -> ApplicationRecord
               -> InterviewCase -> InterviewReview
```

`CandidateProfile` 包含基本信息、项目、经历、教育、技能、求职偏好和确认状态；初版优先维护技术栈、项目经历和 GitHub 等 SWE 求职资产。`ResumeVersion` 是用户确认的简历事实版本，`ResumeVariant` 是针对某个岗位生成的输出版本；二者都不能替代主档。

`ApplicationDecision` 至少记录 `undecided`、`apply`、`skip`、决策原因、时间、关联报告版本和使用的简历版本。用户决定不投递时，原因和报告仍可用于后续复盘；用户决定投递时，Nora 只生成简历与打招呼草稿，不自动执行外部投递。

初版 `MessageDraft` 只输出一段可编辑纯文本，默认专业风格，可选择简洁风格或用户提供内推上下文的风格；用户手动复制发送。新岗位报告可以展示最多 3 条同用户、同岗位族且至少共享 2 个技术栈标签的历史 `skip` 记录，但不自动改变当前建议。

## 4. 产品能力目录

以下五类角色是稳定的产品能力分类，不承诺“一类角色等于一个 LangGraph 节点、进程或服务”。只有出现真实的分支、
暂停/恢复和多 Tool 编排需求时，才通过独立 Architecture Issue 评估 Agent Runtime。

| 能力角色 | 用户触发 | 目标输出 | 关键输入 |
| :--- | :--- | :--- | :--- |
| 投递决策 Agent | 录入职位链接、截图或 JD | 公司与岗位洞察、JD 技能映射、匹配差距、投递建议、简历修改建议 | 岗位快照、公司 Evidence、简历版本 |
| 面试准备 Agent | 收到面试邀请 | 算法题与系统设计题、CS 基础问答、模拟反馈和薄弱点 | JD、简历、技术题库 Evidence、历史复盘 |
| 面试出行 Agent | 确定时间与地点 | 多模式路线、出门时间、天气建议和物品清单 | 地点、时间、交通天气、用户偏好 |
| 面试复盘 Agent | 面试结束 | 问题与回答复盘、能力证据候选、改进计划 | 用户记录、面试计划、历史能力画像 |
| 报告与记忆 Agent | 一次分析或复盘完成 | 版本化 Decision Report、引用链和待确认记忆候选 | 各能力结果、Evidence Pack、用户确认 |

### 能力细节与证据要求

| 能力角色 | 计划能力 | 用户收益 | Evidence / RAG 要求 |
| :--- | :--- | :--- | :--- |
| 投递决策 | 公司公开信息与风险摘要、人岗匹配、差距清单、简历 bullet 建议、投递结论 | 判断是否值得投入以及应如何定制简历 | 公司、JD、简历按来源和版本隔离检索；风险与匹配结论必须引用原文，不能把匿名评价直接升级为事实 |
| 面试准备 | 算法题、系统设计题、CS 基础问答、模拟反馈与薄弱点诊断 | 围绕岗位与个人技术栈定向准备 | 技术题库按岗位、公司类型和技术栈检索；诊断必须关联具体题目、用户回答和可解释评分依据 |
| 面试出行 | 公交/地铁/打车对比、出门时间、天气建议、物品清单 | 降低迟到和遗漏材料风险 | 实时交通天气与历史偏好分开标注来源和时效；过期或不可用时明确降级，不伪造实时结果 |
| 面试复盘 | 问题记录、回答分析、改进范例、能力证据候选 | 将单次面试转化为后续准备材料 | 保留用户原始记录的版本引用；模型总结先作为候选，经确认后再影响长期画像 |
| 报告与记忆 | 报告汇总、投递状态、历史复盘检索、简历版本演进和风险提醒 | 获得跨岗位、跨面试的连续决策支持 | 报告引用不可变 Evidence Pack；记忆检索按用户、权限、版本和保留策略过滤 |

## 5. Decision Report 契约方向

初版报告至少区分：

- **事实（Fact）**：来自用户确认数据或可定位来源快照；
- **规则结果（Rule Result）**：由版本化确定性规则计算；
- **模型推断（Inference）**：由模型基于 Evidence Pack 生成，不能升级为事实；
- **建议（Recommendation）**：说明理由、风险和可选动作；
- **未知（Unknown）**：证据缺失、冲突、过期或当前不可验证；
- **引用（Citation）**：定位到来源版本、片段或字段路径。

具体 Schema、版本兼容性和渲染形式由 M3 的独立契约与 Task Issue 定义。

## 6. 长期记忆原则

长期记忆用于减少重复劳动，不是未经确认的自动画像：

- 投递记录、面试状态和报告版本属于 PostgreSQL 中的业务事实；
- 简历、面试回答和外部文档必须版本化，并遵守后续数据保留与删除策略；
- 模型生成的强项、弱项和公司标签先进入 `MemoryCandidate`，经用户或规则确认后才能成为长期事实；
- 向量索引、缓存和 Agent State 均为可重建派生状态，不能成为第二事实源；
- 新决策优先检索同岗位、同行业和相似能力证据，但必须展示引用与时效。

## 7. 能力状态

| 状态 | 含义 | 当前范围 |
| :--- | :--- | :--- |
| **Current** | 已实现并有验证证据 | 仓库治理、M0/M1、岗位/主档/简历、结构化岗位要求（JobRequirementSnapshot）、受控链接抓取与截图 OCR 输入、Vue 工作台、JD 输入契约，以及 M2 输入、M3 确定性决策、M5.3 固定输入 AI 人岗语义分析、M5 最小 Source→Chunk→Embedding→exact retrieval→grounded/unknown RAG 链路、合成评测集驱动的 RAG Vector/lexical 基线与受控 Hybrid 离线评测（当前未达到上线门槛）、版本化面试准备、面试复盘与可确认 MemoryCandidate、单 Agent/单 Graph LangGraph 工具编排（含显式 Decision Analysis 入口与真实 JobFit COMPUTE）、M4 投递闭环；公司情报、材料生成、手工投递/面试记录、恢复与隔离已有完整浏览器门禁，M5 Agentic RAG 闭环已由隔离 Compose 浏览器门禁验证，并已交付 localhost-only Host Proxy 接入契约、fail-closed 八阶段 Beta 发布/回滚控制面和结构化 ModelPort 调用边界；JD 与 PDF 主档导入均支持一次整体确认，逐项范围、代码路径和证据只见能力台账 |
| **Planned** | 已进入 Milestone/Issue，但必须经过独立实现与验收 | 真实 Beta Environment/Runner 供应与首次公网发布、M5 Evidence/RAG 和其他 AI 增强 |
| **Evolution** | 只有满足触发条件并通过 Architecture Issue 后才可引入 | 外部平台写入、深度面试复盘、实时出行、Milvus 和服务拆分 |

Current 状态以默认分支、已合并 PR 和能力台账为证据；Planned 状态以 GitHub Milestone/Issue 为准。逐项交付证据与限制
只维护在 [`current-capabilities.toml`](current-capabilities.toml)。本文中的产品示例不能替代实现、测试或发布证明。

## 8. 技术与 Provider 边界

- M5 的初期向量能力候选是 PostgreSQL + pgvector；D-007 已冻结首个 Embedding 为阿里云百炼北京地域的
  `qwen3.7-text-embedding` dense 1024 维，当前 HTTP Adapter 与 identity 隔离已就绪，但真实质量评测未准入前不切换线上。
- BGE-M3 是已被 D-007 替代的历史候选；Reranker 只有在固定评测集证明收益后才引入。当前冻结的合成 RAG 评测已完成 Hybrid 指标计算，但未达到上线门槛，暂不引入在线 Hybrid 或 Reranker。
- 模型通过最小 Provider-neutral `ModelPort` 访问；当前 Chat 唯一固定为 DeepSeek `deepseek-v4-flash`，Embedding 仍按
  [`ARCHITECTURE.md`](ARCHITECTURE.md) 的 D-007 使用既定契约，后续 Provider、模型或地域替换必须重新经过 Architecture Review。
- 地图、天气、企业和公开司法数据只通过受控 Adapter 接入；Provider、许可范围、请求频率、数据保留和失败策略必须由对应
  Architecture/Task Issue 验收。
- 当前 Agent Runtime 仅支持 API 进程内受控 async orchestration adapter 的单 Agent/单 Graph、固定 Tool Registry、Approval 和可清理 Checkpoint；不代表 Worker、队列、多 Agent、Supervisor、MCP 或独立服务已交付。M3 仍使用确定性规则和版本化报告，不依赖 RAG、LLM 或多 Agent。
- Redis/Celery 在 M5 仅按性能和故障隔离指标评估，不拥有业务事实，评估结论可以是不引入。

## 9. 文档真源

| 主题 | 权威真源 | 允许的摘要 | 同步规则 |
| :--- | :--- | :--- | :--- |
| 产品目标、用户旅程、能力目录 | 本文 | `README.md` | 摘要只链接本文件，不复制会演化的完整能力契约 |
| 当前已交付能力、代码路径与 PR 证据 | [`current-capabilities.toml`](current-capabilities.toml) | `README.md`、产品、架构、前端和开发文档 | 台账记录用户能力与可复验运行/恢复基线；未取得的 provider、成本或演练证据不得写成 Current，Planned 进度留在 GitHub Milestone/Issue |
| 文档分类、事实所有权、允许摘要和路径影响 | [`docs-contract.toml`](docs-contract.toml) | 本文、[`WORKFLOW.md`](WORKFLOW.md)、Agent 指南 | 代码变更按契约更新规范文档或在 PR 中给出具体豁免理由，CI 负责阻断缺失声明 |
| 已确认业务流程、技术决策基线、缺口分析 | [`BUSINESS_FLOW.md`](BUSINESS_FLOW.md) | `PRODUCT_VISION.md`、`USER_EXPERIENCE.md`、`ROADMAP.md` | 操作流程与决策基线以本文为真源，其他文档只链接不重述 |
| 用户体验场景与交互目标 | [`USER_EXPERIENCE.md`](USER_EXPERIENCE.md) | 产品与前端文档 | 只描述设计目标，不证明功能已交付 |
| 架构、模块边界、数据所有权、依赖方向 | [`ARCHITECTURE.md`](ARCHITECTURE.md) 与已合并 Architecture Issue | `README.md`、AI 指南 | 边界变更必须先审查 Architecture Issue，摘要不得另立规则 |
| 前端技术与 HTTP 集成契约 | [`FRONTEND.md`](FRONTEND.md) | 架构与路线图 | 当前/目标目录和 API 必须明确区分，不伪造 Planned 能力 |
| 里程碑结果、边界与退出目标 | [`ROADMAP.md`](ROADMAP.md) | `README.md` | 路线图不记录任务状态、依赖或执行顺序 |
| 进行中工作、Issue 状态、依赖与执行顺序 | GitHub Milestones/Issues | `ROADMAP.md`、`README.md` | 长期文档只链接，不复制在线规划数据 |
| 历史 M0 Issue 映射 | GitHub Issue #9–#15 与 M0 [Milestone](https://github.com/dev-cai/Nora/milestone/1) | 路线图 | 保留历史交付路径，不为目标结构改写已发生事实 |
| 本地环境、配置、迁移和测试命令 | [`DEVELOPMENT.md`](DEVELOPMENT.md) | `README.md`、[`WORKFLOW.md`](WORKFLOW.md) | 命令只有在默认分支文件与容器中可执行后才能标为 Current |
| Issue 类型、标签、状态和关系 | [`ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md) | [`../CONTRIBUTING.md`](../CONTRIBUTING.md)、[`WORKFLOW.md`](WORKFLOW.md)、项目 Skills | 摘要必须与真源一致；自动化校验规则同步修改 |
| 分支、Commit、验收、PR、CI 和合并步骤 | [`WORKFLOW.md`](WORKFLOW.md) | [`../CONTRIBUTING.md`](../CONTRIBUTING.md)、`AGENTS.md`、项目 Skills | 工作流变更必须同步门禁与自动化，不在多个文件独立设计 |
| 安全报告与基础边界 | [`../SECURITY.md`](../SECURITY.md) | 贡献与架构文档 | 敏感问题不进入公开 Issue，摘要不包含利用细节 |
| 领域术语 | [`GLOSSARY.md`](GLOSSARY.md) | 产品、架构和业务文档 | 首次使用可解释，正式定义只维护一处 |
| 已实现行为 | 默认分支代码、迁移、公开契约和测试 | 所有文档 | 文档与实现冲突时通过 Issue 修正，不能静默选择或把计划写成已实现 |

摘要的职责是帮助目标读者导航，不是复制真源。状态表、目录契约、操作步骤和治理规则发生变化时，必须先修改对应真源，
再检查引用它的摘要；历史执行记录保留在 GitHub Issue、PR 和 Milestone 中，不建立 Markdown 平行台账。物理目录不是事实所有权边界：新增文档先在
`docs-contract.toml` 登记，再按逻辑分类放置，已有路径只有在具备兼容入口时才迁移。

## 10. 非目标

- 不以社招、管理岗或跨行业求职为主要场景（初版聚焦软件工程校招应届生）；
- 用 Agent 数量替代领域边界或把模型输出当作业务事实；
- 在没有合法来源、许可说明和时效信息时宣称公司风险结论；
- 保存模型私有 chain-of-thought；
- 在无 Benchmark 时同时维护 pgvector 与 Milvus；
- 在初版中实现自动投递、自动消息发送、生产级多租户、计费或高可用。
- 把个人资料、投递决定或生成 PDF 作为向量数据库的唯一事实源。
