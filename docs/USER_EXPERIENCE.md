# Nora 用户体验目标

本文描述个人定制求职助手的目标交互；逐项已交付状态只以 [`current-capabilities.toml`](current-capabilities.toml) 为准。

## 1. 主线流程

> 操作流程的权威定义见 [`BUSINESS_FLOW.md`](BUSINESS_FLOW.md) §2 已确认业务流程；本章只描述目标交互体验，
> 不重述业务规则与存储边界。

### 1.1 建立个人主档

用户录入并确认基本信息、项目、教育、工作经历、技能和求职偏好。Nora 为每项内容保留来源、版本和确认状态。向量索引只保存这些事实的可重建检索表示，不能替代主档。

当前 `/profile` 支持有文本层 PDF 主档导入：本地提取文本后由 DeepSeek 生成可编辑候选，用户检查后一次整体确认，非空候选写入新的
CandidateProfile 版本，不自动发布简历版本。当前不支持 DOCX、扫描 PDF OCR 或持久化 Profile ImportSession/ImportDraft；完整 D-021
Resume Import 仍是目标架构。

### 1.2 录入机会

用户可以提交 JD 文本、链接或截图。Current 路径会先抓取或 OCR 正文，再清洗并用 AI 自动填充职位、公司、地点和结构化岗位要求。
用户可修改任意字段并一次整体确认，确认时原子创建 `JobPosting` 与首个 `JobRequirementSnapshot`；确认前不写岗位事实。刷新会恢复
未确认的草稿版本，冲突要求刷新后重试。页面显示来源、时间、AI 候选和未知项；公司公开信息研究在后续阶段保留
来源、许可范围和可信等级。

### 1.3 查看适配分析

Nora 先根据已确认主档、岗位要求快照和简历版本生成确定性 Decision Report；M5 才允许用 Evidence 和模型生成独立增强版本。报告逐项说明：

- 已满足、部分满足、不满足和未知；
- 对应的个人事实和 JD 证据；
- 公司信息若存在，其来源、时效和 unknown 状态；
- 可选建议，而不是未经校准的确定性录用概率。

### 1.4 用户决定

用户明确选择“暂不投递”或“准备投递”，并可填写原因。

- 暂不投递：保存原因、报告版本和时间，供后续比较相似岗位时检索。
- 准备投递：M3 只记录 `apply`；M4 才选择模板、生成岗位专用简历变体和消息草稿，并由用户下载或手动投递。

查看新岗位报告时，Nora 最多展示 3 条同岗位族且至少共享 2 个技术栈标签的历史不投记录，并标注“历史相似记录”；用户可以忽略，不会自动改变建议。打招呼草稿只生成一段可编辑纯文本，默认专业风格，可切换简洁或内推上下文风格，用户手动复制发送。

Nora 不自动提交招聘网站表单、不自动发送消息，也不把模型建议写成用户已经做出的决定。

### 1.5 面试通知与复盘

用户收到通知后录入时间、地点、轮次、联系人和原始附件。Nora 生成基于 JD、简历和历史复盘的准备清单。面试结束后，用户录入问题、回答和自评；系统生成复盘与能力证据候选，只有用户确认后才影响长期主档。

## 2. 设计目标与交付边界

> 交付状态以 [`PRODUCT_VISION.md`](PRODUCT_VISION.md) §7 能力状态为真源；本节为 UX 视角摘要。

| 用户看到的内容 | 当前状态 | 交付边界 |
| --- | --- | --- |
| 本地账号注册、登录、Token | Current，M1 | 不含 OAuth、邮箱验证、密码重置和角色权限 |
| 岗位文本快照 | Current，M1 | 支持认证后的创建/读取、幂等和创建审计；不含评分、公司研究和报告 |
| 主档与简历事实 | Current，既有 M2 基线 | 支持手工确认主档与发布不可变简历版本；`/profile` 另支持 text-PDF AI 导入 |
| 结构化岗位要求确认 | Current，M2 | 原文与解释分离，修正后创建新版本 |
| OCR 与受控链接输入 | Current，M2 / #254 | `/jobs/new` 三模式入口提取正文并进入 JD AI 草稿；图片仍只支持 PNG/JPEG |
| `/profile` text-PDF 主档 AI 导入 | Current | 有文本层 PDF 生成可编辑候选并一次整体确认；DOCX、扫描 PDF OCR、持久化 ImportSession 未实现 |
| JD AI 自动填充 | Current，M5 / #254 | 文本/截图/受控链接统一生成职位、公司、地点和要求草稿；一次整体确认后原子创建岗位及首个要求快照 |
| 确定性决策报告与 JobFit AI | Current，M3/M5 | 报告页分区呈现确定性结果与 JobFitAnalysis；失败时确定性报告继续可用 |
| 投递/不投递决定 | Current，M3 | 报告页可记录 apply/skip；决定固定引用报告和简历版本，skip 原因必填，apply 不生成材料或执行外部写 |
| 定制简历、模板、PDF 与手工投递记录 | Current，M4 | 模板受限 Schema，产物版本化，外部写保持关闭 |
| 面试通知、准备、复盘与 MemoryCandidate | Current，M4/M5 | InterviewDetail 同时提供 Preparation/Review/Memory UI；确认记忆进入 Artifact→Source→Chunk→Embedding/RAG，不自动修改 CandidateProfile |
| Minimal RAG 与离线 Hybrid 评测 | Current，M5 | 线上仍 vector-only；Hybrid Hit@5 0.5833、unknown FPR 0.25，DO NOT SHIP |
| Agent Runtime | Current，M5 | API 进程内单 Agent/单 Graph；无独立页面/Store |
| Evidence Pack、实时出行 | Planned / Evolution | Evidence Pack 尚未交付；实时出行仍为触发式候选 |

## 3. 数据和安全提示

- 个人资料、决定、报告、投递和面试状态属于 PostgreSQL 业务事实。
- 原始简历、截图、附件和生成 PDF 属于对象存储对象；构建产物和用户数据不得提交 Git。
- Chunk 和 Embedding 是可重建派生数据，必须带用户范围、来源版本和生成器版本。
- 公司网评、匿名评价和模型输出必须保留为带标签的 Evidence 或待确认候选，不能直接升级为事实。
- ImportSession/ImportDraft 是用户确认前的版本化候选；版本或内容指纹冲突必须先刷新，不能静默覆盖或部分落库。
- 任何外部写动作都必须由用户确认、幂等执行并留下审计记录。

## 4. 性能表述规则

在基准测试完成前，不在本文承诺“几秒完成”、固定匹配百分比或模型质量指标。后续性能目标必须引用实际测试命令、环境、样本量和结果，并与产品能力状态分开记录。
