
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.schemas.common import SortField, SortOrder


async def get_games(
    db: AsyncSession,
    q: str | None = None,
    platform: str | None = None,
    sort: SortField = SortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Game], int]:
    """
    Retrieve games with filtering, whitelisted sorting, and pagination.
    Guarantees SQL injection safety by using strict enum values and mapped ORM expressions.
    """
    # Base query for counting distinct games
    count_stmt = select(func.count(Game.id))

    # Base query for fetching games
    stmt = (
        select(Game)
        .options(
            selectinload(Game.game_platforms).selectinload(GamePlatform.platform),
        )
    )

    # Join platforms if filtering by platform slug
    if platform:
        platform_filter = Game.game_platforms.any(
            GamePlatform.platform.has(Platform.slug == platform)
        )
        count_stmt = count_stmt.where(platform_filter)
        stmt = stmt.where(platform_filter)

    # Filter by title
    if q:
        search_filter = Game.title.ilike(f"%{q}%")
        count_stmt = count_stmt.where(search_filter)
        stmt = stmt.where(search_filter)

    total = await db.scalar(count_stmt) or 0

    # Whitelist-based sort expression mapping
    is_desc = order == SortOrder.DESC

    if sort == SortField.TITLE:
        stmt = stmt.order_by(Game.title.desc() if is_desc else Game.title.asc())
    elif sort == SortField.METASCORE:
        # Sort by maximum metascore across platforms for this game
        score_subq = (
            select(func.coalesce(func.max(GamePlatform.metascore), -1))
            .where(GamePlatform.game_id == Game.id)
            .correlate(Game)
            .scalar_subquery()
        )
        stmt = stmt.order_by(
            score_subq.desc() if is_desc else score_subq.asc(),
            Game.id.desc() if is_desc else Game.id.asc(),
        )
    elif sort == SortField.USERSCORE:
        # Sort by maximum userscore across platforms for this game
        score_subq = (
            select(func.coalesce(func.max(GamePlatform.userscore), -1.0))
            .where(GamePlatform.game_id == Game.id)
            .correlate(Game)
            .scalar_subquery()
        )
        stmt = stmt.order_by(
            score_subq.desc() if is_desc else score_subq.asc(),
            Game.id.desc() if is_desc else Game.id.asc(),
        )
    else:  # SortField.CREATED_AT default
        stmt = stmt.order_by(Game.created_at.desc() if is_desc else Game.created_at.asc())

    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    games = list(result.scalars().all())

    return games, total


async def get_game_by_id(db: AsyncSession, game_id: int) -> Game | None:
    """Retrieve a single game with platforms and reviews loaded."""
    stmt = (
        select(Game)
        .options(
            selectinload(Game.game_platforms).selectinload(GamePlatform.platform),
            selectinload(Game.reviews),
        )
        .where(Game.id == game_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
