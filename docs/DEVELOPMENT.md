# Nora 开发指南

> 本指南以 Windows 11/10 + Docker Desktop（WSL2 backend）+ WSL2 Ubuntu 为推荐的本地开发环境。
> 日常 Git、Docker 和 Docker Compose 命令在 WSL 终端中执行；Python、uv、Alembic 和质量工具只在容器内执行。
> Windows PowerShell 只用于一次性安装或管理 WSL 与 Docker Desktop，不用于项目开发命令。

## 环境边界

本地开发使用以下边界：

```text
Windows
  ├─ Docker Desktop：WSL2 backend、Docker Engine、Docker Compose
  └─ WSL2 Ubuntu
      ├─ 项目代码：~/projects/Nora
      ├─ Git + Docker CLI
      └─ Compose 容器：Node.js、Web、Python/uv、API、PostgreSQL、MinIO
```

宿主不安装项目 Python、uv、pytest、ruff、mypy 或 Alembic。Docker Desktop 必须启用目标 WSL 发行版集成；
不要同时在 WSL 中另起一套 Docker Engine。

## 前置条件

### Windows 一次性准备

在管理员 PowerShell 中安装 WSL2、Ubuntu 和 Docker Desktop：

```powershell
wsl --install -d Ubuntu
winget install --exact --id Docker.DockerDesktop
```

安装完成后重启 Windows，并从开始菜单打开 Ubuntu，创建 Linux 用户。检查 WSL 版本：

```powershell
wsl --list --verbose
```

目标发行版的 `VERSION` 应为 `2`。

启动 Docker Desktop，在 Settings → Resources → WSL Integration 中启用 Ubuntu。

### WSL 内安装工具

以下命令全部在 Ubuntu/WSL 终端执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
```

Docker CLI 与 Compose 由 Docker Desktop 注入 WSL。验证宿主边界：

```bash
docker version
docker compose version
git --version
```

不在 WSL 中安装 Python 或 uv；后续命令由 Compose development 镜像提供。

## 获取代码

建议把仓库放在 WSL 的 Linux 文件系统中，而不是 `/mnt/c` 或 `/mnt/d` 下。这样可以避免 bind mount、文件监听和 I/O 性能问题。

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/dev-cai/Nora.git
cd Nora
```

Windows 访问该目录时使用资源管理器地址：

```text
\\wsl$\Ubuntu\home\<linux-user>\projects\Nora
```

从 WSL 访问 Windows 文件时使用 `/mnt/<drive-letter>/...`，但不建议将 Nora 工作区放在那里。

## 快速开始

以下命令均在 WSL 的仓库根目录执行：

```bash
cd "$HOME/projects/Nora"
cp backend/.env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Compose 会启动：

- `web`：Vue 3 工作台，监听 `localhost:5173`，浏览器内的 `/api` 请求代理到 API
- `api`：FastAPI API，监听 `localhost:8000`
- `db`：PostgreSQL 16
- `storage`：私有 MinIO，对象字节只通过认证后的 Artifact API 访问
- `storage-init`：一次性创建私有 Bucket、最小权限 Policy 和应用账户，成功后 API 才启动

另开一个 WSL 终端验证：

```bash
cd "$HOME/projects/Nora"
curl http://localhost:8000/live
curl --fail http://localhost:8000/ready
curl http://localhost:5173
docker compose ps
```

首次启动和拉取到新迁移后都要执行 `alembic upgrade head`。API 不会在启动时自动修改数据库结构。

API 进程存活时 `/live` 返回：

```json
{"status":"live"}
```

`/live` 不检查外部依赖。PostgreSQL 可连接且 `SELECT 1` 成功时 `/ready` 返回 `200` 与
`{"status":"ready"}`；未配置、连接失败、查询失败或超时时返回 `503` 与
`{"status":"not_ready","database":"unavailable"}`。

## 环境变量与 Compose 对照

`backend/.env.example` 是可公开提交的本地开发模板。快速开始命令把它复制为仓库根目录 `.env`，供 Compose
执行 `${VARIABLE:-default}` 插值；根 `.env` 不会被整体注入容器，只有 Compose `environment` 中明确列出的值才会进入
对应进程。不要在 `backend/.env.example` 中填写真实值，也不要提交根 `.env`。

本地开发的覆盖顺序为：当前 shell 已导出的变量优先于根 `.env`，两者都没有提供时才使用 Compose 中的 `:-` 默认值。
API 容器启动后，Settings 从进程环境读取同名变量；进程环境优先于 Settings 的 `backend/.env` 文件和代码默认值。

### 可配置变量

| 变量 | 模板值与有效默认值 | 所有者和作用域 | 安全与使用边界 |
|------|--------------------|----------------|----------------|
| `ENV` | `dev` | Compose 注入 API；Settings 接受 `dev`、`staging`、`prod` | 非开发环境会启用更严格的密钥校验 |
| `DEBUG` | 模板和开发 Compose 为 `true`；Settings 独立默认 `false` | API / Settings | 非开发环境应为 `false` |
| `LOG_LEVEL` | 模板和开发 Compose 为 `DEBUG`；基础 Compose 与 Settings 默认 `INFO` | API / Settings | 不得通过调高日志级别记录 Token、密码或正文 |
| `API_PORT` | `8000` | 仅 Compose 宿主端口；映射到 API 容器固定端口 `8000` | 端口冲突时可修改，不进入 Settings |
| `WEB_PORT` | `5173` | 仅 Compose 宿主端口；映射到 Web 容器固定端口 `5173` | 端口冲突时可修改，不进入后端 Settings |
| `AUTH_SECRET_KEY` | `development-only-change-this-secret` | Compose 注入 API；Settings 要求至少 32 个字符 | 公开值仅限本地；`staging`/`prod` 必须替换且不得提交 |
| `AUTH_ACCESS_TOKEN_MINUTES` | `30` | Compose 注入 API；Settings 允许 `1`–`1440` | 控制访问令牌有效期，不是密钥 |
| `BAIDU_OCR_API_KEY` | 空 | API / Settings（百度智能云 OCR 应用凭据） | 生产环境必须配置且不得提交；未配置时 OCR 接口返回稳定 `ocr_failed` |
| `BAIDU_OCR_SECRET_KEY` | 空 | API / Settings（百度智能云 OCR 应用凭据） | 生产环境必须配置且不得提交；与 API Key 成对 |
| `BAIDU_OCR_ENDPOINT` | `accurate_basic` | API / Settings | 百度 OCR 接口名，如 `general_basic` / `accurate_basic` |
| `POSTGRES_USER` | `nora` | Compose 配置 `db`，并参与派生 API 的 `DATABASE_URL` | 生产环境不得沿用公开示例凭据 |
| `POSTGRES_PASSWORD` | `change-me-local` | Compose 配置 `db`，并参与派生 API 的 `DATABASE_URL` | 仅限本地示例；真实值不得提交或输出到日志 |
| `POSTGRES_DB` | `nora` | Compose 配置 `db`，并参与派生 API 的 `DATABASE_URL` | 数据库名称，不是宿主地址 |
| `POSTGRES_PORT` | `5432` | 仅 Compose 宿主端口；映射到 `db:5432` | 容器间连接始终使用固定端口 `5432` |
| `STORAGE_PORT` | `9000` | 仅 Compose 宿主 S3 API 端口；映射到 `storage:9000` | 仅用于开发调试；浏览器和前端不得直连 |
| `STORAGE_CONSOLE_PORT` | `9001` | 仅 Compose 宿主控制台端口；映射到 `storage:9001` | 不应暴露到不可信网络 |
| `MINIO_ROOT_USER` | `minioadmin` | Compose 只注入 `storage` 容器 | 公开值仅限本地，生产环境必须替换 |
| `MINIO_ROOT_PASSWORD` | `change-me-local` | Compose 只注入 `storage` 容器 | 公开值仅限本地，真实值不得提交 |
| `ARTIFACT_STORAGE_ACCESS_KEY` | `nora-app` | `storage-init` 创建并注入 API | 仅有目标私有 Bucket 的读写删权限，不是 root 凭据 |
| `ARTIFACT_STORAGE_SECRET_KEY` | `development-artifact-secret` | `storage-init` 与 API | 公开值仅限本地；非开发环境必须通过 Secret 管理注入 |
| `ARTIFACT_STORAGE_BUCKET` | `nora-artifacts` | `storage-init` 与 API / Settings | Bucket 保持私有，不提供匿名或长期签名 URL |
| `ARTIFACT_STORAGE_ENDPOINT` | Compose 固定 `storage:9000`；模板为 `localhost:9000` | API / Settings | 使用 `host:port`，不得包含 scheme 或路径 |
| `ARTIFACT_STORAGE_SECURE` | Compose 与模板为 `false` | API / Settings | Beta/生产按 #171 的 TLS 边界配置 |

### 内部派生值

这些变量不属于根 `.env` 的用户配置面，因此不写入 `backend/.env.example`：

| 变量 | 来源和有效值 | 作用域 |
|------|--------------|--------|
| `DATABASE_URL` | Compose 使用 `POSTGRES_USER`、`POSTGRES_PASSWORD` 和 `POSTGRES_DB` 生成 `postgresql+asyncpg://<user>:<password>@db:5432/<database>` | API 容器 / Settings；必须使用 `postgresql+asyncpg` |
| `DATABASE_URL`、`TEST_DATABASE_URL` | test profile 固定为隔离测试库 `postgresql+asyncpg://nora_test:nora_test@test-db:5432/nora_test` | 仅 `test` 容器；不连接开发数据卷 |
| `PYTHONPYCACHEPREFIX` | Compose 固定为 `/workspace/backend/.cache/pycache` | API development、tools 和 test 容器的缓存路径 |

容器内服务发现使用 Compose 服务名：API 连接 PostgreSQL 时主机是 `db`，测试容器连接 `test-db`。从 WSL 宿主
直接连接开发 PostgreSQL 时才使用 `localhost:${POSTGRES_PORT}`。`localhost` 在 API 容器内指向 API 容器自身，不能替代
`db`。同理，宿主访问 API 和 MinIO 时使用对应宿主端口，容器间访问使用服务名和固定容器端口。

Settings 还提供以下应用级默认值，但当前 Compose 没有把它们列入根 `.env` 配置面：

| Settings 变量 | 代码默认值 | 说明 |
|---------------|------------|------|
| `LOG_FORMAT` | `json` | 可选 `json` 或 `console` |
| `DATABASE_POOL_SIZE` | `5` | 数据库连接池常驻连接数 |
| `DATABASE_MAX_OVERFLOW` | `10` | 连接池允许的额外连接数 |
| `DATABASE_POOL_TIMEOUT` | `30.0` | 获取连接的超时秒数 |
| `ARTIFACT_MAX_SIZE_BYTES` | `10485760` | 单个 Artifact 最大 10 MiB，最高允许配置为 100 MiB |
| `ARTIFACT_ALLOWED_CONTENT_TYPES` | PNG、JPEG、PDF、纯文本、HTML | 逗号分隔 allowlist；未列类型返回 `415` |

### Artifact 与 Source 本地验证

`storage-init` 使用 MinIO root 凭据完成受控初始化；API 容器只收到最小权限应用凭据。上传返回的公开元数据不包含 Bucket、
对象键或凭据，下载经认证 API 代理并设置安全响应头。运行真实 Adapter 合约测试：

```bash
docker compose up -d db storage storage-init
docker compose run --rm -e TEST_ARTIFACT_STORAGE_ENDPOINT=storage:9000 \
  -e TEST_ARTIFACT_STORAGE_ACCESS_KEY=nora-app \
  -e TEST_ARTIFACT_STORAGE_SECRET_KEY=development-artifact-secret \
  -e TEST_ARTIFACT_STORAGE_BUCKET=nora-artifacts test \
  uv run pytest tests/integration/test_minio_artifact_storage.py -q
```

数据库迁移继续使用 `alembic upgrade head`；#21 的 `0014_artifacts_sources` 支持降级后重新升级。不要使用 MinIO Console
或对象存在性判断业务状态，PostgreSQL 中的 Artifact 生命周期始终是唯一事实源。

如需覆盖这些 Settings-only 值，应在受审查的 Compose environment 或进程环境中显式提供；只把它们写进仓库根 `.env`
不会自动注入 API。此 Issue 不定义生产秘密管理或部署拓扑。

### 对照验证

在 WSL 仓库根目录运行以下检查。它会双向比较模板变量与两份 Compose 文件的插值变量；任一侧多出变量都会显示差异并
让命令失败。内部派生值和固定值由上表单独维护，不参与插值集合比较。

```bash
example_vars="$(mktemp)"
compose_vars="$(mktemp)"
trap 'rm -f "$example_vars" "$compose_vars"' EXIT

sed -n 's/^\([A-Z][A-Z0-9_]*\)=.*/\1/p' backend/.env.example | sort -u >"$example_vars"
grep -hoE '\$\{[A-Z][A-Z0-9_]*' docker-compose.yml docker-compose.override.yml \
  | cut -c3- | sort -u >"$compose_vars"

comm -3 "$example_vars" "$compose_vars"
test -z "$(comm -3 "$example_vars" "$compose_vars")"
docker compose --profile test config --quiet
```

检查成功时 `comm` 没有输出，后续命令退出码为 `0`。`docker compose config` 的完整渲染结果可能包含本地密码，排障时只在
本机查看，不要粘贴到 Issue、PR、日志或聊天记录。

### 验证 Identity API

Identity 纵向切片提供本地用户名/密码注册、登录和当前用户查询：

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"change-me-123"}'

curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"change-me-123"}'

curl http://localhost:8000/auth/me \
  -H 'Authorization: Bearer <access_token>'
```

访问令牌默认有效期为 30 分钟。`AUTH_SECRET_KEY` 的开发默认值只适用于本机；`ENV=staging` 或
`ENV=prod` 时必须提供至少 32 字节的随机值，否则应用拒绝启动。例如可在 WSL 中生成：

```bash
openssl rand -hex 32
```

不要把生成值写回 `backend/.env.example` 或提交包含真实密钥的 `.env`。

### 验证岗位快照 API

登录取得 Token 后，使用每次导入操作唯一的 `Idempotency-Key` 创建岗位快照：

```bash
curl -i -X POST http://localhost:8000/job-postings \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Idempotency-Key: local-job-001' \
  -H 'Content-Type: application/json' \
  -d '{"jd_text":"Senior Python Engineer - Build reliable APIs.","job_title":"Backend Engineer","company_name":"Example Corp","location":"Shanghai","source_type":"manual"}'

curl 'http://localhost:8000/job-postings?page=1&page_size=20' \
  -H 'Authorization: Bearer <access_token>'

curl http://localhost:8000/job-postings/<job_posting_id> \
  -H 'Authorization: Bearer <access_token>'
```

首次创建返回 `201`；同一用户使用同键和同内容重试返回首次结果及 `200`；同键但内容不同返回 `409`。
旧客户端可以省略标题、公司和地点，服务端会分别回填“未提供职位”“未提供公司”“未提供地点”；显式传入空值、
空白字符串或超过 200 个字符时返回 `422`。列表按创建时间倒序返回，`page` 从 `1` 开始，`page_size` 范围为 `1`–`100`。
岗位 ID 只能由所属用户读取，不存在或属于其他用户时统一返回 `404`。
首次创建还会在同一数据库事务中追加一条不含 JD 正文的审计事件；幂等重放不会重复记录事件。审计摘要只保存
`source_type` 和 `status`，目标创建版本单独保存为结构化 `target_version`。该字段必须是大于等于 `1` 的非空整数，
岗位创建事件使用实际持久化版本；迁移会将既有审计记录回填为 `1`，数据库默认值也保留为 `1`，以兼容旧版追加方。

岗位、幂等记录和审计事件构成同一事务：任一写入失败时三者均不提交。同一用户和幂等键的并发请求最多创建一条岗位、
一条幂等记录和一条审计事件；同键不同内容仍返回 `409 idempotency_conflict`，不会追加第二条审计事件。

### 验证 CandidateProfile API

主档接口要求先完成注册并携带登录返回的 Bearer Token。首次 `PUT` 创建版本 1，后续完整提交会追加版本；
`GET` 默认读取最新版本，也可以通过 `version` 查询历史快照。字段确认状态和 `user_input` 来源由服务端保存。

```bash
curl -X PUT http://localhost:8000/profile \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "basic_information": {
      "display_name": {"value": "Alice", "confirmation_status": "confirmed"},
      "current_location": {"value": "Shanghai", "confirmation_status": "confirmed"}
    },
    "preferences": {
      "target_locations": {"value": ["Shanghai", "Remote"], "confirmation_status": "confirmed"},
      "accepts_remote": {"value": true, "confirmation_status": "confirmed"},
      "target_roles": {"value": ["Backend Engineer"], "confirmation_status": "unconfirmed"}
    },
    "education": [],
    "experiences": [],
    "skills": [{
      "id": "75c9697d-a4a0-4e54-8ee8-9f4df51489ec",
      "name": {"value": "Python", "confirmation_status": "confirmed"},
      "proficiency": {"value": "advanced", "confirmation_status": "unconfirmed"},
      "years": {"value": 5, "confirmation_status": "confirmed"}
    }]
  }'

curl http://localhost:8000/profile \
  -H 'Authorization: Bearer <access_token>'

curl 'http://localhost:8000/profile?version=1' \
  -H 'Authorization: Bearer <access_token>'
```

跨用户访问不会暴露主档存在性，统一返回 `404 entity_not_found`。教育、经历和技能条目的 UUID 必须由客户端生成并在后续
完整 `PUT` 中保持稳定，同一集合内不得重复。

### 验证 ResumeVersion API

从明确的 CandidateProfile 版本发布简历快照。发布只复制 confirmed 基本信息、教育、经历和技能；求职偏好及未确认字段
不会进入简历。主档后续变化不会改写已经发布的历史版本。

```bash
curl -X POST http://localhost:8000/resumes \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Backend Resume","profile_version":1}'

curl 'http://localhost:8000/resumes?page=1&page_size=20' \
  -H 'Authorization: Bearer <access_token>'

curl http://localhost:8000/resumes/<resume_version_id> \
  -H 'Authorization: Bearer <access_token>'
```

每次发布返回 `201` 并生成新的用户范围版本号。指定主档版本不存在或属于其他用户时返回 `404 entity_not_found`；主档没有
可发布的 confirmed 简历事实时返回 `400 profile_has_no_confirmed_data`。ResumeVersion 发布本身不导入简历文件；模板、岗位定制和
PDF 生成由后续独立接口处理。

停止服务但保留数据卷：

```bash
docker compose stop
docker compose down
```

删除容器和本地数据库/MinIO 数据：

```bash
docker compose down -v
```

## 日常操作

### 前端开发与质量检查

前端使用 Node.js 24、npm、Vue 3、Vite、TypeScript、Vue Router 和 Pinia。Node 版本单一真源为
`frontend/.nvmrc`（当前 24.18.1），配合 `frontend/.npmrc` 的 `engine-strict=true` 作为硬门禁；CI 通过
`node-version-file: frontend/.nvmrc` 读取同一版本。使用 Compose 启动时，Vite 将
`/api` 代理到 `http://api:8000`；直接在宿主运行时默认代理到 `http://localhost:8000`。可在
`frontend/.env` 中通过 `VITE_NORA_API_BASE_URL` 覆盖浏览器 API 基础路径，或通过
`VITE_NORA_PROXY_TARGET` 覆盖 Vite 开发代理目标。不要在这些变量中写入 Token 或其他秘密。

在 WSL 仓库根目录使用 Compose 开发：

```bash
docker compose up -d --build db api web
docker compose exec api alembic upgrade head
```

如需直接运行前端工具，进入 `frontend/` 后执行：

```bash
npm ci
npm run api:generate
npm run api:check
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
```

`api:generate` 使用 `backend/scripts/export_openapi.py` 离线调用 FastAPI 应用工厂，再以锁定的
`openapi-typescript@7.13.0` 重建 `frontend/src/api/generated/openapi.json` 与 `schema.d.ts`；不启动 API、连接数据库或读取常规
Nora 运行时环境变量。该命令需要仓库锁定的 Python 3.11、uv 0.11.3、Node 24.18.1 与 npm 11 环境；CI 会显式安装这些版本。
`api:check` 重建后验证两个文件已被 Git 追踪、无 diff 且目录没有未追踪输出。修改 FastAPI 路由或 Pydantic 响应契约时必须同时提交重建结果。

登录 Token 与当前用户只在标签页级 `sessionStorage` 中受控保存；刷新后通过 `/auth/me` 校验恢复，登出、`401` 或校验失败会彻底清除。前端只通过公开 HTTP API 访问 Nora，
不得连接数据库、导入后端模块或读取后端内部文件。

查看服务日志：

```bash
docker compose logs -f
docker compose logs -f api
docker compose logs -f web
```

### 浏览器级真实 Compose E2E

当前质量门禁在真实浏览器中验证 M2 输入与 M3 决策闭环。E2E 使用 Playwright（用例位于 `frontend/e2e/`），在 Compose 栈
就绪后运行：

```bash
docker compose up -d --build db api web
docker compose exec api alembic upgrade head

# 等待 web(:5173) 与 api(:8000) 就绪后，在 frontend/ 下执行：
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

- 用例 `frontend/e2e/main-flow.spec.ts` 覆盖：注册/登录 → 刷新保持登录 → 创建岗位 → 主档保存 → 简历列表 →
  登出后受保护路由跳转登录。
- 用例 `frontend/e2e/analysis-ready.spec.ts` 覆盖：确认主档与简历 → 岗位要求版本追加 → 刷新恢复 → 双用户隔离。
- 用例 `frontend/e2e/decision-flow.spec.ts` 覆盖：创建固定版本 DecisionCase → 断言 match/unknown 规则结果 → 生成并刷新恢复报告 → 记录并恢复 skip 决定 → 双用户读取与写入隔离 → 原用户重新登录后按固定标识恢复案例、报告和决定；主流程不使用 Mock 或外部 Provider，完整 HTTP 错误组合由 API 契约和集成测试承担。
- 失败时在 `frontend/test-results/` 与 `frontend/playwright-report/` 生成截图与 trace；可执行
  `npm run e2e:report` 查看。
- 每次运行使用隔离随机账号，不在业务数据中制造冲突。
- CI：`.github/workflows/e2e.yml` 在每个 PR 和 main push 上启动 Compose、迁移隔离数据库、执行 Web/API smoke 与同一套浏览器用例，并在成功或失败后通过 `docker compose down --volumes --remove-orphans` 清理隔离环境。

### 请求关联标识

API 为每个请求维护 `request_id` 结构化日志字段，用于定位单次 HTTP 请求的响应和日志。

客户端可以通过 `X-Request-ID` 传入标识。缺失时服务端生成 UUID，并通过同名响应头回传。
传入值必须为 1–128 位，只能包含 ASCII 字母、数字、点、下划线和连字符，且首位必须是字母或数字；非法值返回
`400` 和稳定错误码 `invalid_correlation_id`，该错误响应仍携带服务端生成的有效 `X-Request-ID`。标识不得包含 Token、
Cookie、请求正文、邮箱或其他个人数据。

`X-Trace-ID` 不属于当前契约：服务端忽略调用方传入值，也不生成、记录或回传伪 Trace ID。排障时从响应头取得
`X-Request-ID` 定位单次请求；请求结束后服务端会清理字段，避免上下文泄漏到后续请求。

查看容器状态和资源：

```bash
docker compose ps
docker stats
```

修改 `backend/app/` 后，开发覆写文件会挂载 WSL 工作区，Uvicorn 会自动重载 API。

执行数据库迁移：

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic downgrade -1
docker compose exec api alembic history
```

连接 PostgreSQL：

```bash
docker compose exec db psql -U nora -d nora
```

## 本地测试与质量检查

Compose 开发覆写使用 Dockerfile 的 `development` target，开发依赖安装在容器 `/opt/venv`，不会被仓库
bind mount 覆盖。静态检查、单元测试和架构测试不需要启动依赖服务：

```bash
docker compose build api tools
docker compose run --rm --no-deps tools ruff check .
docker compose run --rm --no-deps tools ruff format --check .
docker compose run --rm --no-deps tools mypy app/
docker compose run --rm --no-deps tools pytest tests/unit tests/architecture -q
```

集成测试只连接 `test` profile 中的隔离 PostgreSQL。`test-db` 使用 tmpfs，不复用开发数据库或命名卷：

```bash
docker compose --profile test run --rm test
docker compose --profile test stop test-db
```

集成测试要求 `TEST_DATABASE_URL` 或 `DATABASE_URL` 使用 `postgresql+asyncpg`。缺少连接或使用其他驱动时，
测试会明确失败；项目不支持 SQLite 回退。

### 确定性 PDF 渲染环境

PDF 渲染只以 `docker/Dockerfile.api` 构建的锁定 Linux 环境为可复现基线：Python 依赖锁定 WeasyPrint 69.x，系统包固定
Pango 1.56.3 与 Noto CJK 20240730，镜像和 Adapter 固定 `SOURCE_DATE_EPOCH=1767225600`。渲染器版本同时记录
WeasyPrint、Pango、Adapter 和 SOURCE_DATE_EPOCH，字体集另有独立版本；升级任一输入都必须形成新的生成身份并重新执行
确定性测试。宿主缺少 Pango 时可以运行不导入 Adapter 的单元和静态检查，但不能把宿主渲染结果作为验收证据。

使用锁文件和镜像验证相同生成身份的字节稳定性、URL 拒绝与迁移：

```bash
docker compose --profile test build test
docker compose --profile test run --rm test \
  pytest tests/integration/test_resume_pdf_renderer.py \
    tests/integration/test_resume_pdf_migration.py \
    tests/integration/test_decision_report_api.py -q
```

渲染器不读取用户 HTML、脚本、本地文件或网络资源；不要在容器外安装替代字体后更新基线哈希。生成的 PDF 属于运行时
私有 Artifact，不提交到 Git。

### 镜像版本升级与回滚

Dockerfile 和 Compose 中的 Python、uv、PostgreSQL 与 MinIO 镜像均固定到 manifest digest；Python、uv 和
PostgreSQL 同时保留可读版本标签。容器构建门禁（CI `containers` job）只依赖 Docker 构建上下文，不要求
Runner 或开发宿主预装 Python、uv；后端 `quality` job 则通过 `actions/setup-python` 与 `astral-sh/setup-uv`
在运行时按需安装，同样不依赖预装环境。

升级镜像时，先选择上游明确版本标签并查询多架构 manifest digest：

```bash
docker buildx imagetools inspect <image>:<version> --format '{{json .Manifest.Digest}}'
```

在同一个 PR 中更新全部重复引用，尤其是 PostgreSQL 在 `docker-compose.yml`、`docker-compose.override.yml` 和
`.github/workflows/pr-conventions.yml` 中的 digest，以及 uv 在 `docker/Dockerfile.api` 和
`.github/workflows/pr-conventions.yml` 中的版本标签与 digest。然后从仓库根目录执行完整解析和重建：

```bash
docker compose --profile test config --quiet
docker compose --profile test build --no-cache api tools test
docker build --no-cache --file docker/Dockerfile.api --target runtime --tag nora-api-runtime:verify .
docker compose --profile test run --rm test
docker compose up -d db api
docker compose exec api alembic upgrade head
curl --fail http://localhost:8000/ready
```

这些 CI 构建命令只解析配置和构建镜像，不启动 Compose 服务，也不会创建或写入 PostgreSQL、MinIO 命名卷。人工健康
检查才会启动 `db` 和 `api`；不要使用 `docker compose down -v`，除非明确要删除本地数据。

镜像升级需要回滚时，使用 `git revert <image-update-commit>` 恢复上一组已审查 digest，再执行同一套完整重建和健康检查。
不要只修改本地镜像标签或单个重复引用，否则开发环境与 CI 会使用不同镜像。

### 缓存目录

容器内运行 Python 与质量工具时，所有后端项目缓存统一写入 `backend/.cache/`：

- Python 字节码：`backend/.cache/pycache/`
- pytest：`backend/.cache/pytest/`
- mypy：`backend/.cache/mypy/`
- ruff：`backend/.cache/ruff/`

`.cache/` 已同时从 Git 和 Docker 构建上下文排除。源码、测试、Alembic 与脚本目录不应再生成
`__pycache__/`，仓库根目录也不应再出现 `.pytest_cache/`、`.mypy_cache/` 或 `.ruff_cache/`。

### 启用提交前门禁

仓库在 `.githooks/pre-commit` 提供受版本控制的 Git hook。新克隆仓库只需执行一次：

```bash
git config core.hooksPath .githooks
```

此 hook 通过一个 Compose `tools` 容器依次执行 ruff 格式检查、ruff lint、mypy，以及单元和架构测试；
宿主仍只需要 Git、Docker 与 Docker Compose，不需要 Python 或 pre-commit 包。手动验证 hook：

```bash
.githooks/pre-commit
```

检查失败时 Git 会中止 Commit。修复问题后重新提交；不要使用 `--no-verify` 绕过项目门禁。

### Codex 自动审核（宿主工具）

PR 的 Codex 自动审核（`.codex/skills/nora-pr-review`）由 **Codex 应用自身**完成审核，**不启动浏览器、不需要 API Key 或
session token**，只依赖宿主 Python 标准库与 `gh` CLI。审核 prompt 与回复只保存在宿主临时目录，不进入仓库工作树。

运行自动审核（两阶段）：

```bash
# 阶段 1：生成审核指令（含 PR diff、判定标准、输出格式）
python .codex/skills/nora-pr-review/scripts/nora_review.py --prepare --pr <PR 编号>

# 阶段 2：Codex 阅读指令并产出结论（保存为 reply-<PR>.md）后，解析并发布 PR Review
python .codex/skills/nora-pr-review/scripts/nora_review.py --submit --pr <PR 编号>
```

调试开关：`--no-post`（submit 时渲染 review body 但不发布）、`--force`（覆盖已存在同作者 Review）、`--reply-file`
（指定回复文件位置）、`--output-dir`（指定中间产物目录）。

## 依赖管理

运行时依赖和开发依赖均通过 development 容器内的 uv 管理：

```bash
docker compose run --rm --no-deps tools uv add package-name
docker compose run --rm --no-deps tools uv add --dev package-name
docker compose run --rm --no-deps tools uv remove package-name
docker compose run --rm --no-deps tools uv lock
docker compose build api
```

提交依赖变更时必须同时提交 `backend/pyproject.toml` 和 `backend/uv.lock`。不要提交 `.env`、`.venv`、`dist` 或其他本地产物。

## 路径与挂载规则

- 推荐工作区：`/home/<user>/projects/Nora`。
- Compose bind mount 的源路径来自 WSL 当前目录，不使用 `C:\...` 或 `D:\...`。
- 不要在 PowerShell 中进入 WSL 工作区后调用另一套 Docker context。
- `.env` 只在 WSL 工作区根目录创建；模板是 `backend/.env.example`。
- Docker 命名卷保存数据库和 MinIO 数据，不写入仓库目录。

## 故障排查

### Docker daemon 未运行

确认 Windows 中 Docker Desktop 已启动，并且目标 Ubuntu 发行版的 WSL Integration 已启用。然后在 WSL 验证：

```bash
docker context show
docker info
```

### 端口已被占用

检查端口：

```bash
ss -ltnp | grep -E ':8000|:5432|:9000|:9001'
```

修改 `.env` 中的 `API_PORT`、`POSTGRES_PORT`、`STORAGE_PORT` 或 `STORAGE_CONSOLE_PORT` 后重建服务：

```bash
docker compose down
docker compose up --build
```

### API 无法连接数据库

先检查数据库健康状态和 API 环境变量：

```bash
docker compose ps db api
docker compose logs db
docker compose exec api printenv DATABASE_URL
```

容器内数据库主机必须是 `db`，不能写 `localhost`。等待 `db` 通过 healthcheck 后再启动 API。

### 修改代码后没有重载

确认仓库位于 WSL Linux 文件系统，并检查挂载：

```bash
docker compose config
docker compose exec api pwd
docker compose logs api
```

如果仓库位于 `/mnt/c` 或 `/mnt/d`，迁移到 `$HOME/projects/Nora` 后重新执行 `docker compose up --build`。

### 清理后重新初始化

以下操作会删除本地数据库和 MinIO 数据，不可恢复：

```bash
docker compose down -v
docker compose up --build
```

## 当前边界

本指南只说明开发和运行方法，不维护功能完成清单。当前可运行能力、逐项代码路径与合并证据只以
[`current-capabilities.toml`](current-capabilities.toml) 为准；不要把本指南或路线图中的目标、示例和环境骨架当作当前能力。
