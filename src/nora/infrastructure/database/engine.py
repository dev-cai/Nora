"""异步 SQLAlchemy 引擎和会话工厂。"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from nora.infrastructure.config import Settings


def create_database_engine(settings: Settings, database_url: str | None = None) -> AsyncEngine:
    """按配置创建异步引擎；SQLite 测试连接不使用 PostgreSQL 池参数。"""

    url = database_url or settings.database_url
    if not url:
        raise ValueError("DATABASE_URL is required to create a database engine")

    kwargs: dict[str, object] = {"echo": settings.debug, "pool_pre_ping": True}
    if not url.startswith("sqlite+"):
        kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
        )
    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建不自动提交的异步会话工厂。"""

    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
