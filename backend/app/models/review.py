from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.platform import Platform


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Deduplication constraint for repeated ingestion
        UniqueConstraint("game_id", "review_type", "external_id", name="uq_review_game_type_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("platforms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "critic" or "user"
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
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
    game: Mapped["Game"] = relationship("Game", back_populates="reviews")
    platform: Mapped["Platform | None"] = relationship("Platform", lazy="selectin")

