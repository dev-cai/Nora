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

- macOS 15.7.9 + zsh + OrbStack（包含 Docker Engine + Docker Compose）
- Git、Python 3.11、uv、Node.js 24、npm
- GitHub CLI（`gh`）

### 首次运行

```bash
git clone git@github.com:dev-cai/Nora.git
cd Nora
cp backend/.env.example backend/.env
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
cd backend && uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.apps.api:create_app --factory --host 0.0.0.0 --port 8000 --reload
# 另一个终端：cd frontend && npm ci && npm run dev
curl --fail http://localhost:8000/ready
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

`.githooks/pre-commit` 使用宿主 `backend/.venv` 中的 uv 执行格式、lint、类型检查、单元测试和架构测试。
hook 失败时修复问题后重试，不使用 `--no-verify` 绕过检查。完整集成测试仍在下方本地门禁中执行。

### 安全供应链门禁

PR 与 main push 的 `PR conventions / Secret, dependency, and SBOM gates` 使用固定 Commit SHA 的 Action：完整历史
Secret scan、PR dependency review、API/Web runtime 镜像 SPDX JSON SBOM。SBOM 作为 workflow
artifact 保留 30 天。存在 High 以上新增依赖风险或 Secret 命中时门禁失败，不能以 `exit-code: 0`、
删除扫描步骤或 mutable Action tag 绕过。

确属误报或当前无修复版本的发现项必须逐项记录：标识符、受影响镜像/包、可利用性判断、补偿控制、owner、关联 Issue 或私密安全
记录，以及不超过 30 天的到期日。到期前必须升级、移除或重新审查；例外只能进入受审查的扫描配置，不能把真实 Secret、个人数据或
漏洞利用细节写入公开仓库。无处置记录的发现项保持阻塞。

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

Frontend quality gate 会在 lint、typecheck、test 和 build 前运行 `npm run api:check`：使用锁定的 Python/uv/Node/npm 环境离线重建
FastAPI OpenAPI 与 TypeScript 声明，再通过 tracked-file、`git diff --exit-code` 和未追踪文件检查阻止契约漂移。generated 文件必须与
后端 Schema 同一 PR 提交，禁止人工编辑或从运行中服务下载。

浏览器 E2E 已暂停并从仓库移除；当前 CI 不运行 Playwright、E2E Compose 或浏览器门禁。跨 API 行为由后端集成测试、前端组件测试和 API smoke 覆盖。

Milestone 关闭前执行一次收口审计：逐项核对 Current 能力台账、默认分支代码路径、测试和已合并 PR 证据；随后运行完整文档门禁。
计划进度以 GitHub Milestone/Issue 为准，不为封版结果再创建平行的 Markdown 状态表。

### Beta 发布工作流

`.github/workflows/beta-deploy.yml` 不属于 PR 门禁，也不在分支上自动部署。它只允许在 PR 已合并、目标完整 SHA 位于受保护
`main` 且该 SHA 的后端、前端、浏览器、容器、安全和文档 check run 全部成功后手工触发。API/Web 镜像、SBOM、attestation 与
release manifest 由同一 run 产生；部署 Job 必须经过 `beta` Environment 审批并落到带 `nora-beta-deploy` 标签的专用 Runner。

Environment 的并发锁不能替代主机文件锁；Runner 也不能直接调用 Docker Compose、读取运行时 Secret 或修改 root-owned 发布
文件，只能通过 stdin 交付短期 GHCR Token，并以最小 sudo 权限调用 `/usr/local/sbin/nora-release`。正常部署和人工回滚使用同一
入口；失败后不得临时 SSH 执行未审查 Compose、可变 tag 或 Alembic downgrade。真实 Environment/Runner 尚未供应时，合并发布
代码只表示控制面已交付，不表示 Beta 已上线。

主机入口执行固定八阶段 `preflight -> backup -> pull -> migrate -> start -> internal-smoke -> public-smoke -> promote`。Nora 只发布
localhost Web 端口，真实 Host TLS Proxy 必须覆盖 forwarded headers 后转发到 Web；public smoke 使用正常证书校验验证真实 HTTPS
Origin、HSTS、Web 安全 Header 和 `/api` Web proxy 链，完成前不得写 production env、current 或 last-healthy 指针。

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
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
cd backend && uv run alembic upgrade head
uv run uvicorn app.apps.api:create_app --factory --host 0.0.0.0 --port 8000 --reload
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
cd backend
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
```

### 步骤 6：运行本地门禁

提交前必须执行以下全部检查：

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app/
uv run pytest tests/unit tests/architecture -q
docker compose -f ../docker-compose.dev.yml --profile test up -d test-db
TEST_DATABASE_URL=postgresql+asyncpg://nora_test:nora_test@localhost:5433/nora_test \
  uv run pytest tests/unit tests/integration tests/architecture -q
```

全部通过方可提交。因外部服务不可用跳过部分检查时，必须记录原因。

浏览器 E2E 已暂停并从仓库移除；PR 与 main push 不再执行浏览器门禁，也不再启动专用 E2E Compose、TLS reference proxy 或 Playwright 浏览器。

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
docker compose -f docker-compose.dev.yml up -d db storage  # 开发依赖
docker compose -f docker-compose.dev.yml down             # 停止开发依赖
docker compose -f docker-compose.dev.yml logs -f db       # 查看数据库日志
docker compose -f docker-compose.dev.yml exec db psql -U nora -d nora
docker compose -f docker-compose.yml up -d --build        # runtime 发布烟测栈
docker compose -f docker-compose.yml down
docker compose -f docker-compose.dev.yml down -v           # 清理开发数据卷
```

### 测试

```bash
cd backend
uv run pytest tests/unit/                                            # 单元
uv run pytest tests/architecture/                                    # 架构
docker compose -f ../docker-compose.dev.yml --profile test up -d test-db
TEST_DATABASE_URL=postgresql+asyncpg://nora_test:nora_test@localhost:5433/nora_test uv run pytest tests/integration -q
docker compose -f ../docker-compose.dev.yml --profile test stop test-db
```

### 代码检查

```bash
cd backend
uv run ruff check .          # Lint
uv run ruff format --check . # 格式检查
uv run ruff format .         # 自动格式化
uv run mypy app/             # 类型检查
```

### 依赖管理

```bash
cd backend
uv add <package>       # 添加依赖
uv add --dev <package> # 添加开发依赖
uv remove <package>    # 移除
uv lock                # 更新锁文件
```

修改依赖后提交 `backend/pyproject.toml` 和 `backend/uv.lock`。

### 数据库

```bash
cd backend
uv run alembic upgrade head                                      # 执行迁移
uv run alembic revision --autogenerate -m "描述"                 # 创建迁移
uv run alembic downgrade -1                                      # 回滚
docker compose -f ../docker-compose.dev.yml exec db psql -U nora -d nora
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
