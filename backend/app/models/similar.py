from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.game import Game


class SimilarGame(Base):
    __tablename__ = "similar_games"
    __table_args__ = (
        # Prohibit self-similarity reference
        CheckConstraint("game_id != similar_game_id", name="ck_similar_game_not_self"),
        # Unique pair constraint
        UniqueConstraint("game_id", "similar_game_id", name="uq_similar_game_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similar_game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(50), default="cosine-v1", nullable=False)

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
    game: Mapped["Game"] = relationship(
        "Game", foreign_keys=[game_id], back_populates="similar_associations"
    )
    similar_game: Mapped["Game"] = relationship("Game", foreign_keys=[similar_game_id])
