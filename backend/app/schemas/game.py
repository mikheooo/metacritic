from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.platform import GamePlatformRead
from app.schemas.review import ReviewRead
from app.schemas.summary import GameReviewSummaryRead
from app.schemas.youtube import YouTubeLetsPlayRead


class GameBase(BaseModel):
    title: str
    metacritic_slug: str
    metacritic_url: str
    cover_url: str | None = None
    developer: str | None = None
    description: str | None = None
    description_ru: str | None = None
    trailer_url: str | None = None
    critic_summary: str | None = None
    user_summary: str | None = None


class GameCreate(GameBase):
    pass


class GameRead(GameBase):
    id: int
    created_at: datetime
    updated_at: datetime
    game_platforms: list[GamePlatformRead] = []

    model_config = ConfigDict(from_attributes=True)


class SimilarGameItemRead(BaseModel):
    id: int
    title: str
    cover_url: str | None = None
    similarity_score: float
    platforms: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class GameDetailRead(GameRead):
    reviews: list[ReviewRead] = []
    review_summaries: list[GameReviewSummaryRead] = []
    critic_summary_detail: GameReviewSummaryRead | None = None
    user_summary_detail: GameReviewSummaryRead | None = None
    critic_review_count: int = 0
    user_review_count: int = 0
    similar_games: list[SimilarGameItemRead] = []
    lets_play: YouTubeLetsPlayRead | None = None

    model_config = ConfigDict(from_attributes=True)


class GameListResponse(BaseModel):
    items: list[GameRead]
    total: int
    limit: int
    offset: int
