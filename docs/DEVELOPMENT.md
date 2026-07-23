# 开发指南

> **Docker 优先。** 所有开发、测试和代码检查操作都在容器中进行。宿主机不需要安装 Python 或 pip，只需 Docker 和 Docker Compose。
>
> **无虚拟环境。** 不创建 `.venv`，不激活 venv。容器内使用 `uv --system` 直接管理系统 Python 环境，宿主机不安装项目依赖。

## 前置条件

- **Docker Desktop**（Windows / macOS）或 **Docker Engine + Docker Compose**（Linux）
- **uv**（可选，仅当需要在宿主机执行快速脚本或初始化时）
- Git

验证环境：

```bash
docker --version
docker compose version
```

## 快速开始

### 1. 启动开发环境

```bash
# 从环境变量模板创建本地配置
cp .env.example .env

# 启动所有服务（API + 数据库 + Redis + MinIO）
docker compose up
```

首次启动会自动构建镜像并安装依赖，耗时约 1-3 分钟。后续启动使用缓存。

### 2. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 查看运行中的服务
docker compose ps
```

### 3. 查看日志

```bash
# 所有服务日志
docker compose logs -f

# 仅 API 服务日志
docker compose logs -f api
```

### 4. 停止环境

```bash
# 停止并保留容器
docker compose stop

# 停止并删除容器（不删除数据卷）
docker compose down

# 完全清理（包括数据卷）
docker compose down -v
```

---

## 容器架构

```
宿主机                        Docker 网络
┌──────────┐               ┌─────────────────────┐
│  源码目录 │──volume mount──│  api (FastAPI)      │
│  .env    │               │  uvicorn --reload    │
│  .env.example           │  :8000               │
│          │               ├─────────────────────┤
│          │               │  db (PostgreSQL 16)  │
│          │               │  :5432               │
│          │               ├─────────────────────┤
│          │               │  redis (Redis 7)     │
│          │               │  :6379               │
│          │               ├─────────────────────┤
│          │               │  storage (MinIO)     │
│          │               │  :9000 :9001         │
└──────────┘               └─────────────────────┘
```

### Volume 挂载

- 源码目录挂载到容器内，修改代码即时生效（uvicorn `--reload`）
- 依赖锁文件（`uv.lock`）通过挂载同步到宿主机
- 数据库数据存储在 Docker 命名卷中，不在项目目录内
- 工具缓存（ruff、pytest、mypy）存储在容器内，不写入宿主机

---

## 常用命令

所有命令通过 `docker compose exec` 在运行中的容器内执行。

### 运行测试

```bash
# 运行全部测试
docker compose exec api pytest

# 运行指定测试文件
docker compose exec api pytest tests/unit/test_config.py

# 运行指定测试函数
docker compose exec api pytest tests/unit/test_config.py::test_load_env

# 带覆盖率
docker compose exec api pytest --cov=nora --cov-report=term

# 架构测试
docker compose exec api pytest tests/architecture/
```

### 代码检查

```bash
# Lint 检查
docker compose exec api ruff check .

# 格式化检查
docker compose exec api ruff format --check .

# 自动格式化
docker compose exec api ruff format .

# 类型检查
docker compose exec api mypy src/
```

### 数据库

```bash
# 执行迁移
docker compose exec api alembic upgrade head

# 创建新迁移
docker compose exec api alembic revision --autogenerate -m "描述"

# 回滚迁移
docker compose exec api alembic downgrade -1

# 查看迁移历史
docker compose exec api alembic history

# 连接到 PostgreSQL（psql）
docker compose exec db psql -U nora -d nora
```

### 依赖管理

使用 `uv` 管理依赖。容器内已设置 `UV_SYSTEM_PYTHON=1`，所有 `uv` 命令直接操作系统 Python，不创建虚拟环境。
`pyproject.toml` 和 `uv.lock` 通过 volume 同步到宿主机。

```bash
# 添加运行时依赖
docker compose exec api uv add httpx

# 添加开发依赖
docker compose exec api uv add --dev pytest-watch

# 移除依赖
docker compose exec api uv remove httpx

# 更新所有依赖
docker compose exec api uv sync --upgrade

# 查看依赖树
docker compose exec api uv tree
```

> 修改依赖后提交 `pyproject.toml` 和 `uv.lock` 的变更。

### 其他

```bash
# 进入容器 Shell
docker compose exec api bash

# 打开 Python REPL
docker compose exec api python

# 重建镜像（修改 Dockerfile 或依赖后）
docker compose build api

# 查看容器资源使用
docker stats
```

---

## 开发工作流

### 标准循环

```bash
# 1. 从 main 创建分支
git checkout -b nora/feat-xxx

# 2. 启动环境（后台模式）
docker compose up -d

# 3. 编码 → 即时生效（hot reload）
#    编辑源码文件，保存后 uvicorn 自动重载

# 4. 运行测试和代码检查
docker compose exec api pytest
docker compose exec api ruff check .
docker compose exec api mypy src/

# 5. 创建迁移（如需修改数据库）
docker compose exec api alembic revision --autogenerate -m "描述"

# 6. 执行迁移
docker compose exec api alembic upgrade head

# 7. 提交代码
git add -A
git commit -m "feat(scope): 实现 xxx"

# 8. 停止环境
docker compose down
```

### 添加新依赖

```bash
docker compose exec api uv add package-name
```

这会同时更新 `pyproject.toml` 和 `uv.lock`。后续提交这两个文件即可，其他开发者通过 `docker compose up` 重建镜像时自动安装新依赖。

### 重置数据库

```bash
# 删除数据卷后重启
docker compose down -v
docker compose up
```

---

## 代码组织

```
Nora/
├── apps/
│   ├── api/              # FastAPI 应用工厂、路由、middleware
│   ├── worker/           # Celery 任务进程
│   └── demo/             # Gradio 客户端（后续引入）
├── src/nora/
│   ├── domain/           # 领域模型、规则、Policy（无外部依赖）
│   ├── application/      # Use Case、Command、Query、DTO
│   ├── ports/            # Repository、Gateway 等接口抽象
│   ├── agents/           # LangGraph Adapter、Agent State
│   ├── infrastructure/   # PostgreSQL、Redis、Storage 等实现
│   └── integrations/     # 外部服务 Adapter（模型、地图、天气等）
├── tests/
│   ├── unit/             # 无外部依赖的纯逻辑测试
│   ├── architecture/     # 依赖方向、导入规则验证
│   ├── contract/         # Port 契约测试
│   ├── integration/      # 需要 PostgreSQL/Redis 等服务的测试
│   └── e2e/              # 端到端测试
├── docker/
│   ├── Dockerfile.api    # API 服务镜像
│   └── Dockerfile.worker # Worker 服务镜像
├── docker-compose.yml    # 主编排文件
├── docker-compose.override.yml  # 开发覆写
└── pyproject.toml        # 项目元数据与工具配置
```

### 依赖方向（强制）

```
apps/  ──→  src/nora/application/  ──→  src/nora/domain/
                │
                ↓
         src/nora/ports/  ←──  src/nora/infrastructure/
                                    src/nora/integrations/
```

- `domain/` 只使用 Python 标准库，不导入 FastAPI、SQLAlchemy、LangGraph 等
- `application/` 可以导入 domain 和 ports，不导入 infrastructure
- `infrastructure/` 实现 ports 中定义的接口
- 违反该方向的代码在架构测试中被阻断

---

## 配置说明

### 环境变量

通过 `.env` 文件配置（由 `docker-compose.override.yml` 自动加载）：

```ini
# 运行环境
ENV=development
DEBUG=true
LOG_LEVEL=debug

# 数据库（由 docker-compose 提供服务，无需修改）
DATABASE_URL=postgresql+asyncpg://nora:nora@db:5432/nora

# Redis（由 docker-compose 提供服务，无需修改）
REDIS_URL=redis://redis:6379/0

# 对象存储（由 docker-compose 提供服务，无需修改）
STORAGE_ENDPOINT=http://storage:9000
STORAGE_ACCESS_KEY=noraminioadmin
STORAGE_SECRET_KEY=noraminioadmin
```

> **不要提交 `.env` 文件。** 使用 `.env.example` 作为模板，提交 `.env.example` 的变更。

### 端口映射

| 服务 | 内部端口 | 宿主机端口 | 说明 |
|------|---------|-----------|------|
| API | 8000 | 8000 | FastAPI 服务 |
| PostgreSQL | 5432 | 5432 | 数据库 |
| Redis | 6379 | 6379 | 缓存/队列 |
| MinIO API | 9000 | 9000 | 对象存储 |
| MinIO Console | 9001 | 9001 | MinIO 管理界面 |

---

## Dockerfile 说明

### API 服务（`docker/Dockerfile.api`）

```dockerfile
FROM python:3.11-slim

# uv 直接管理系统 Python，不创建虚拟环境
ENV UV_SYSTEM_PYTHON=1

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 复制依赖文件
COPY pyproject.toml uv.lock /app/
WORKDIR /app

# 安装依赖（直接写入系统 Python，无 .venv）
RUN uv sync --frozen --no-dev

# 复制源码
COPY . /app

# 开发模式入口（docker-compose.override.yml 覆盖 CMD）
CMD ["uvicorn", "nora.apps.api:create_app()", "--host", "0.0.0.0", "--port", "8000"]
```

> `UV_SYSTEM_PYTHON=1` 使 uv 直接操作容器内的系统 Python，不生成 `.venv` 目录。`--no-dev` 缩小生产镜像体积；开发时通过 `docker-compose.override.yml` 传入 `--dev`。

### Worker 服务（`docker/Dockerfile.worker`）

预留骨架，M4 补充。

---

## 代码质量

### 质量标准

- **ruff**：代码风格和 lint 检查，遵循 `pyproject.toml` 中的配置
- **mypy**：严格模式类型检查
- **pytest**：测试覆盖率逐步提升，新代码必须有对应测试
- **架构测试**：验证依赖方向，domain 层不得导入外部框架

### 提交前运行

```bash
docker compose exec api ruff check .
docker compose exec api mypy src/
docker compose exec api pytest
```

### 常见问题

**Q：修改代码后没有自动重载？**
确保 `docker-compose.override.yml` 中挂载了源码目录，且 uvicorn 以 `--reload` 模式运行。

**Q：容器内无法连接数据库？**
数据库服务名是 `db`，连接字符串使用 `host=db` 而不是 `localhost`。

**Q：如何清理所有缓存和数据？**
```bash
docker compose down -v
docker system prune -a  # 清理所有未使用的镜像和构建缓存
```

**Q：依赖变更后容器未更新？**
```bash
docker compose build --no-cache api
docker compose up -d
```
