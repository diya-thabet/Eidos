"""
Database engine and session factory.

Supports multiple backends via SQLAlchemy async drivers:

  EIDOS_DATABASE_URL=                         Driver needed
  postgresql+asyncpg://...                    asyncpg
  mysql+aiomysql://...                        aiomysql
  sqlite+aiosqlite:///path.db                 aiosqlite
  oracle+oracledb://...                       oracledb (async)
  mssql+aioodbc://...                         aioodbc

Switch databases by changing the single env var; no code change needed.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# If in_memory_db is True, override database_url to use SQLite in-memory
_effective_url = (
    "sqlite+aiosqlite://"
    if settings.in_memory_db
    else settings.database_url
)

# SQLite doesn't support pool_size / max_overflow
_is_sqlite = _effective_url.startswith("sqlite")

_engine_kwargs: dict[str, Any] = {"echo": settings.db_echo}
if not _is_sqlite:
    _engine_kwargs["pool_size"] = settings.db_pool_size
    _engine_kwargs["max_overflow"] = settings.db_max_overflow
elif _effective_url == "sqlite+aiosqlite://":
    # In-memory SQLite: use StaticPool so all connections share the same DB
    _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(_effective_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session
