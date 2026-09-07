from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, running, completed, failed
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)  # scheduled, manual
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    game_processings: Mapped[list["DailyGameProcessing"]] = relationship(
        "DailyGameProcessing",
        back_populates="crawl_run",
    )


class DailyCrawlState(Base):
    __tablename__ = "daily_crawl_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    processing_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(50), default="new_releases", nullable=False)  # new_releases, browse
    browse_page: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    browse_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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


class DailyGameProcessing(Base):
    __tablename__ = "daily_game_processings"
    __table_args__ = (
        # Mandatory invariant: one game cannot be processed more than once per calendar day
        UniqueConstraint("processing_date", "game_external_id", name="uq_daily_game_processing_date_game"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    processing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    game_external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    crawl_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("crawl_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    crawl_run: Mapped[Optional["CrawlRun"]] = relationship("CrawlRun", back_populates="game_processings")
