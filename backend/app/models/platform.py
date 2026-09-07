from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.game import Game


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    # Relationships
    game_platforms: Mapped[list["GamePlatform"]] = relationship(
        "GamePlatform",
        back_populates="platform",
        cascade="all, delete-orphan",
    )


class GamePlatform(Base):
    __tablename__ = "game_platforms"
    __table_args__ = (UniqueConstraint("game_id", "platform_id", name="uq_game_platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platforms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metascore: Mapped[int | None] = mapped_column(Integer, nullable=True)
    userscore: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    game: Mapped["Game"] = relationship("Game", back_populates="game_platforms")
    platform: Mapped["Platform"] = relationship(
        "Platform", back_populates="game_platforms", lazy="selectin"
    )
