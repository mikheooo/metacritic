
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import SortField, SortOrder
from app.schemas.game import GameDetailRead, GameListResponse, GameRead
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
    description="Retrieve detailed game card including platform scores and reviews.",
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
    return GameDetailRead.model_validate(game)
