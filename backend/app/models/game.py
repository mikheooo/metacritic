from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.platform import GamePlatform
    from app.models.review import Review
    from app.models.similar import SimilarGame
    from app.models.summary import GameReviewSummary


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    metacritic_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metacritic_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trailer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    critic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    game_platforms: Mapped[list["GamePlatform"]] = relationship(
        "GamePlatform",
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review",
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    review_summaries: Mapped[list["GameReviewSummary"]] = relationship(
        "GameReviewSummary",
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    similar_associations: Mapped[list["SimilarGame"]] = relationship(
        "SimilarGame",
        primaryjoin="Game.id == SimilarGame.game_id",
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
