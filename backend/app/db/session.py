from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Engine kwargs
async_engine_kwargs = {"echo": False, "future": True}
sync_engine_kwargs = {"echo": False, "future": True}

if not settings.DATABASE_URL.startswith("sqlite"):
    async_engine_kwargs["pool_pre_ping"] = True
if not settings.sync_database_url.startswith("sqlite"):
    sync_engine_kwargs["pool_pre_ping"] = True

# Async engine & sessionmaker (for FastAPI)
async_engine = create_async_engine(settings.DATABASE_URL, **async_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Sync engine & sessionmaker (for Celery workers & Alembic)
sync_engine = create_engine(settings.sync_database_url, **sync_engine_kwargs)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
