"""006_youtube_letsplay

Revision ID: 006_youtube_letsplay
Revises: 005_crawl_runs_events
Create Date: 2026-09-07 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_youtube_letsplay"
down_revision: str | None = "005_crawl_runs_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create game_youtube_videos table
    op.create_table(
        "game_youtube_videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=True),
        sa.Column("channel_title", sa.String(length=255), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("search_query", sa.String(length=500), nullable=False),
        sa.Column("selection_rank", sa.Integer(), server_default="1", nullable=False),
        sa.Column("selection_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="discovered", nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
    )
    op.create_index(op.f("ix_game_youtube_videos_id"), "game_youtube_videos", ["id"], unique=False)
    op.create_index(
        op.f("ix_game_youtube_videos_game_id"), "game_youtube_videos", ["game_id"], unique=True
    )
    op.create_index(
        op.f("ix_game_youtube_videos_youtube_video_id"),
        "game_youtube_videos",
        ["youtube_video_id"],
        unique=False,
    )

    # 2. Create youtube_transcripts table
    op.create_table(
        "youtube_transcripts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_youtube_video_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("is_generated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("segment_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["game_youtube_video_id"], ["game_youtube_videos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_youtube_video_id"),
    )
    op.create_index(op.f("ix_youtube_transcripts_id"), "youtube_transcripts", ["id"], unique=False)
    op.create_index(
        op.f("ix_youtube_transcripts_game_youtube_video_id"),
        "youtube_transcripts",
        ["game_youtube_video_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_youtube_transcripts_text_hash"),
        "youtube_transcripts",
        ["text_hash"],
        unique=False,
    )

    # 3. Create youtube_summaries table
    op.create_table(
        "youtube_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_youtube_video_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "key_points",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("summary_language", sa.String(length=20), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["game_youtube_video_id"], ["game_youtube_videos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_youtube_video_id"),
    )
    op.create_index(op.f("ix_youtube_summaries_id"), "youtube_summaries", ["id"], unique=False)
    op.create_index(
        op.f("ix_youtube_summaries_game_youtube_video_id"),
        "youtube_summaries",
        ["game_youtube_video_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_youtube_summaries_input_fingerprint"),
        "youtube_summaries",
        ["input_fingerprint"],
        unique=False,
    )

    # 4. Add youtube_processed_count to crawl_runs
    op.add_column(
        "crawl_runs",
        sa.Column(
            "youtube_processed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("crawl_runs", "youtube_processed_count")
    op.drop_index(op.f("ix_youtube_summaries_input_fingerprint"), table_name="youtube_summaries")
    op.drop_index(
        op.f("ix_youtube_summaries_game_youtube_video_id"), table_name="youtube_summaries"
    )
    op.drop_index(op.f("ix_youtube_summaries_id"), table_name="youtube_summaries")
    op.drop_table("youtube_summaries")

    op.drop_index(op.f("ix_youtube_transcripts_text_hash"), table_name="youtube_transcripts")
    op.drop_index(
        op.f("ix_youtube_transcripts_game_youtube_video_id"), table_name="youtube_transcripts"
    )
    op.drop_index(op.f("ix_youtube_transcripts_id"), table_name="youtube_transcripts")
    op.drop_table("youtube_transcripts")

    op.drop_index(op.f("ix_game_youtube_videos_youtube_video_id"), table_name="game_youtube_videos")
    op.drop_index(op.f("ix_game_youtube_videos_game_id"), table_name="game_youtube_videos")
    op.drop_index(op.f("ix_game_youtube_videos_id"), table_name="game_youtube_videos")
    op.drop_table("game_youtube_videos")
