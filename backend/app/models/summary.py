from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.game import Game


class GameReviewSummary(Base):
    __tablename__ = "game_review_summaries"
    __table_args__ = (
        UniqueConstraint("game_id", "review_type", name="uq_game_review_summary_game_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "critic" or "user"
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    likes: Mapped[list[str]] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    dislikes: Mapped[list[str]] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
    )
    review_count_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_reviews_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="openai", nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    game: Mapped["Game"] = relationship("Game", back_populates="review_summaries")
