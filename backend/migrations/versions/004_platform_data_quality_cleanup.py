"""004_platform_data_quality_cleanup

Revision ID: 004_platform_cleanup
Revises: 003_pgvector_embeddings
Create Date: 2026-09-07 13:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_platform_cleanup"
down_revision: str | None = "003_pgvector_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Normalize contaminated platform names with valid slugs to canonical names
    canonical_updates = [
        ("pc", "PC"),
        ("xbox-series-x", "Xbox Series X"),
        ("xbox-series-s", "Xbox Series S"),
        ("xbox-one", "Xbox One"),
        ("nintendo-switch", "Nintendo Switch"),
        ("nintendo-switch-2", "Nintendo Switch 2"),
        ("playstation-4", "PlayStation 4"),
        ("playstation-5", "PlayStation 5"),
    ]
    for slug, clean_name in canonical_updates:
        op.execute(
            sa.text("UPDATE platforms SET name = :name WHERE slug = :slug").bindparams(
                name=clean_name, slug=slug
            )
        )

    # 2. Re-point or clean ps5 (alias of playstation-5)
    # Remove duplicate game_platform links where game already has playstation-5
    op.execute(
        sa.text("""
            DELETE FROM game_platforms gp_ps5
            USING platforms p_ps5, platforms p_ps5_canon, game_platforms gp_canon
            WHERE p_ps5.slug = 'ps5'
              AND p_ps5_canon.slug = 'playstation-5'
              AND gp_ps5.platform_id = p_ps5.id
              AND gp_canon.platform_id = p_ps5_canon.id
              AND gp_ps5.game_id = gp_canon.game_id;
        """)
    )

    # Re-point any remaining game_platforms from ps5 to playstation-5
    op.execute(
        sa.text("""
            UPDATE game_platforms gp
            SET platform_id = (SELECT id FROM platforms WHERE slug = 'playstation-5' LIMIT 1)
            WHERE gp.platform_id = (SELECT id FROM platforms WHERE slug = 'ps5' LIMIT 1)
              AND EXISTS (SELECT 1 FROM platforms WHERE slug = 'playstation-5');
        """)
    )

    # Delete duplicate ps5 platform
    op.execute(sa.text("DELETE FROM platforms WHERE slug = 'ps5';"))

    # 3. Defensively remove any leftover contaminated platforms matching category/review patterns
    op.execute(
        sa.text("""
            DELETE FROM game_platforms
            WHERE platform_id IN (
                SELECT id FROM platforms
                WHERE lower(name) LIKE 'new % games'
                   OR lower(name) LIKE 'best % games'
                   OR lower(name) LIKE 'upcoming % games'
                   OR lower(name) LIKE 'based on %'
            );
        """)
    )
    op.execute(
        sa.text("""
            DELETE FROM platforms
            WHERE lower(name) LIKE 'new % games'
               OR lower(name) LIKE 'best % games'
               OR lower(name) LIKE 'upcoming % games'
               OR lower(name) LIKE 'based on %';
        """)
    )


def downgrade() -> None:
    pass
