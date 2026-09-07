from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal, get_async_db


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Dependency returning the async session maker."""
    return AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for injecting async SQLAlchemy sessions into route handlers."""
    async for session in get_async_db():
        yield session

