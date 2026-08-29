# Nora 开发指南

> 本指南以 macOS 15.7.9 + zsh + OrbStack 为推荐的本地开发环境。
> Git、Docker 和 Docker Compose 命令在 macOS Terminal 中执行；API、Web、Python、uv、Alembic 和质量工具在宿主机运行，IDE 可直接附加断点。

## 环境边界

本地开发使用以下边界：

```text
macOS 15.7.9
  ├─ OrbStack：Docker Engine + Docker Compose
  ├─ zsh + Git + Docker CLI
  ├─ Python 3.11 + uv + Node.js 24 + npm
  └─ 项目代码：~/Projects/Nora
```

OrbStack 必须处于运行状态；不要同时启动另一套 Docker Engine 或切换到其他 Docker context。

## 前置条件

### macOS 一次性准备

使用 Homebrew 安装宿主开发工具和 OrbStack：

```bash
brew install python@3.11 uv node@24 git
brew install --cask orbstack
```

打开 OrbStack 后，Docker CLI 与 Compose 会自动使用 OrbStack context。验证宿主工具：

```bash
docker version
docker compose version
git --version
python3.11 --version
uv --version
node --version
npm --version
```

## 获取代码

建议把仓库放在 macOS 本地磁盘（例如 `~/Projects`）中，避免网络盘或外置慢速卷导致文件监听和 I/O 性能问题。

```bash
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
git clone https://github.com/dev-cai/Nora.git
cd Nora
```

## 快速开始

以下命令均在 macOS zsh 的仓库根目录执行：

```bash
cd "$HOME/Projects/Nora"
cp backend/.env.example backend/.env
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init

cd backend
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.apps.api:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

另开终端启动前端：

```bash
cd "$HOME/projects/Nora/frontend"
npm ci
npm run dev
```

开发 Compose 只启动 PostgreSQL、MinIO 和一次性 `storage-init`；API/Web 由宿主进程运行，因此 IDE 可直接设置断点和单步调试。

另开一个 macOS Terminal 验证：

```bash
cd "$HOME/projects/Nora"
curl http://localhost:8000/live
curl --fail http://localhost:8000/ready
curl http://localhost:5173
docker compose -f docker-compose.dev.yml ps
```

首次启动和拉取到新迁移后都要在 `backend/` 执行 `uv run alembic upgrade head`。API 不会在启动时自动修改数据库结构。

API 进程存活时 `/live` 返回：

```json
{"status":"live"}
```

`/live` 不检查外部依赖。PostgreSQL 可连接且 `SELECT 1` 成功时 `/ready` 返回 `200` 与
`{"status":"ready"}`；未配置、连接失败、查询失败或超时时返回 `503` 与
`{"status":"not_ready","database":"unavailable"}`。生产环境还要求私有 Artifact Bucket 可访问；对象存储失败或超时返回
`503` 与 `{"status":"not_ready","artifact_storage":"unavailable"}`，响应不包含 endpoint、Bucket、对象键或凭据。

## 环境变量与 Compose 对照

`backend/.env.example` 是可公开提交的本地开发模板。宿主 API 从 `backend/.env` 读取它；开发 Compose 的变量通过仓库根目录
`.env`（如需覆盖默认值可从模板复制）执行 `${VARIABLE:-default}` 插值。根 `.env` 不会被整体注入容器，只有 Compose
`environment` 中明确列出的值才会进入对应进程。不要在模板中填写真实值，也不要提交任何 `.env` 文件。

宿主 API 必须使用 `localhost` 地址，例如 `DATABASE_URL=postgresql+asyncpg://nora:change-me-local@localhost:5432/nora`
和 `ARTIFACT_STORAGE_ENDPOINT=localhost:9000`；容器间连接才使用 `db`、`storage` 服务名。

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
| `AUTH_ACCESS_TOKEN_MINUTES` | `30` | Compose 注入 API；Settings 允许 `1`–`30` | 控制访问令牌有效期，不是密钥；生产上限为 30 分钟 |
| `AUTH_KEY_RING_DIRECTORY` | 空（开发使用 `AUTH_SECRET_KEY`） | 生产 API 的 root-owned JWT key ring 目录 | 文件名是 `kid`，每个文件至少 32 bytes；不得放入仓库或命令参数 |
| `AUTH_ACTIVE_KID` | `dev` | API 当前签发 key 的安全标识 | 只能使用 `[A-Za-z0-9._-]{1,64}`，必须存在于 key ring |
| `AUTH_RATE_LIMIT_SECRET` | 开发专用示例值 | API PostgreSQL 限额桶 HMAC 真源 | 生产必须替换，且不得与任何 JWT key 相同；原始用户名、邮箱和 IP 不落库 |
| `PUBLIC_ORIGIN` | 空（开发允许通配 CORS） | 生产唯一浏览器 HTTPS Origin | 禁止 wildcard、`null`、HTTP、路径、查询、片段和正则 |
| `TRUSTED_PROXY_CIDR` | 空（开发直连 peer） | 开发/测试 API 配置；#224 目标生产值由 Compose 固定为 Web IP `/32` | 生产不接受 operator 配置或整个 edge subnet；只接受固定 Web peer 转发的单个 `X-Forwarded-For` 与 `https`，拒绝 chain |
| `BAIDU_OCR_API_KEY` | 空 | API / Settings（百度智能云 OCR 应用凭据） | 生产环境必须配置且不得提交；未配置时 OCR 接口返回稳定 `ocr_failed` |
| `BAIDU_OCR_SECRET_KEY` | 空 | API / Settings（百度智能云 OCR 应用凭据） | 生产环境必须配置且不得提交；与 API Key 成对 |
| `BAIDU_OCR_ENDPOINT` | `accurate_basic` | API / Settings | 百度 OCR 接口名，如 `general_basic` / `accurate_basic` |
| `DEEPSEEK_API_KEY` | 空 | 显式模型 smoke / Settings | DeepSeek API Key；不得提交、记录或传入命令参数，未配置不影响确定性流程 |
| `DEEPSEEK_API_KEY_FILE` | 空 | Settings 的受控 Secret 文件入口 | 与直接值互斥；必须是绝对路径、非 symlink、1-16384 bytes 且 group 不可写、others 不可访问 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek Chat Adapter | 固定值，不允许切换 endpoint 或协议；Adapter 请求 `/v1/chat/completions` |
| `DEEPSEEK_CHAT_MODEL` | `deepseek-v4-flash` | DeepSeek Chat Adapter / JD Import / JobFit 身份 | 进程启动时读取的单一 Chat 模型标识；修改后重新启动，不能按请求动态路由 |
| `DEEPSEEK_CHAT_TIMEOUT_SECONDS` | `60` | DeepSeek Chat Adapter | 单次调用总墙钟允许 `(0, 60]` 秒；timeout 最多重试一次后返回稳定失败 |
| `EMBEDDING_API_KEY` | 空 | Qwen Embedding Adapter / 显式动态评测 | 阿里云百炼 Embedding Key；不得提交、记录或传入命令参数，未配置时稳定失败 |
| `EMBEDDING_API_KEY_FILE` | 空 | Settings 的受控 Embedding Secret 文件入口 | 与直接值互斥；绝对路径、非 symlink、1-16384 bytes 且 group 不可写、others 不可访问 |
| `EMBEDDING_WORKSPACE_ID` | 空 | Qwen Embedding Adapter | 北京地域业务空间 ID；固定拼接官方 compatible embeddings endpoint |
| `EMBEDDING_TIMEOUT_SECONDS` | `60` | Qwen Embedding Adapter | 单次调用总墙钟允许 `(0, 60]` 秒；timeout 最多重试一次后返回稳定失败 |
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
| `ARTIFACT_BACKUP_ACCESS_KEY` | `nora-backup` | `storage-init` 创建、备份入口读取 | 仅允许列出目标 Bucket 并读取对象，不能写入或删除 |
| `ARTIFACT_BACKUP_SECRET_KEY` | `development-backup-secret` | `storage-init` 与备份入口 | 公开值仅限本地；不得与 MinIO root 或应用身份复用 |
| `ARTIFACT_STORAGE_BUCKET` | `nora-artifacts` | `storage-init` 与 API / Settings | Bucket 保持私有，不提供匿名或长期签名 URL |
| `ARTIFACT_STORAGE_ENDPOINT` | Compose 固定 `storage:9000`；模板为 `localhost:9000` | API / Settings | 使用 `host:port`，不得包含 scheme 或路径 |
| `ARTIFACT_STORAGE_SECURE` | Compose 与模板为 `false` | API / Settings | Beta/生产按 #171 的 TLS 边界配置 |

### 内部派生值

以下是容器内部派生值，不属于根 `.env` 的用户配置面；宿主 API 使用的 `DATABASE_URL` 已在 `backend/.env.example` 中单独提供：

| 变量 | 来源和有效值 | 作用域 |
|------|--------------|--------|
| `DATABASE_URL` | Compose 使用 `POSTGRES_USER`、`POSTGRES_PASSWORD` 和 `POSTGRES_DB` 生成 `postgresql+asyncpg://<user>:<password>@db:5432/<database>` | API runtime 容器 / Settings；必须使用 `postgresql+asyncpg` |
| `TEST_DATABASE_URL` | test profile 使用隔离测试库 `postgresql+asyncpg://nora_test:nora_test@test-db:5432/nora_test` | 宿主集成测试通过 `localhost:5433` 覆盖；不连接开发数据卷 |
| `PYTHONPYCACHEPREFIX` | 容器 runtime 可按需设置 | Python 字节码缓存路径，不属于 Compose 配置面 |

容器内服务发现使用 Compose 服务名：API 连接 PostgreSQL 时主机是 `db`，测试容器连接 `test-db`。从 macOS 宿主
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

### Beta owner 管理

生产不开放 `POST /auth/register`。唯一 owner 必须在维护窗口通过不提供 HTTP 路由的管理命令创建或恢复；用户名、邮箱和密码分别从
只允许 owner 管理命令所属 consumer group 读取的 `root:10001`/`0440` 非 symlink Secret 文件读取，不能写入命令参数、Shell
history、日志或 Compose 配置：

```bash
docker compose -f deploy/compose.production.yml exec api nora-identity bootstrap-owner \
  --request-id bootstrap-2026-08-15 \
  --username-file /run/secrets/nora-owner-username \
  --email-file /run/secrets/nora-owner-email \
  --password-file /run/secrets/nora-owner-password
```

恢复凭据使用 `recover-owner`，成功会递增 `session_version` 并立即使旧 Bearer Token 失效。命令只输出稳定状态、request ID、user ID
和 session version；同一 request identity 重放不会重复开户或恢复。PostgreSQL 限额桶、唯一 owner 槽和审计事件在同一事务边界内维护。
生产 `/ready` 只有数据库可用、恰好一个 active owner 且该 owner 被 singleton 槽追踪时返回 ready；空库、多用户或槽损坏均 fail closed。

认证安全事件以 JSON 日志中的 `metric_name=nora_security_events_total`、`metric_value=1` 输出。日志聚合只把固定的
`security_signal`、`result`、`reason` 和 `trusted_proxy` 作为低基数标签；request ID、`key_id`、session version、Retry-After 和
key count 只用于定位，不作为指标标签，也不得加入用户名、邮箱、原始 IP、密码、hash、Token 或 Secret。单次普通登录失败不告警；
任一 `authentication_rate_limited` 已代表 5/20/30 次窗口阈值被触发，应进入告警候选；`origin_rejected` 在 5 分钟内累计 5 次进入
告警候选。Identity 集成测试用 31 次合成认证请求、拒绝预检和并发 bootstrap 验证信号前置条件，目标 Beta 的采集与告警规则由 #138
接入部署日志管道。

### Artifact 与 Source 本地验证

`storage-init` 使用 MinIO root 凭据完成受控初始化；API 容器只收到最小权限应用凭据。上传返回的公开元数据不包含 Bucket、
对象键或凭据，下载经认证 API 代理并设置安全响应头。运行真实 Adapter 合约测试：

```bash
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
cd backend
TEST_ARTIFACT_STORAGE_ENDPOINT=localhost:9000 \
TEST_ARTIFACT_STORAGE_ACCESS_KEY=nora-app \
TEST_ARTIFACT_STORAGE_SECRET_KEY=development-artifact-secret \
TEST_ARTIFACT_STORAGE_BUCKET=nora-artifacts \
  uv run pytest tests/integration/test_minio_artifact_storage.py -q
```

数据库迁移继续使用 `alembic upgrade head`；#21 的 `0014_artifacts_sources` 支持降级后重新升级。不要使用 MinIO Console
或对象存在性判断业务状态，PostgreSQL 中的 Artifact 生命周期始终是唯一事实源。

如需覆盖这些 Settings-only 值，应在受审查的 Compose environment 或进程环境中显式提供；只把它们写进仓库根 `.env`
不会自动注入 API。Beta 的秘密管理、单主机 Compose 拓扑和发布边界由 [`ARCHITECTURE.md`](ARCHITECTURE.md)
的 D-019 定义；本节公开示例值和本地端口不得用于 Beta。

### 对照验证

在 macOS zsh 仓库根目录运行以下检查，确认开发依赖和 runtime/release Compose 均可解析。`backend/.env.example` 还包含宿主 API
专用的 `DATABASE_URL`、Provider 配置，以及仅用于本地端口/项目名的变量；这些变量不要求出现在两份 Compose 文件中。

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.dev.yml --profile test config --quiet
```

检查成功时命令退出码为 `0`。`docker compose config` 的完整渲染结果可能包含本地密码，排障时只在
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
`ENV=prod` 时必须提供至少 32 字节的随机值，否则应用拒绝启动。例如可在 macOS 中生成：

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

停止开发依赖但保留数据卷：

```bash
docker compose -f docker-compose.dev.yml stop
docker compose -f docker-compose.dev.yml down
```

删除容器和本地数据库/MinIO 数据：

```bash
docker compose -f docker-compose.dev.yml down -v
```

## 日常操作

### 前端开发与质量检查

前端使用 Node.js 24、npm、Vue 3、Vite、TypeScript、Vue Router 和 Pinia。Node 版本单一真源为
`frontend/.nvmrc`（当前 24.18.1），配合 `frontend/.npmrc` 的 `engine-strict=true` 作为硬门禁；CI 通过
`node-version-file: frontend/.nvmrc` 读取同一版本。宿主运行时 Vite 默认将 `/api` 代理到 `http://localhost:8000`。可在
`frontend/.env` 中通过 `VITE_NORA_API_BASE_URL` 覆盖浏览器 API 基础路径，或通过
`VITE_NORA_PROXY_TARGET` 覆盖 Vite 开发代理目标。不要在这些变量中写入 Token 或其他秘密。

宿主机开发（API/Web 可由 IDE 直接调试）：

```bash
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
cd backend
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.apps.api:create_app --factory --host 0.0.0.0 --port 8000 --reload

# 另一个终端
cd frontend
npm ci
npm run dev
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

查看依赖容器日志（API 日志直接显示在 uvicorn 终端）：

```bash
docker compose -f docker-compose.dev.yml logs -f
```

### 浏览器级真实 Compose E2E

浏览器 E2E 已暂停并从仓库移除。当前本地和 CI 不提供 Playwright 命令、浏览器用例、E2E Compose 或生产安全浏览器门禁。
跨 API 流程改由后端集成测试、前端组件测试和 API smoke 覆盖；重新引入浏览器门禁需要独立 Issue、契约更新和稳定的测试流程。

### 请求关联标识

API 为每个请求维护 `request_id` 结构化日志字段，用于定位单次 HTTP 请求的响应和日志。

客户端可以通过 `X-Request-ID` 传入标识。缺失时服务端生成 UUID，并通过同名响应头回传。
传入值必须为 1–128 位，只能包含 ASCII 字母、数字、点、下划线和连字符，且首位必须是字母或数字；非法值返回
`400` 和稳定错误码 `invalid_correlation_id`，该错误响应仍携带服务端生成的有效 `X-Request-ID`。标识不得包含 Token、
Cookie、请求正文、邮箱或其他个人数据。

`X-Trace-ID` 不属于当前契约：服务端忽略调用方传入值，也不生成、记录或回传伪 Trace ID。排障时从响应头取得
`X-Request-ID` 定位单次请求；请求结束后服务端会清理字段，避免上下文泄漏到后续请求。

### 日志派生请求与业务指标

API 为每个完成或被拒绝的请求输出两条 JSON 指标记录：

- `nora_http_requests_total`：`metric_value=1`，用于吞吐与错误率计数；
- `nora_http_request_duration_seconds`：`metric_value` 为本次请求耗时秒数，用于延迟分布。

两者只聚合 `http_method`、`http_route`、`status_class` 和 `result`。`http_route` 是 FastAPI 静态路由模板；未匹配或路由解析前拒绝统一为 `_unmatched`，不会记录原始 URL、path 参数或 query。`request_id` 只用于从指标定位同一次请求的日志和错误，不作为指标标签。

分析、报告生成、Artifact 上传/删除、PDF 生成和 ApplicationRecord 创建/转换还输出
`nora_business_operations_total`，固定维度为 `business_operation` 与 `result`。这些记录不包含用户 ID、业务对象 ID、Token、Cookie、简历/JD/PDF 正文、签名 URL、Prompt、异常堆栈或 Trace ID。

本地可从 API JSON 日志中过滤全部日志派生指标：

```bash
# API 日志在运行 uvicorn 的终端；依赖容器日志可用：
docker compose -f docker-compose.dev.yml logs db storage
```

当前仓库只定义可采集信号；部署日志管道、聚合规则和告警由 #138 接入。

查看依赖容器状态和资源：

```bash
docker compose -f docker-compose.dev.yml ps
docker stats
```

修改 `backend/app/` 后，宿主机 Uvicorn `--reload` 会自动重载 API；IDE 调试时可改用调试器启动同一应用工厂。

执行数据库迁移（宿主 `backend/`）：

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic history
```

连接 PostgreSQL：

```bash
docker compose -f docker-compose.dev.yml exec db psql -U nora -d nora
```

## 本地测试与质量检查

开发依赖安装在宿主机 `backend/.venv`。静态检查、单元测试和架构测试不需要启动依赖服务：

```bash
cd backend
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy app/
uv run pytest tests/unit tests/architecture -q
```

### DeepSeek 结构化输出动态 smoke

普通 CI 只运行 Fake/Recorded 测试，不读取真实 Provider Secret。需要验证 DeepSeek 的真实调用时，在受控 shell 中通过环境变量
或权限受限的绝对 Secret 文件显式注入 Key，并同时设置运行开关：

```bash
cd backend
NORA_RUN_DEEPSEEK_SMOKE=1 \
DEEPSEEK_API_KEY_FILE=/absolute/path/to/deepseek-api-key \
.venv/bin/pytest tests/smoke/test_deepseek_model.py -q
```

未设置 `NORA_RUN_DEEPSEEK_SMOKE=1` 时该测试报告 skipped；设置开关但缺少 Key 时明确失败。Smoke 使用固定
`deepseek-v4-flash`、JSON mode 和本地 Pydantic Schema 校验及无敏感探测内容，不写数据库或其他业务事实。不要把真实 Key 放入 `.env`、命令参数、测试输出或
仓库；费用预警/额度必须先在 DeepSeek 控制台配置。

### Qwen Embedding RAG 动态评测

普通 CI 只运行 deterministic 基线与 MockTransport 契约测试。真实评测必须在受控 shell 提供独立的
`EMBEDDING_API_KEY`（或 `EMBEDDING_API_KEY_FILE`）及北京地域 `EMBEDDING_WORKSPACE_ID`，然后执行：

```bash
backend/.venv/bin/python backend/scripts/rag_eval.py \
  --embedding-provider real \
  --output /tmp/rag_eval_v1.qwen.results.json
```

缺少任一凭据时输出 `not run`，不得将 deterministic 结果冒充真实质量证据。评测输出记录 Provider/model/version/dimension、
vector 与冻结 RRF Hybrid 指标、延迟和估算成本；真实评测未达到冻结门槛前，线上不得切换 Embedding。

集成测试只连接 `docker-compose.dev.yml` 的 `test` profile 中的隔离 PostgreSQL。`test-db` 使用 tmpfs，不复用开发数据库或命名卷：

```bash
docker compose -f docker-compose.dev.yml --profile test up -d test-db
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://nora_test:nora_test@localhost:5433/nora_test \
  uv run pytest tests/unit tests/integration tests/architecture -q
docker compose -f docker-compose.dev.yml --profile test stop test-db
```

集成测试要求 `TEST_DATABASE_URL` 或 `DATABASE_URL` 使用 `postgresql+asyncpg`。缺少连接或使用其他驱动时，
测试会明确失败；项目不支持 SQLite 回退。

### 确定性 PDF 渲染环境

PDF 渲染只以 `docker/Dockerfile.api` 构建的锁定 Linux 环境为可复现基线：Python 依赖锁定 WeasyPrint 69.x，系统包固定
Pango 1.56.3 与 Noto CJK 20240730，镜像和 Adapter 固定 `SOURCE_DATE_EPOCH=1767225600`。渲染器版本同时记录
WeasyPrint、Pango、Adapter 和 SOURCE_DATE_EPOCH，字体集另有独立版本；升级任一输入都必须形成新的生成身份并重新执行
确定性测试。宿主缺少 Pango 时可以运行不导入 Adapter 的单元和静态检查，但不能把宿主渲染结果作为验收证据。

使用锁文件和 runtime 镜像验证相同生成身份的字节稳定性、URL 拒绝与迁移（需要在镜像中执行时，使用 CI 或临时 `docker run`）：

```bash
cd backend
uv run pytest tests/integration/test_resume_pdf_renderer.py \
  tests/integration/test_resume_pdf_migration.py \
  tests/integration/test_decision_report_api.py -q
```

渲染器不读取用户 HTML、脚本、本地文件或网络资源；不要在容器外安装替代字体后更新基线哈希。生成的 PDF 属于运行时
私有 Artifact，不提交到 Git。

### 镜像版本升级与回滚

Dockerfile 和 Compose 中的 Python、uv、PostgreSQL 与 MinIO 镜像均固定到 manifest digest；Python、uv 和
PostgreSQL 同时保留可读版本标签。API Dockerfile 还固定 Debian 安全补丁包版本，避免基础镜像更新窗口中的已修复
HIGH/Critical 漏洞重新进入运行时。容器构建门禁（CI `containers` job）只依赖 Docker 构建上下文；后端 `quality` job
在 CI 中通过 `actions/setup-python` 与 `astral-sh/setup-uv` 安装并锁定工具。

升级镜像时，先选择上游明确版本标签并查询多架构 manifest digest：

```bash
docker buildx imagetools inspect <image>:<version> --format '{{json .Manifest.Digest}}'
```

在同一个 PR 中更新全部重复引用，尤其是 PostgreSQL 在 `docker-compose.yml`、`docker-compose.dev.yml` 和
`.github/workflows/pr-conventions.yml` 中的 digest，以及 uv 在 `docker/Dockerfile.api` 和
`.github/workflows/pr-conventions.yml` 中的版本标签与 digest。然后从仓库根目录执行完整解析和重建：

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.dev.yml --profile test config --quiet
docker build --no-cache --file docker/Dockerfile.api --target runtime --tag nora-api-runtime:verify .
docker build --no-cache --file docker/Dockerfile.web --target runtime --tag nora-web-runtime:verify .
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
cd backend && uv run alembic upgrade head
curl --fail http://localhost:8000/ready
```

这些 CI 构建命令只解析配置和构建镜像，不启动 Compose 服务，也不会创建或写入 PostgreSQL、MinIO 命名卷。人工健康
检查才会启动 `db` 和 `api`；不要使用 `docker compose down -v`，除非明确要删除本地数据。

镜像升级需要回滚时，使用 `git revert <image-update-commit>` 恢复上一组已审查 digest，再执行同一套完整重建和健康检查。
不要只修改本地镜像标签或单个重复引用，否则开发环境与 CI 会使用不同镜像。

### Beta 单主机生产基线

Issue #224 已把 D-019 的唯一目标生产拓扑收敛为 `Host Reverse Proxy/TLS -> 127.0.0.1:${NORA_WEB_PORT} -> Web -> API`。Host Proxy 是
产品无关的宿主职责，拥有公网 `80/443`、TLS、HTTP 到 HTTPS、HSTS 和 forwarded header 覆盖；Nora Compose 只允许 Web 发布
`127.0.0.1` HTTP 端口，API、PostgreSQL 和 MinIO 不发布宿主端口。Web 固定内部 IP并负责静态/SPA、`/api` proxy 与 CSP/XFO/
Referrer/`nosniff`，API 只信任该 Web IP `/32`。

[`deploy/compose.production.yml`](../deploy/compose.production.yml) 已实现该唯一拓扑：Web 固定使用 `172.28.0.10` 并只发布
`127.0.0.1:${NORA_WEB_PORT}:5173`，API 的 `TRUSTED_PROXY_CIDR` 固定为 `172.28.0.10/32`，data network 为 internal。production
runtime 不包含 Caddy、ingress、80/443 映射或旧拓扑兼容开关；Host Proxy 不得绕过 Web 直接访问 API。

复制 [`deploy/production.env.example`](../deploy/production.env.example) 到主机私有位置后，必须填写真实 provider、region、唯一
HTTPS `NORA_PUBLIC_ORIGIN`、`1024..65535` 的 `NORA_WEB_PORT`、月度预算、告警阈值、跨故障域备份目的地标识和完整
`image@sha256:<digest>`。示例中的 `UNSET`、示例域名和零 digest 只用于
`docker compose config`，不能部署或作为 Beta 证据。自动发布由下述唯一 GitHub Actions 管道消费同一 env 和 Compose 契约。

生产 Secret 事实源是 root-owned 主机目录。API、迁移与 MinIO/备份 Secret 使用 `root:10001`、PostgreSQL 初始化密码使用 `root:70`，
文件权限固定 `0440`；JWT key ring 目录为 `root:10001`/`0750`，其中每个 key 为 `0440`。Secret 文件必须是绝对路径、常规文件、
非 symlink、UTF-8 且不超过 16 KiB。`DATABASE_URL_FILE`、`AUTH_RATE_LIMIT_SECRET_FILE`、Artifact 应用凭据文件和 JWT key ring
只挂载到消费者；Compose、命令参数和日志中不出现值。API 的 `DATABASE_URL_FILE` 必须使用 `nora_app` 等非 superuser 应用身份，
并与 PostgreSQL 初始化密码、迁移管理 URL 使用不同文件和凭据。数据目录的 owner 分别为 PostgreSQL `70:70`、其余 runtime
`10001:10001`，且不得对 other 开放。

`migration` 只读取管理 URL 并执行 Alembic；随后 `db-init` 创建/轮换非 superuser、非 createdb/createrole 的应用身份，并授予 Nora
Schema 现有及后续表/序列所需的 DML 权限。API 不接收 PostgreSQL 初始化或迁移身份。`storage-init` 同样只在初始化 profile 使用
MinIO root，分别创建 Bucket 读写删应用身份和只读备份身份；API 与备份入口均不接收 MinIO root。

`preflight.py` 会 fail closed：拒绝 mutable tag、环境文件中的直接 Secret、非法或重复变量名、示例目标信息、非法 HTTPS
`NORA_PUBLIC_ORIGIN`、非法 `NORA_WEB_PORT`、重复/相对数据或 Secret 路径，以及 owner、group、mode 不正确的 Secret 或数据目录。
root operator 脚本不 source env 文件，只通过 preflight 的字段白名单读取所需非 Secret 值。Web bind 与 API 可信 `/32` 是 Compose
内部事实，不能由 production env 放宽。首次启动后使用已有 `nora-identity bootstrap-owner` 管理命令建立唯一 owner，再验证
`/live`、`/ready`、Web `/api` 同源调用、容器 UID、`CapEff`、只读根文件系统、只有 localhost Web published port，以及 API/DB/MinIO
无宿主端口。生产 `/ready` 必须同时验证唯一 owner、PostgreSQL 与 Artifact Storage；不得以 `/live` 或 MinIO 进程存活替代就绪。

#### Beta 自动发布与回滚

`.github/workflows/beta-deploy.yml` 是 D-019 的唯一正常发布控制面，只接受手工 `workflow_dispatch`。`deploy` 操作要求完整
`main` Commit SHA，重新核对该 Commit 通过 `deploy/release_manifest.py::REQUIRED_CI_CHECKS` 定义的全部 required checks 后构建并推送
API/Web GHCR digest、生成 SPDX SBOM、发布 GitHub provenance/SBOM attestation，并生成不可变 release manifest。`rollback`
只接受已记录的健康 release ID 和非空原因。工作流使用 `beta-deployment` 单并发锁；实际部署与回滚 Job 还必须经过受保护
`beta` Environment，并只运行在 `[self-hosted, linux, x64, nora-beta-deploy]` 专用 Runner 上。
构建前还会回读 GitHub 元数据，要求 Environment 存在、至少一个 required reviewer、仅允许受保护分支且关闭管理员绕过，并要求
至少一个带完整标签的专用 Runner 在线；缺少任一条件即 fail closed，不允许 GitHub 静默创建无保护 Environment。读取 Environment
保护规则和 Runner 列表要求 Administration 只读权限，`GITHUB_TOKEN` 不能通过 workflow `permissions:` 获得该权限；`verify` Job
改用仓库 Secret `RELEASE_CONTROL_TOKEN`（限定该仓库 Administration:read 的 fine-grained PAT），只在该 Secret 缺失时才回落到
`GITHUB_TOKEN` 供本地/手工调用；该 Token 只用于只读校验，不写入镜像层、Compose 文件或日志。

主机供应完成后，operator 从已验证的 `main` checkout 安装 root-owned 固定入口，并确认专用 Runner 用户没有登录 Shell、Docker
管理权限或运行时 Secret 读取权：

```bash
sudo deploy/install_release_entrypoint.sh nora-deploy
sudo stat -c '%U:%G %a %n' /usr/local/sbin/nora-release /opt/nora/deploy/release.py
sudo visudo -cf /etc/sudoers.d/nora-release
```

安装脚本只把经审查的发布、preflight、public smoke、backup 与 Compose 文件复制到 `/opt/nora/deploy`，固定入口为
`/usr/local/sbin/nora-release`，状态目录为 `/var/lib/nora/releases`。Runner 通过 stdin 提供当前 Job 的短期 GHCR Token；root
入口验证 manifest、SBOM 哈希、Schema 兼容策略哈希、主干 check run ID 和 GitHub attestation 后立即登录拉取，结束时 logout。
GitHub Environment 不保存数据库、MinIO、JWT、owner 密码或备份解密材料。

目标发布固定记录 `preflight -> backup -> pull -> migrate -> start -> internal-smoke -> public-smoke -> promote`。无 Schema 变化时 backup
明确记录为 skipped；迁移前失败不改写生产 env 或 `last-healthy.json`。`migrate` 阶段依次执行 Alembic 迁移、`db-init` 与
`storage-init`：迁移先建好表，`db-init` 再用 admin 身份幂等创建/更新最小权限 PostgreSQL 运行时角色并授予表与序列权限，
`storage-init` 幂等创建私有 Artifact Bucket 与最小权限对象存储身份；三者都幂等，每次发布都会重新执行，首次部署无需 operator 手工
初始化数据库角色或 Bucket。迁移停止 Web/API、保持 PostgreSQL/MinIO 运行；候选服务先完成
内部 API/Web/Artifact smoke，再通过真实 `NORA_PUBLIC_ORIGIN`、正常 TLS 校验验证 Web、`/api/live`、`/api/ready`、应用安全 headers、
Host Proxy HSTS 与 Web API proxy 链标记。只有 public smoke 全部通过才能替换 production env 和写健康指针；禁止 `--insecure`。

自动回滚不会执行 Alembic downgrade。同一 Schema revision 可回退到已知健康镜像；跨 revision 只有当前 Commit 中
`deploy/schema-compatibility.json` 明确允许且其哈希已进入 manifest 时，候选失败才可自动回退。恢复旧版本后仍必须重新通过
internal smoke 和 public smoke，之后才可更新 env/指针并记录 rollback healthy；无安全回滚条件或恢复 smoke 失败时停止 Web/API 并
保持维护态。其他迁移后失败由 operator 先取消 workflow、取得同一 Environment/主机锁并使用联合恢复流程。人工镜像回滚仍调用同一入口：

```bash
gh workflow run beta-deploy.yml \
  -f operation=deploy -f commit_sha=<完整 main SHA>
gh workflow run beta-deploy.yml \
  -f operation=rollback -f rollback_release_id=<release-id> \
  -f rollback_reason='operator-approved reason'
```

beta Environment、专用 Runner 与目标部署配置路径已被真实 workflow exercise；是否完成某次 Beta 发布，以 GitHub Actions 对应
run、release manifest 和主机八阶段记录为准，不硬编码最近一次 run 的成败。不得把单元测试、GitHub-hosted build 或本地
Compose 结果写成真实目标环境部署；具体 workflow run、release manifest、主机八阶段记录和真实 HTTPS public smoke 结果才是部署证据。

#### 联合备份与隔离恢复

主机需安装 `age`。备份目的地必须是已挂载的私有跨故障域、append-only 位置；`NORA_BACKUP_AGE_RECIPIENT` 只在 operator
进程环境中提供，不写入 env 文件。preflight、备份和恢复由受控 root operator 执行，以核验跨 group Secret 并把明文 staging
显式交给固定 UID `10001` 的 ops 容器；目标备份屏障停止 Web/API，依次生成 PostgreSQL custom dump、available Artifact manifest、
删除台账和 MinIO 对象副本，恢复 Web/API 后再加密写入新恢复点；元数据导出只挂载应用数据库 URL，对象复制只挂载只读备份身份且
不接收 MinIO root，失败时 trap 会恢复 Web/API 并清除明文 staging。

```bash
NORA_BACKUP_AGE_RECIPIENT='age1...' \
  deploy/backup.sh /etc/nora/production.env /mnt/private-append-only/nora
```

恢复 env 必须使用不同 Compose project、数据库目录、Bucket 数据目录、Secret、DNS 记录和报告目录，project 名必须包含
`restore` 或 `rehearsal`。恢复命令不启动 Web/API，不绑定宿主端口，也不执行任何外部写；恢复归档只接受固定元数据文件、
常规对象文件和安全相对路径，拒绝链接、特殊文件、路径穿越及未知顶层条目。它恢复 PostgreSQL 与对象后，
记录 Schema revision，并核验 owner/版本引用、Artifact size/SHA-256、缺失/损坏对象、孤儿对象和删除状态；任一差异以退出码 `2` 阻止
晋升，报告只保存 Artifact/owner ID 与对象键的短哈希，不保存原始对象键或正文。

```bash
NORA_ISOLATED_RESTORE_CONFIRMATION=isolated-no-public-ingress \
  deploy/restore.sh /etc/nora/restore.env recovery-point.tar.age \
  /etc/nora/restore-age-identity /var/lib/nora/restore-report
```

`backup-record.json` 记录停写秒数，`restore-record.json` 记录隔离恢复秒数和无公网/无外部写边界。它们是某次演练数据，不自动等于
RPO/RTO 承诺。只有真实 Beta provider/region、跨故障域目的地、成本、保留期、责任人及首次恢复演练均已记录，才能形成目标环境
证据；本地 Compose 演练不得冒充该证据。逻辑删除立即撤销 API 可见性，物理删除失败保持可重试状态；PostgreSQL 继续是生命周期
事实源，MinIO 只保存字节。当前没有全账户数据导出 API，operator dump 只用于受控恢复，不对用户界面开放。

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

此 hook 通过宿主机 `uv run` 依次执行 ruff 格式检查、ruff lint、mypy，以及单元和架构测试。手动验证 hook：

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

运行时依赖和开发依赖均通过宿主机 `backend/` 中的 uv 管理：

```bash
cd backend
uv add package-name
uv add --dev package-name
uv remove package-name
uv lock
uv sync --frozen --extra dev
```

提交依赖变更时必须同时提交 `backend/pyproject.toml` 和 `backend/uv.lock`。不要提交 `.env`、`.venv`、`dist` 或其他本地产物。

Agent Runtime 的 LangGraph 依赖由 `backend/pyproject.toml` 固定在 `langgraph>=1.0,<2`，通过 `uv lock` 更新锁文件；
LangGraph 只在 `backend/app/agent_runtime/` 外层 Adapter 使用，不能被 Domain、Ports 或 Application 导入。

## 路径与挂载规则

- 推荐工作区：`/Users/<user>/Projects/Nora`（即 `$HOME/Projects/Nora`）。
- Compose 开发文件只挂载 Docker 数据卷，不挂载源码；API/Web 直接使用宿主机工作区。
- 不要在 macOS 中切换到另一套 Docker context 或同时启动另一套 Docker Engine。
- 宿主 API 使用 `backend/.env`；发布 smoke Compose 使用根目录 `.env`，模板均为 `backend/.env.example`。
- Docker 命名卷保存数据库和 MinIO 数据，不写入仓库目录。

## 故障排查

### Docker daemon 未运行

确认 OrbStack 已启动且当前 Docker context 指向 OrbStack，然后在 macOS Terminal 验证：

```bash
docker context show
docker info
```

### 端口已被占用

检查端口：

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':8000|:5432|:9000|:9001'
```

修改 `.env` 中的 `API_PORT`、`POSTGRES_PORT`、`STORAGE_PORT` 或 `STORAGE_CONSOLE_PORT` 后重建服务：

```bash
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d db storage
```

### API 无法连接数据库

先检查数据库健康状态和 API 环境变量：

```bash
docker compose -f docker-compose.dev.yml ps db
docker compose -f docker-compose.dev.yml logs db
cd backend && grep '^DATABASE_URL=' .env
```

容器内数据库主机必须是 `db`，不能写 `localhost`。等待 `db` 通过 healthcheck 后再启动 API。

### 修改代码后没有重载

确认宿主 API 以 `--reload` 启动，并检查监听端口：

```bash
curl --fail http://localhost:8000/live
ps aux | grep '[u]vicorn'
```

如果仓库位于网络盘或外置慢速卷，迁移到 `$HOME/Projects/Nora` 后重新启动宿主 API/Web。

### 清理后重新初始化

以下操作会删除本地数据库和 MinIO 数据，不可恢复：

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d db storage
docker compose -f docker-compose.dev.yml run --rm storage-init
```

## 当前边界

本指南只说明开发和运行方法，不维护功能完成清单。当前可运行能力、逐项代码路径与合并证据只以
[`current-capabilities.toml`](current-capabilities.toml) 为准；不要把本指南或路线图中的目标、示例和环境骨架当作当前能力。
