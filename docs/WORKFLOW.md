# 开发交付工作流

> 从认领 Issue 到 PR 合并的完整操作步骤。所有开发者（人和 AI）在开始 Issue 实现前必须阅读。
>
> 相关文档：`CONTRIBUTING.md`（规则）、`docs/DEVELOPMENT.md`（环境与命令）、`docs/ISSUE_WORKFLOW.md`（Issue 规则）

---

## 工作流全景

```
  认领 Issue ──> 创建 nora/ 分支 ──> 编码 + 测试 + Commit
        │
        v
  提交验收清单 ──> 用户授权? ──否──> 返回修改
        │ 是
        v
  推送分支 + 创建 PR ──> CI 通过 ──> 用户合并 ──> 关闭 Issue
```

---

## 前置条件

### 环境要求

- Docker Desktop 或 Docker Engine + Docker Compose
- Git
- GitHub CLI（`gh`）

### 首次运行

```bash
git clone git@github.com:dev-cai/Nora.git
cd Nora
cp .env.example .env
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
| `in-progress` | 正在实施 | 创建分支并产生实质修改后 |
| `acceptance` | 待用户验收 | 本地待验收版本完成后 |
| `review` | 等待 CI 和审查 | PR 创建后 |

### Issue 标签

每 Issue 有且仅有一个 `type:*`、一个 `priority:*`、至少一个 `area:*`。

```
  type:      architecture | epic | task | bug | docs
  priority:  p0 | p1 | p2 | p3
  area:      architecture | backend | frontend | agent | rag
             data | infra | security | docs
```

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
| `refactor` | 重构（不新增功能也不修 Bug） |
| `test` | 新增或修改测试 |
| `chore` | 工具配置、依赖维护 |
| `ci` | CI 配置变更 |

Commit 正文按需解释原因，引用 Issue：`Refs #<编号>`。

### 人工验收门禁（强制）

本地实现完成 **不等于** 可以推送。推送前必须提交验收清单：

```
  Issue 编号与链接
  当前分支名与本地 Commit
  基于真实 diff 的变更摘要
  已执行验证及其实际结果
  未执行检查及原因
  用户可直接操作的验收步骤
```

只有用户明确说"可以推送"后才能执行 `git push`。授权只对当前版本有效，修改后自动失效。推送授权不包含合并授权。

### PR 规范

- 正文必须以 `Closes #<编号>` 开头
- 包含：背景与目标、实际变更、明确未包含、影响分析、验证结果
- 禁止使用 `[Roadmap]`、`[Phase]`、`[Implementation]` 前缀
- main 禁止直接推送和 force-push，Squash Merge 合并

---

## 逐步操作指南

### 步骤 1：准备工作

```bash
git checkout main
git pull origin main
# 确认前置依赖 Issue 已合并
```

### 步骤 2：创建分支

```bash
git checkout -b nora/<type>-<subject>
# 示例：git checkout -b nora/feat-user-identity
```

更新 Issue 正文状态为 `in-progress`。

### 步骤 3：启动开发环境

```bash
docker compose up -d
curl http://localhost:8000/health    # 验证服务就绪
```

### 步骤 4：编码实现

- 只实现当前 Issue 范围的内容
- 遵循依赖方向：Domain -> Application -> Adapters
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
docker compose exec api ruff check .
docker compose exec api mypy src/
docker compose exec api pytest
```

全部通过方可提交。因外部服务不可用跳过部分检查时，必须记录原因。

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

### 步骤 8：提交人工验收

推送前停止，向用户提交验收清单。

验收清单示例：

```
## 验收清单

Issue：M1.3 实现岗位快照 API（#18）
分支：nora/feat-job-posting-api
本地 Commit：a1b2c3d4

变更摘要：
- 新增 4 个文件
- 修改 2 个文件

已执行验证：
- ruff check .            通过
- mypy src/               通过
- pytest tests/           通过（24 passed）
- alembic upgrade head    通过

验收步骤：
1. curl -X POST localhost:8000/job-postings ...
2. curl -X GET localhost:8000/job-postings/{id} ...
```

在用户明确授权前，不得执行 `git push`。

### 步骤 9：推送与创建 PR

```bash
git push origin nora/<type>-<subject>

gh pr create \
  --base main \
  --head nora/<type>-<subject> \
  --title "<type>(<scope>): <中文 subject>" \
  --body "Closes #<编号>
...
"
```

更新 Issue 正文状态为 `review`。

### 步骤 10：等待 CI 与审查

- CI 自动执行：ruff -> mypy -> pytest -> 架构测试
- PR 正文必须包含 `Closes #<Issue>`，否则 CI 拒绝
- CI 失败时修正后重新推送

### 步骤 11：合并

- 用户审查通过后 Squash Merge
- PR 合并后自动关闭 Issue
- 删除远程分支

```bash
git branch -d nora/<type>-<subject>
```

### 步骤 12：开始下一个 Issue

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
docker compose exec api pytest                             # 全部
docker compose exec api pytest tests/unit/                 # 单元
docker compose exec api pytest tests/architecture/         # 架构
docker compose exec api pytest -k "test_job_posting"      # 筛选
docker compose exec api pytest --cov=nora --cov-report=term # 覆盖率
```

### 代码检查

```bash
docker compose exec api ruff check .                       # Lint
docker compose exec api ruff format --check .              # 格式检查
docker compose exec api ruff format .                      # 自动格式化
docker compose exec api mypy src/                          # 类型检查
```

### 依赖管理

```bash
docker compose exec api uv add <package>                   # 添加依赖
docker compose exec api uv add --dev <package>             # 添加开发依赖
docker compose exec api uv remove <package>                # 移除
docker compose exec api uv sync --upgrade                  # 更新全部
```

修改依赖后提交 `pyproject.toml` 和 `uv.lock`。

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
3. 无 Issue 的提交。所有变更必须关联 Issue（仓库初始化除外）
4. 验收前推送。必须先提交验收清单并获得用户明确授权
5. 使用 `[Roadmap]`、`[Phase]` 等固定标题前缀
6. 提交 `.env`、密钥、Token、Cookie、浏览器会话、真实简历等敏感信息
7. 不经过 Architecture Issue 新增依赖、数据所有权或外部写能力
8. Domain 层导入 FastAPI、SQLAlchemy、LangGraph 等外部框架
9. 提交 `__pycache__/`、`.venv/`、`.pytest_cache/` 等缓存文件
10. 混入多个 Issue 的内容到同一个 PR
