"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-09-07 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Games table
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metacritic_slug", sa.String(length=255), nullable=False),
        sa.Column("metacritic_url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("developer", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trailer_url", sa.String(length=500), nullable=True),
        sa.Column("critic_summary", sa.Text(), nullable=True),
        sa.Column("user_summary", sa.Text(), nullable=True),
        sa.Column("embedding", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metacritic_url", name="uq_games_metacritic_url"),
    )
    op.create_index(op.f("ix_games_id"), "games", ["id"], unique=False)
    op.create_index(op.f("ix_games_metacritic_slug"), "games", ["metacritic_slug"], unique=False)
    op.create_index(op.f("ix_games_metacritic_url"), "games", ["metacritic_url"], unique=True)
    op.create_index(op.f("ix_games_title"), "games", ["title"], unique=False)

    # 2. Platforms table
    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_platforms_slug"),
    )
    op.create_index(op.f("ix_platforms_id"), "platforms", ["id"], unique=False)
    op.create_index(op.f("ix_platforms_slug"), "platforms", ["slug"], unique=True)

    # 3. GamePlatform association table
    op.create_table(
        "game_platforms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("metascore", sa.Integer(), nullable=True),
        sa.Column("userscore", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "platform_id", name="uq_game_platform"),
    )
    op.create_index(op.f("ix_game_platforms_id"), "game_platforms", ["id"], unique=False)
    op.create_index(op.f("ix_game_platforms_game_id"), "game_platforms", ["game_id"], unique=False)
    op.create_index(op.f("ix_game_platforms_platform_id"), "game_platforms", ["platform_id"], unique=False)

    # 4. Reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("review_type", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "review_type", "external_id", name="uq_review_game_type_external_id"),
    )
    op.create_index(op.f("ix_reviews_id"), "reviews", ["id"], unique=False)
    op.create_index(op.f("ix_reviews_game_id"), "reviews", ["game_id"], unique=False)
    op.create_index(op.f("ix_reviews_external_id"), "reviews", ["external_id"], unique=False)

    # 5. SimilarGames table
    op.create_table(
        "similar_games",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("similar_game_id", sa.Integer(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("game_id != similar_game_id", name="ck_similar_game_not_self"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["similar_game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "similar_game_id", name="uq_similar_game_pair"),
    )
    op.create_index(op.f("ix_similar_games_id"), "similar_games", ["id"], unique=False)
    op.create_index(op.f("ix_similar_games_game_id"), "similar_games", ["game_id"], unique=False)
    op.create_index(op.f("ix_similar_games_similar_game_id"), "similar_games", ["similar_game_id"], unique=False)

    # 6. CrawlRuns table
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("trigger_type", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_runs_id"), "crawl_runs", ["id"], unique=False)

    # 7. DailyCrawlStates table
    op.create_table(
        "daily_crawl_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("processing_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(length=50), nullable=False, server_default="new_releases"),
        sa.Column("browse_page", sa.Integer(), server_default="1", nullable=False),
        sa.Column("browse_offset", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("processing_date", name="uq_daily_crawl_states_processing_date"),
    )
    op.create_index(op.f("ix_daily_crawl_states_id"), "daily_crawl_states", ["id"], unique=False)
    op.create_index(op.f("ix_daily_crawl_states_processing_date"), "daily_crawl_states", ["processing_date"], unique=True)

    # 8. DailyGameProcessings table
    op.create_table(
        "daily_game_processings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("processing_date", sa.Date(), nullable=False),
        sa.Column("game_external_id", sa.String(length=255), nullable=False),
        sa.Column("crawl_run_id", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_run_id"], ["crawl_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("processing_date", "game_external_id", name="uq_daily_game_processing_date_game"),
    )
    op.create_index(op.f("ix_daily_game_processings_id"), "daily_game_processings", ["id"], unique=False)
    op.create_index(op.f("ix_daily_game_processings_processing_date"), "daily_game_processings", ["processing_date"], unique=False)
    op.create_index(op.f("ix_daily_game_processings_game_external_id"), "daily_game_processings", ["game_external_id"], unique=False)
    op.create_index(op.f("ix_daily_game_processings_crawl_run_id"), "daily_game_processings", ["crawl_run_id"], unique=False)


def downgrade() -> None:
    op.drop_table("daily_game_processings")
    op.drop_table("daily_crawl_states")
    op.drop_table("crawl_runs")
    op.drop_table("similar_games")
    op.drop_table("reviews")
    op.drop_table("game_platforms")
    op.drop_table("platforms")
    op.drop_table("games")
