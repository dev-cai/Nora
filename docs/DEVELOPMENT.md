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
      └─ Compose 容器：Python/uv、API、PostgreSQL、Redis、MinIO
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
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
```

Compose 会启动：

- `api`：FastAPI API，监听 `localhost:8000`
- `db`：PostgreSQL 16
- `redis`：Redis 7 骨架，M4 才进入业务路径
- `storage`：MinIO 骨架，后续对象存储能力按 Issue 交付

另开一个 WSL 终端验证：

```bash
cd "$HOME/projects/Nora"
curl http://localhost:8000/health
curl http://localhost:8000/ready
docker compose ps
```

首次启动和拉取到新迁移后都要执行 `alembic upgrade head`。API 不会在启动时自动修改数据库结构。

数据库可用时，健康检查应返回：

```json
{"status":"healthy"}
```

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

不要把生成值写回 `.env.example` 或提交包含真实密钥的 `.env`。

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

查看服务日志：

```bash
docker compose logs -f
docker compose logs -f api
```

查看容器状态和资源：

```bash
docker compose ps
docker stats
```

修改 `src/` 后，开发覆写文件会挂载 WSL 工作区，Uvicorn 会自动重载 API。

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
docker compose run --rm --no-deps tools mypy src/
docker compose run --rm --no-deps tools pytest tests/unit tests/architecture -q
```

集成测试只连接 `test` profile 中的隔离 PostgreSQL。`test-db` 使用 tmpfs，不复用开发数据库或命名卷：

```bash
docker compose --profile test run --rm test
docker compose --profile test stop test-db
```

集成测试要求 `TEST_DATABASE_URL` 或 `DATABASE_URL` 使用 `postgresql+asyncpg`。缺少连接或使用其他驱动时，
测试会明确失败；项目不支持 SQLite 回退。

## 依赖管理

运行时依赖和开发依赖均通过 development 容器内的 uv 管理：

```bash
docker compose run --rm --no-deps tools uv add package-name
docker compose run --rm --no-deps tools uv add --dev package-name
docker compose run --rm --no-deps tools uv remove package-name
docker compose run --rm --no-deps tools uv lock
docker compose build api
```

提交依赖变更时必须同时提交 `pyproject.toml` 和 `uv.lock`。不要提交 `.env`、`.venv`、`dist` 或其他本地产物。

## 路径与挂载规则

- 推荐工作区：`/home/<user>/projects/Nora`。
- Compose bind mount 的源路径来自 WSL 当前目录，不使用 `C:\...` 或 `D:\...`。
- 不要在 PowerShell 中进入 WSL 工作区后调用另一套 Docker context。
- `.env` 只在 WSL 工作区创建；模板是仓库中的 `.env.example`。
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
ss -ltnp | grep -E ':8000|:5432|:6379|:9000|:9001'
```

修改 `.env` 中的 `API_PORT`、`POSTGRES_PORT`、`REDIS_PORT`、`STORAGE_PORT` 或 `STORAGE_CONSOLE_PORT` 后重建服务：

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

当前已提供 M0 基线、Identity 本地账号认证与用户范围 Repository，以及不可变 JobPosting 领域模型和持久化
适配器。岗位创建/读取 API、幂等请求与审计仍由 M1 后续 Issue 交付；OAuth、邮箱验证、密码重置、角色权限、
RAG、Agent、Celery 和生产部署也尚不可用。不要把路线图内容当作当前可用能力。
