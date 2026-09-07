from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for injecting async SQLAlchemy sessions into route handlers."""
    async for session in get_async_db():
        yield session
