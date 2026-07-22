# Nora

Nora（Navigate · Observe · Review · Agent）是一个面向求职决策的可审计多智能体平台。目标是以
Agentic RAG 组织企业背景、岗位匹配、面试准备、出行规划、风险研判和长期复盘，为用户生成附带证据引用的
求职决策报告。

## 当前状态

这是全新架构周期的治理基线。仓库当前只包含协作规范、GitHub 模板、项目 Skill 和流程校验，不包含应用代码、
依赖、数据库结构、Agent、RAG、外部集成或部署实现。

技术栈、系统边界、数据所有权、安全模型和交付路线必须先由独立 Architecture Issue 确认，再以一个个可验收
切片实施。路线图不是完成状态，创建目录或接口占位也不算功能落地。

## 核心原则

- 事实、推断和建议必须明确区分，关键结论保留来源与版本。
- Agent 只编排确定的应用用例，不直接成为业务事实来源。
- 网页、文档、模型输出和外部回调均视为不可信输入。
- 外部写默认关闭，并受审批、幂等、审计和安全边界约束。
- 一 Issue、一 `nora/` 分支、一 PR；合并后再开始下一项。
- Commit、PR 标题和项目说明首选中文，技术标识保持行业标准写法。

## 开始协作

1. 阅读 [架构状态](docs/ARCHITECTURE.md)。
2. 阅读 [Issue 工作流](docs/ISSUE_WORKFLOW.md) 和 [贡献指南](CONTRIBUTING.md)。
3. 创建或认领一个范围明确、可独立验收的 Issue。
4. 从最新 `main` 创建 `nora/<type>-<subject>` 分支。
5. 通过 PR、CI 和审查后合并，再开始下一项。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。
