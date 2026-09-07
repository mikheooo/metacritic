"""003_pgvector_game_embeddings_and_similar_games

Revision ID: 003_pgvector_embeddings
Revises: c5f1c3786bf9
Create Date: 2026-09-07 12:30:00.000000

"""
from collections.abc import Sequence

import pgvector
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_pgvector_embeddings"
down_revision: str | None = "c5f1c3786bf9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension if not already enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create game_embeddings table
    op.create_table(
        "game_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_version", sa.String(length=50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", name="uq_game_embeddings_game_id"),
    )
    op.create_index(op.f("ix_game_embeddings_id"), "game_embeddings", ["id"], unique=False)
    op.create_index(op.f("ix_game_embeddings_game_id"), "game_embeddings", ["game_id"], unique=False)
    op.create_index(op.f("ix_game_embeddings_input_fingerprint"), "game_embeddings", ["input_fingerprint"], unique=False)

    # 3. Create HNSW index with vector_cosine_ops
    op.execute(
        "CREATE INDEX ix_game_embeddings_vector ON game_embeddings USING hnsw (embedding vector_cosine_ops);"
    )

    # 4. Update similar_games table
    op.add_column(
        "similar_games",
        sa.Column("algorithm_version", sa.String(length=50), server_default="cosine-v1", nullable=False),
    )
    op.add_column(
        "similar_games",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 5. Drop deprecated games.embedding column
    op.drop_column("games", "embedding")


def downgrade() -> None:
    # 1. Restore deprecated games.embedding column
    op.add_column(
        "games",
        sa.Column("embedding", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True),
    )

    # 2. Rollback similar_games columns
    op.drop_column("similar_games", "updated_at")
    op.drop_column("similar_games", "algorithm_version")

    # 3. Drop game_embeddings table (drops HNSW index automatically)
    op.drop_index(op.f("ix_game_embeddings_input_fingerprint"), table_name="game_embeddings")
    op.drop_index(op.f("ix_game_embeddings_game_id"), table_name="game_embeddings")
    op.drop_index(op.f("ix_game_embeddings_id"), table_name="game_embeddings")
    op.drop_table("game_embeddings")
