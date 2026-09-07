"""005_crawl_runs_evolution_and_events

Revision ID: 005_crawl_runs_events
Revises: 004_platform_cleanup
Create Date: 2026-09-07 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_crawl_runs_events"
down_revision: str | None = "004_platform_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add monitoring and lifecycle columns to crawl_runs
    op.add_column("crawl_runs", sa.Column("task_id", sa.String(length=255), nullable=True))
    op.add_column("crawl_runs", sa.Column("target_count", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("crawl_runs", sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_runs", sa.Column("reviews_processed_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_runs", sa.Column("summaries_generated_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_runs", sa.Column("embeddings_generated_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_runs", sa.Column("current_stage", sa.String(length=50), nullable=True))
    op.add_column(
        "crawl_runs",
        sa.Column(
            "current_game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("crawl_runs", sa.Column("current_game_title", sa.String(length=255), nullable=True))
    op.add_column("crawl_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crawl_runs", sa.Column("error_summary", sa.Text(), nullable=True))

    op.create_index(op.f("ix_crawl_runs_task_id"), "crawl_runs", ["task_id"], unique=False)

    # 2. Create crawl_run_events append-only table
    op.create_table(
        "crawl_run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crawl_run_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crawl_run_events_id"), "crawl_run_events", ["id"], unique=False)
    op.create_index(op.f("ix_crawl_run_events_crawl_run_id"), "crawl_run_events", ["crawl_run_id"], unique=False)
    op.create_index(op.f("ix_crawl_run_events_event_type"), "crawl_run_events", ["event_type"], unique=False)
    op.create_index("ix_crawl_run_events_run_id_id", "crawl_run_events", ["crawl_run_id", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_crawl_run_events_run_id_id", table_name="crawl_run_events")
    op.drop_index(op.f("ix_crawl_run_events_event_type"), table_name="crawl_run_events")
    op.drop_index(op.f("ix_crawl_run_events_crawl_run_id"), table_name="crawl_run_events")
    op.drop_index(op.f("ix_crawl_run_events_id"), table_name="crawl_run_events")
    op.drop_table("crawl_run_events")

    op.drop_index(op.f("ix_crawl_runs_task_id"), table_name="crawl_runs")
    op.drop_column("crawl_runs", "error_summary")
    op.drop_column("crawl_runs", "heartbeat_at")
    op.drop_column("crawl_runs", "current_game_title")
    op.drop_column("crawl_runs", "current_game_id")
    op.drop_column("crawl_runs", "current_stage")
    op.drop_column("crawl_runs", "embeddings_generated_count")
    op.drop_column("crawl_runs", "summaries_generated_count")
    op.drop_column("crawl_runs", "reviews_processed_count")
    op.drop_column("crawl_runs", "discovered_count")
    op.drop_column("crawl_runs", "target_count")
    op.drop_column("crawl_runs", "task_id")
