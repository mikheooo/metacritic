
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.game import Game
from app.models.platform import GamePlatform
from app.models.review import Review
from app.models.similar import SimilarGame
from app.models.summary import GameReviewSummary
from app.schemas.common import SortField, SortOrder
from app.schemas.game import GameDetailRead, GameListResponse, GameRead, SimilarGameItemRead
from app.schemas.summary import GameReviewSummaryRead
from app.services.game_service import get_game_by_id, get_games

router = APIRouter(prefix="/games", tags=["Games"])



@router.get(
    "",
    response_model=GameListResponse,
    summary="List Games",
    description="Retrieve paginated games catalog with filtering and safe whitelisted sorting.",
)
async def list_games(
    q: str | None = Query(default=None, description="Filter by title (case-insensitive substring)"),
    platform: str | None = Query(default=None, description="Filter by platform slug (e.g. pc, ps5, switch)"),
    sort: SortField = Query(default=SortField.CREATED_AT, description="Sort field: metascore, userscore, title, created_at"),
    order: SortOrder = Query(default=SortOrder.DESC, description="Sort direction: asc or desc"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of games to return"),
    offset: int = Query(default=0, ge=0, description="Number of games to skip"),
    db: AsyncSession = Depends(get_db),
) -> GameListResponse:
    games, total = await get_games(
        db=db,
        q=q,
        platform=platform,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    items = [GameRead.model_validate(g) for g in games]
    return GameListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{game_id}",
    response_model=GameDetailRead,
    summary="Get Game Details",
    description="Retrieve detailed game card including platform scores, reviews, structured AI summaries, and similar games.",
)
async def get_game(
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> GameDetailRead:
    game = await get_game_by_id(db=db, game_id=game_id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with id {game_id} not found",
        )

    stmt_sums = select(GameReviewSummary).where(GameReviewSummary.game_id == game_id)
    sums_res = await db.execute(stmt_sums)
    all_sums = list(sums_res.scalars().all())

    critic_sum = None
    user_sum = None
    for s in all_sums:
        if s.review_type == "critic":
            critic_sum = s
        elif s.review_type == "user":
            user_sum = s

    stmt_c = select(func.count(Review.id)).where(Review.game_id == game_id, Review.review_type == "critic")
    stmt_u = select(func.count(Review.id)).where(Review.game_id == game_id, Review.review_type == "user")
    critic_count = await db.scalar(stmt_c) or 0
    user_count = await db.scalar(stmt_u) or 0

    # Load similar games from recommendation cache
    stmt_sim = (
        select(SimilarGame)
        .options(
            selectinload(SimilarGame.similar_game)
            .selectinload(Game.game_platforms)
            .selectinload(GamePlatform.platform)
        )
        .where(SimilarGame.game_id == game_id)
        .order_by(SimilarGame.similarity_score.desc())
    )
    sim_res = await db.execute(stmt_sim)
    similar_rows = sim_res.scalars().all()

    similar_items: list[SimilarGameItemRead] = []
    for s_row in similar_rows:
        sim_game = s_row.similar_game
        if not sim_game or sim_game.id == game_id:
            continue
        plat_names = [
            gp.platform.name
            for gp in getattr(sim_game, "game_platforms", [])
            if gp.platform and gp.platform.name
        ]
        similar_items.append(
            SimilarGameItemRead(
                id=sim_game.id,
                title=sim_game.title,
                cover_url=sim_game.cover_url,
                similarity_score=round(s_row.similarity_score, 4),
                platforms=plat_names,
            )
        )

    detail = GameDetailRead.model_validate(game)
    if critic_sum:
        detail.critic_summary_detail = GameReviewSummaryRead.model_validate(critic_sum)
    if user_sum:
        detail.user_summary_detail = GameReviewSummaryRead.model_validate(user_sum)
    detail.critic_review_count = critic_count
    detail.user_review_count = user_count
    detail.similar_games = similar_items

    return detail

