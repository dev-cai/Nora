from unittest.mock import patch

from app.infrastructure.config import Settings
from app.infrastructure.database.engine import create_database_engine


def test_database_engine_receives_configured_pool_options() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://nora:nora@db/nora",
        database_pool_size=7,
        database_max_overflow=13,
        database_pool_timeout=4.5,
    )

    with patch("app.infrastructure.database.engine.create_async_engine") as create_engine:
        engine = create_database_engine(settings)

    assert engine is create_engine.return_value
    create_engine.assert_called_once_with(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=7,
        max_overflow=13,
        pool_timeout=4.5,
    )
