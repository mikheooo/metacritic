from datetime import UTC, date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, running, completed, partial, failed
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)  # scheduled, manual

    target_count: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    reviews_processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summaries_generated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embeddings_generated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)  # queued, discovering, ingesting, reviews, summarizing, embedding, similarity, completed, partial, failed
    current_game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_game_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    events: Mapped[list["CrawlRunEvent"]] = relationship(
        "CrawlRunEvent",
        back_populates="crawl_run",
        cascade="all, delete-orphan",
        order_by="CrawlRunEvent.id",
    )


class CrawlRunEvent(Base):
    __tablename__ = "crawl_run_events"
    __table_args__ = (
        Index("ix_crawl_run_events_run_id_id", "crawl_run_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    crawl_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("crawl_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="SET NULL"),
        nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    crawl_run: Mapped["CrawlRun"] = relationship("CrawlRun", back_populates="events")


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
