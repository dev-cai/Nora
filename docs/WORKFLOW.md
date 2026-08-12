# 开发交付工作流

> 从认领 Issue 到 PR 合并的完整操作步骤。所有开发者（人和 AI）在开始 Issue 实现前必须阅读。
>
> 相关文档：`CONTRIBUTING.md`（规则）、`docs/DEVELOPMENT.md`（环境与命令）、`docs/ISSUE_WORKFLOW.md`（Issue 规则）

---

## 工作流全景

```
  从 main 建分支（Issue 可选）──> 编码 + 测试 + Commit
        │
        v
  本地验证通过 ──> 推送 + 创建 PR + 触发自动审核
        │
        v
  自动审核通过? ──否──> 返回修改
        │ 是
        v
  CI 通过 ──> 用户合并授权 ──> 关闭关联 Issue（如有）+ 删除分支
```

---

## 前置条件

### 环境要求

- Docker Desktop（WSL2 backend，包含 Docker Engine + Docker Compose）
- Git
- GitHub CLI（`gh`）

### 首次运行

```bash
git clone git@github.com:dev-cai/Nora.git
cd Nora
cp backend/.env.example .env
docker compose up
curl http://localhost:8000/health
```

详见 `docs/DEVELOPMENT.md`。

---

## 提交前规范

### Issue 状态

状态记录在 Issue 正文中，不使用 `status:*` 标签：

| 状态 | 说明 | 设置时机 |
|------|------|---------|
| `ready` | 可开始实施 | Issue 创建时（无阻塞依赖） |
| `blocked` | 等待前置依赖 | Issue 创建时（有阻塞依赖） |
| `in-progress` | 正在实施 | 创建分支并产生实质修改后；自动审核要求修改且 PR 未合并时返回 |
| `review` | 等待 CI 和自动审核 | PR 创建后 |

### Issue 标签

每 Issue 有且仅有一个 `type:*`、一个 `priority:*`、至少一个 `area:*`。

```
  type:      architecture | epic | task | bug | docs
  priority:  p0 | p1 | p2 | p3
  area:      architecture | backend | frontend | agent | rag
             data | infra | security | docs
```

### Issue 标题

使用自然中文直接描述问题或结果。允许可选 `M<n>` / `M<n>.<n>` Milestone 前缀，例如
`M2.1 实现简历版本模型`；禁止类型方括号、`[Roadmap]`、`[Phase]` 和 Issue 编号前缀。

### 分支命名

```
  nora/<type>-<subject>

  示例：
  nora/feat-user-identity       新功能
  nora/fix-request-timeout       修复缺陷
  nora/docs-architecture         文档变更
  nora/ci-pr-conventions         CI 配置
```

### Commit 格式

```
  <type>(<optional-scope>): <中文 subject，72 字符以内>
```

| type | 使用场景 |
|------|---------|
| `feat` | 新功能、新接口、新模块 |
| `fix` | 修复缺陷 |
| `docs` | 文档、注释变更 |
| `style` | 格式调整（不影响逻辑） |
| `refactor` | 重构（不新增功能也不修 Bug） |
| `perf` | 性能优化 |
| `test` | 新增或修改测试 |
| `chore` | 工具配置、依赖维护 |
| `build` | 构建系统或外部依赖变更 |
| `ci` | CI 配置变更 |
| `revert` | 回滚提交 |

Commit 正文按需解释原因，如有关联 Issue 用 `Refs #<编号>` 引用。

### 自动审核门禁

本地实现完成并通过本地门禁后，直接推送并创建唯一 PR，随后触发 Codex 自动审核。自动审核结论只有「通过 / 不通过」：
通过 → APPROVE；不通过 → REQUEST_CHANGES + 修改建议。自动审核不通过时返回修改并重新推送重审。

自动审核通过不代表合并授权。PR 合并前必须通过 CI 与自动审核，合并仍由用户显式授权。

### 本地 Git hook

首次克隆后启用仓库提供的提交前门禁：

```bash
git config core.hooksPath .githooks
```

`.githooks/pre-commit` 使用 Compose `tools` 容器执行格式、lint、类型检查、单元测试和架构测试，
不依赖宿主 Python。hook 失败时修复问题后重试，不使用 `--no-verify` 绕过检查。完整集成测试仍在下方本地门禁中执行。

### PR 规范

- 如关联 Issue，正文包含唯一 `Closes #<编号>`；Issue 可选
- 包含：背景与目标、实际变更、明确未包含、影响分析、文档影响、验证结果
- 禁止使用 `[Roadmap]`、`[Phase]`、`[Implementation]` 前缀
- main 禁止直接推送和 force-push，Squash Merge 合并

### 文档影响门禁

[`docs-contract.toml`](docs-contract.toml) 按代码路径声明规范事实源。实现前读取命中规则的文档，推送前运行：

```bash
python scripts/docs/check_impact.py --base origin/main
python -m unittest discover -s scripts/docs/tests -v
python scripts/docs/check_links.py
python scripts/docs/check_consistency.py
```

事实发生变化时更新命中的规范文档；事实未变化时不机械修改文档，但 PR“文档影响”章节必须填写至少 12 字的具体理由。
Current 能力、代码路径与证据只维护在 [`current-capabilities.toml`](current-capabilities.toml)；临时进度只维护在 GitHub
Issue/Milestone。CI 使用同一契约复算 diff，Agent 的推送前检查不能替代 CI。

Milestone 关闭前执行一次收口审计：逐项核对 Current 能力台账、默认分支代码路径、测试和已合并 PR 证据；随后运行完整文档门禁。
计划进度以 GitHub Milestone/Issue 为准，不为封版结果再创建平行的 Markdown 状态表。

---

## 逐步操作指南

### 步骤 1：准备工作

```bash
git checkout main
git pull origin main
# 如有关联前置依赖 Issue，确认已合并
```

### 步骤 2：创建分支

```bash
git checkout -b nora/<type>-<subject>
# 示例：git checkout -b nora/feat-user-identity
```

如有关联 Issue，更新其正文状态为 `in-progress`。

### 步骤 3：启动开发环境

```bash
docker compose up -d
curl http://localhost:8000/health    # 验证服务就绪
```

新克隆仓库还需要启用本地 hook：

```bash
git config core.hooksPath .githooks
```

### 步骤 4：编码实现

- 只实现当前 Issue 范围的内容
- 遵循依赖方向：Apps/Adapters -> Application/Ports -> Domain
- Domain 层不导入 FastAPI、SQLAlchemy、LangGraph 等外部框架
- 新增代码必须有对应测试
- 源码修改后 uvicorn 自动热重载

### 步骤 5：数据库迁移（如需修改 Schema）

```bash
docker compose exec api alembic revision --autogenerate -m "描述"
docker compose exec api alembic upgrade head
```

### 步骤 6：运行本地门禁

提交前必须执行以下全部检查：

```bash
docker compose run --rm --no-deps tools ruff check .
docker compose run --rm --no-deps tools ruff format --check .
docker compose run --rm --no-deps tools mypy app/
docker compose run --rm --no-deps tools pytest tests/unit tests/architecture -q
docker compose --profile test run --rm test
```

全部通过方可提交。因外部服务不可用跳过部分检查时，必须记录原因。

浏览器门禁由 `.github/workflows/e2e.yml` 在 PR 与 main push 上启动独立 Compose 栈、执行迁移、Web/API smoke 和 Playwright 全套用例；M3 决策闭环覆盖固定版本输入、规则与报告分区、刷新恢复、apply/skip 及双用户读写隔离。工作流无论成功或失败都删除该次 Compose 容器、网络与数据卷，不复用开发数据库。

### 步骤 7：提交 Commit

```bash
git add -A
git commit -m "feat(scope): 实现的具体功能"
```

Commit 正文按需补充：

```
feat(api): 实现岗位快照创建接口

- 支持 JD 文本提交和幂等去重
- 返回稳定 ID 和来源元数据

Refs #18
```

### 步骤 8：推送、创建 PR 并触发自动审核

本地验证通过后，不再请求人工验收，直接：

```bash
git push origin nora/<type>-<subject>

gh pr create \
  --base main \
  --head nora/<type>-<subject> \
  --title "<type>(<scope>): <中文 subject>" \
  --body-file pr-body.md    # 正文可含 Closes #<编号>（可选），UTF-8 无 BOM
```

PR 正文如含 `Closes #<编号>` 必须唯一，并写明背景、实际变更、非目标、影响分析、文档影响、验证结果、未执行检查及原因、
审查重点。

如有关联 Issue，更新其正文状态为 `review`，随后触发自动审核：

```bash
python .codex/skills/nora-pr-review/scripts/nora_review.py --pr <PR 编号>
```

### 步骤 9：等待 CI 与自动审核

- CI 自动执行：ruff -> mypy -> pytest -> 架构测试
- 自动审核通过 GitHub PR Review 正式发布结论：通过 = APPROVE；不通过 = REQUEST_CHANGES + 修改建议
- CI 或自动审核不通过时，修正后重新推送并再次触发自动审核

### 步骤 10：合并

- 自动审核通过且用户审查同意后 Squash Merge
- PR 合并后自动关闭 Issue
- 删除远程分支

```bash
git branch -d nora/<type>-<subject>
```

### 步骤 11：开始下一个 Issue

回到步骤 1，从最新 `main` 开始。

---

## 快速参考

### Docker

```bash
docker compose up -d               # 后台启动
docker compose down                # 停止
docker compose logs -f api         # 查看 API 日志
docker compose exec api bash       # 进入容器
docker compose exec api python     # Python REPL
docker compose build api           # 重建 API 镜像
docker compose down -v             # 完全清理（含数据卷）
```

### 测试

```bash
docker compose run --rm --no-deps tools pytest tests/unit/           # 单元
docker compose run --rm --no-deps tools pytest tests/architecture/   # 架构
docker compose --profile test run --rm test                           # 全部，集成测试使用隔离 PostgreSQL
docker compose --profile test run --rm test pytest -k "job_posting" # 筛选
docker compose --profile test stop test-db                            # 停止临时测试数据库
```

### 代码检查

```bash
docker compose run --rm --no-deps tools ruff check .          # Lint
docker compose run --rm --no-deps tools ruff format --check . # 格式检查
docker compose run --rm --no-deps tools ruff format .         # 自动格式化
docker compose run --rm --no-deps tools mypy app/             # 类型检查
```

### 依赖管理

```bash
docker compose run --rm --no-deps tools uv add <package>       # 添加依赖
docker compose run --rm --no-deps tools uv add --dev <package> # 添加开发依赖
docker compose run --rm --no-deps tools uv remove <package>    # 移除
docker compose run --rm --no-deps tools uv lock                # 更新锁文件
```

修改依赖后提交 `backend/pyproject.toml` 和 `backend/uv.lock`。

### 数据库

```bash
docker compose exec api alembic upgrade head               # 执行迁移
docker compose exec api alembic revision --autogenerate -m "描述"  # 创建迁移
docker compose exec api alembic downgrade -1               # 回滚
docker compose exec db psql -U nora -d nora               # 连接 PostgreSQL
```

---

## 禁令清单

1. main 直接推送。所有变更必须通过 PR 合并
2. Force push 到 main。main 分支受保护
3. 无分支的提交。每个 PR 必须对应一个独立分支
4. 无本地验证结果的推送。推送前必须跑完本地门禁；PR 合并前必须通过自动审核
5. 使用 `[Roadmap]`、`[Phase]` 等固定标题前缀
6. 提交 `.env`、密钥、Token、Cookie、浏览器会话、真实简历等敏感信息
7. 不经过 Architecture Issue 新增依赖、数据所有权或外部写能力
8. Domain 层导入 FastAPI、SQLAlchemy、LangGraph 等外部框架
9. 提交 `.cache/`、`__pycache__/`、`.venv/` 等缓存文件
10. 混入多个 Issue 的内容到同一个 PR
