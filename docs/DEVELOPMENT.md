# Nora 开发指南

> 本指南以 Windows 11/10 + WSL2 Ubuntu 为唯一推荐的本地开发环境。
> 日常代码、uv、Docker Engine 和 Docker Compose 命令均在 WSL 终端中执行。
> Windows PowerShell 只用于一次性安装或管理 WSL，不用于项目开发命令。

## 环境边界

本地开发使用以下边界：

```text
Windows
  └─ WSL2 Ubuntu
      ├─ 项目代码：~/projects/Nora
      ├─ uv / Python：用于本地测试和质量检查
      ├─ Docker Engine
      └─ Docker Compose：API、PostgreSQL、Redis、MinIO
```

本项目不要求 Docker Desktop。不要在同一个工作流中混用 Windows Docker CLI、Docker Desktop 上下文和 WSL 内 Docker Engine。

## 前置条件

### Windows 一次性准备

在管理员 PowerShell 中安装 WSL2 和 Ubuntu：

```powershell
wsl --install -d Ubuntu
```

安装完成后重启 Windows，并从开始菜单打开 Ubuntu，创建 Linux 用户。检查 WSL 版本：

```powershell
wsl --list --verbose
```

目标发行版的 `VERSION` 应为 `2`。

### WSL 内安装工具

以下命令全部在 Ubuntu/WSL 终端执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3 python3-pip docker.io docker-compose-plugin
```

将当前用户加入 Docker 组，然后重新打开 WSL 终端：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

如果发行版未启用 systemd，可临时启动 Docker daemon：

```bash
sudo service docker start
```

验证工具：

```bash
docker version
docker compose version
python3 --version
git --version
```

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

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

当前 API 镜像使用 `--no-dev` 安装 runtime 依赖。测试、Ruff 和 mypy 在 WSL 内使用 uv 执行，不在 Windows Python 中执行：

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest tests/architecture -q
```

PostgreSQL、API 和其他依赖服务仍通过 WSL 内的 Docker Compose 启动：

```bash
docker compose up -d
uv run pytest -q
docker compose down
```

本地没有 PostgreSQL 时，Repository 集成测试会使用 SQLite async adapter；CI 会注入 PostgreSQL service 连接进行验证。

## 依赖管理

运行时依赖和开发依赖均通过 WSL 内的 uv 管理：

```bash
uv add package-name
uv add --dev package-name
uv remove package-name
uv lock
uv sync --frozen --extra dev
```

提交依赖变更时必须同时提交 `pyproject.toml` 和 `uv.lock`。不要提交 `.env`、`.venv`、`dist` 或其他本地产物。

## 路径与挂载规则

- 推荐工作区：`/home/<user>/projects/Nora`。
- Compose bind mount 的源路径来自 WSL 当前目录，不使用 `C:\...` 或 `D:\...`。
- 不要在 PowerShell 中进入 WSL 工作区后调用另一套 Docker context。
- `.env` 只在 WSL 工作区创建；模板是仓库中的 `.env.example`。
- Docker 命名卷保存数据库和 MinIO 数据，不写入仓库目录。

## 故障排查

### `docker: permission denied`

确认用户已加入 Docker 组，并重新打开 WSL：

```bash
groups
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

### Docker daemon 未运行

```bash
sudo service docker start
docker info
```

如果使用启用 systemd 的 WSL 发行版，可检查：

```bash
systemctl status docker
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
