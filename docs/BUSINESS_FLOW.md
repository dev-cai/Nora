# Nora 业务流程与缺口分析（决策基线）

> **文档定位**：本文是已确认业务流程与产品决策的基线真源，记录**已确认的业务流程**、**已确认的技术决策**、
> 与当前项目实现的**差距分析**以及调整方向。本文不独立定义技术实现边界；任何落地都必须遵守
> [`ARCHITECTURE.md`](ARCHITECTURE.md) 的变更规则和仓库交付门禁。
>
> 相关真源：[`PRODUCT_VISION.md`](PRODUCT_VISION.md)、[`ROADMAP.md`](ROADMAP.md)。建立基线：2026-08-02。

---

## 1. 目标用户与产品定位（已确认）

- 目标用户：**软件工程专业应届生，以校招为主**。
- 产品形态：**个人定制求职决策系统**（单人使用，非企业级多租户）。
- 定位：围绕校招流程（在线评测 OA -> 技术面 -> HR 面 -> Offer）提供可审计的决策与准备支持。
- 非目标：社招、管理岗、跨行业求职；生产级多租户、计费、高可用。

## 2. 已确认的业务流程

```text
第一步  建立并确认个人主档与不可变简历版本
第二步  输入 JD（文本 / 截图 / 链接）并确认结构化岗位要求
第三步  创建固定输入版本的 DecisionCase，生成确定性报告，用户选择 apply / skip
第四步  apply 后生成定制简历、PDF 和消息草稿；用户手工投递并记录结果与面试通知
第五步  在确定性闭环可独立运行后，以 Evidence、检索和可选模型增强报告
候选    外部平台写入、深度面试复盘、实时出行、长期记忆和 Agent Runtime 按触发条件立项
```

### 各阶段要点

| 阶段 | 关键动作 | 落库/产物 | 里程碑 |
| :--- | :--- | :--- | :--- |
| 输入基线 | 主档、简历、JD 原文和用户确认的岗位要求 | `CandidateProfile`、`ResumeVersion`、`JobPosting`、`JobRequirementSnapshot` | M2 |
| 确定性分析 | 固定输入版本，运行规则并记录投/不投 | `DecisionCase`、`DecisionReport`、`ApplicationDecision` | M3 |
| 投递闭环 | 生成材料，用户手工投递并记录最小面试通知 | `ResumeVariant`、`MessageDraft`、PDF、`ApplicationRecord`、`InterviewCase` | M4 |
| Evidence/AI 增强 | 版本化来源、检索、Evidence Pack 和可选模型增强 | `Source`、`Chunk`、`Embedding`、`EvidencePack`、增强报告版本 | M5 |
| 触发式候选 | 外部写、深度面试/出行、长期记忆和 Agent 编排 | 独立 Architecture/Task Issue 决定 | 非默认 Milestone |

## 3. 已确认的技术决策

> 以下决策用于约束后续交付。权威技术定义以 [`ARCHITECTURE.md`](ARCHITECTURE.md) §4 和 §12 为准。

| 决策 | 选择 | 说明 |
| :--- | :--- | :--- |
| **D-存储** | **PostgreSQL；M5 候选 pgvector** | 结构化事实存普通表；向量只保存可重建 Chunk/Embedding 索引。Embedding 契约先于 pgvector Schema，Milvus 仅在容量触发后评估。 |
| **D-自动化** | **半自动，外部写关闭** | 系统可以生成草稿和材料，用户手工复制、投递并确认记录；不实现自动登录平台操作。 |
| **D-模板** | **声明式不可变模板** | 模板不能执行任意代码；具体 PDF 渲染器、字体和元数据必须在 M4 实现中锁定并验证确定性。 |

## 4. 与当前项目实现的差距

### 4.1 Current 导航

本文不维护 Current 能力清单。默认分支已有能力、代码路径和合并证据只见
[`current-capabilities.toml`](current-capabilities.toml)。

### 4.2 目标能力缺口

| 缺口 | 目标边界 |
| :--- | :--- |
| 投递闭环 | 版本化投递材料、手工投递记录和最小面试通知 |
| Beta 运行 | 部署、认证、安全、恢复、持续交付与真实浏览器验收 |
| Evidence 基础 | 版本化来源、确定性 Chunk、检索评测和 Evidence Pack |
| 可选模型增强 | Provider 隔离、Schema 校验、版本化增强与确定性降级 |
| 条件规模化 | Reranker、缓存和 Worker 只在指标证明必要时引入 |

### 4.3 越界与收敛

| 项 | 处理规则 |
| :--- | :--- |
| 向量库作为业务事实主存储 | 禁止；PostgreSQL 结构化表保存事实，向量只作可重建索引 |
| 多 Agent 编排 | 不作为里程碑叙事；只有稳定 Use Case、多 Tool 和暂停/恢复需求成立后评估 |
| 外部平台自动投递/发送 | 不属于 M2-M5；重新立项需许可、Approval、幂等、审计和人工接管 |
| 深度面试复盘、实时出行和长期记忆 | 保留在触发式候选池，不阻塞 M4 最小 `InterviewCase` |
| 复杂公司情报 | M4 先交付来源、摘要、时效和 unknown；不得把匿名评价升级为事实 |

## 5. 已采用的 M2-M5 调整

| 里程碑 | 用户结果 |
| :--- | :--- |
| M2 | 基于已有岗位/主档/简历/Web 基线，补齐可确认、版本化、可直接分析的输入 |
| M3 | 无模型、向量、缓存和 Worker 也能生成确定性报告并记录 apply/skip |
| M4 | 生成投递材料、手工记录投递和面试通知，并达到可部署单用户 Beta |
| M5 | 增加 Evidence、检索和可选模型增强；规模化组件只按指标引入 |

M6+ 已取消为主动 Milestone。未来能力进入 [`ROADMAP.md`](ROADMAP.md) 的触发式候选池，而不是继续按编号预排。

## 6. 规划交接原则

1. 本文只固定业务流程和产品决策，不记录交付状态；
2. [`ROADMAP.md`](ROADMAP.md) 只固定里程碑结果、边界和退出目标；
3. 原子工作、依赖、顺序和状态只记录在 GitHub Milestones/Issues；
4. 已交付范围只通过 [`current-capabilities.toml`](current-capabilities.toml) 追踪；
5. 需要改变数据所有权、运行时组件或外部写边界时，先建立 Architecture Issue；
6. 条件组件未达到量化阈值时可以形成不引入结论。
