"""007_russian_content_localization

Revision ID: 007_russian_content
Revises: 006_youtube_letsplay
Create Date: 2026-09-08 11:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_russian_content"
down_revision: str | None = "006_youtube_letsplay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add description_ru and description_source_hash to games
    op.add_column("games", sa.Column("description_ru", sa.Text(), nullable=True))
    op.add_column(
        "games", sa.Column("description_source_hash", sa.String(length=64), nullable=True)
    )

    # 2. Add body_ru and body_source_hash to reviews
    op.add_column("reviews", sa.Column("body_ru", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("body_source_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    # 1. Drop columns from reviews
    op.drop_column("reviews", "body_source_hash")
    op.drop_column("reviews", "body_ru")

    # 2. Drop columns from games
    op.drop_column("games", "description_source_hash")
    op.drop_column("games", "description_ru")
