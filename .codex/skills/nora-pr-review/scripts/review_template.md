# Codex 自动审核意见

**审核方式**：Codex 自动审核 · 本仓库本地脚本

| 项目 | 内容 |
|------|------|
| PR | #{{PR}} {{TITLE}} |
| 分支 | {{HEAD}} → {{BASE}} |
| 变更规模 | +{{ADDITIONS}} / -{{DELETIONS}}，共 {{CHANGED_FILES}} 个文件 |
| CI 状态 | {{CHECKS}} |

## 审核结论

{{CONCLUSION}}（{{VERDICT}}）

## 审核范围

- 依据 PR diff（+{{ADDITIONS}}/-{{DELETIONS}}）与关联 Issue 验收条件
- 对照 `docs/ARCHITECTURE.md` 依赖方向与边界
- 检查项：静态质量、契约与测试覆盖、安全与外部写、密钥/凭据、文档同步、Issue 范围一致性

## 通过项

{{APPROVED_ITEMS}}

## 修改建议

| 严重度 | 位置（文件:行） | 问题 | 修改建议 |
|--------|-----------------|------|----------|
{{SUGGESTIONS_ROWS}}

## 结论说明

{{CONCLUSION_NOTE}}
