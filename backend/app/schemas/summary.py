from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GameReviewSummaryRead(BaseModel):
    id: int
    game_id: int
    review_type: str
    summary: str
    likes: list[str] = []
    dislikes: list[str] = []
    review_count_used: int = 0
    total_reviews_seen: int = 0
    input_fingerprint: str
    provider: str
    model: str
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    generated_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
