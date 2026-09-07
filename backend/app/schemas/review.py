from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewRead(BaseModel):
    id: int
    review_type: str
    external_id: str | None = None
    author: str | None = None
    rating: float | None = None
    body: str | None = None
    published_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
