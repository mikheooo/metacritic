import logging
import math
import time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.embedding import GameEmbedding
from app.models.similar import SimilarGame

logger = logging.getLogger(__name__)


def _cosine_similarity_python(vec_a: list[float], vec_b: list[float]) -> float:
    """Fallback cosine similarity computation for SQLite unit test environments."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1.0
    norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1.0
    return float(dot / (norm_a * norm_b))


class SimilarGamesService:
    """
    Computes semantic similarity using pgvector cosine distance in PostgreSQL,
    and materializes top-K recommendations into the similar_games cache table.
    """

    def __init__(
        self,
        db: AsyncSession,
        limit: int = settings.SIMILAR_GAMES_LIMIT,
        algorithm_version: str = "cosine-v1",
    ) -> None:
        self.db = db
        self.limit = limit
        self.algorithm_version = algorithm_version

    async def find_similar_games(
        self,
        game_id: int,
        limit: int | None = None,
    ) -> list[tuple[int, float]]:
        """
        Executes vector similarity search for a given game.
        Returns top-K (similar_game_id, similarity_score) tuples, ordered by score descending.
        Excludes source game (never recommends self) and unembedded games.
        """
        k = limit or self.limit

        # 1. Fetch source embedding
        stmt_src = select(GameEmbedding).where(GameEmbedding.game_id == game_id)
        res_src = await self.db.execute(stmt_src)
        src_emb = res_src.scalar_one_or_none()
        if not src_emb:
            logger.debug("Source game %d has no embedding; returning empty similar list", game_id)
            return []

        # 2. Check dialect
        bind = self.db.bind
        dialect_name = bind.dialect.name if bind else "postgresql"

        if dialect_name == "postgresql":
            # Native PostgreSQL pgvector cosine search:
            # cosine_distance operator <=> evaluates cosine distance (0 for identical, up to 2).
            # cosine_similarity = 1 - cosine_distance.
            distance_expr = GameEmbedding.embedding.cosine_distance(src_emb.embedding)
            similarity_expr = (1.0 - distance_expr).label("similarity_score")

            stmt = (
                select(GameEmbedding.game_id, similarity_expr)
                .where(GameEmbedding.game_id != game_id)
                .order_by(distance_expr.asc())
                .limit(k)
            )
            res = await self.db.execute(stmt)
            rows = res.all()
            return [(row[0], float(row[1])) for row in rows]

        # In-memory fallback for SQLite unit test environments
        stmt_candidates = select(GameEmbedding).where(GameEmbedding.game_id != game_id)
        res_cand = await self.db.execute(stmt_candidates)
        candidates = res_cand.scalars().all()

        scored: list[tuple[int, float]] = []
        for cand in candidates:
            # cand.embedding on SQLite is deserialized as a list or string
            vec_cand = cand.embedding if isinstance(cand.embedding, list) else list(cand.embedding)
            vec_src = src_emb.embedding if isinstance(src_emb.embedding, list) else list(src_emb.embedding)
            sim = _cosine_similarity_python(vec_src, vec_cand)
            scored.append((cand.game_id, sim))

        # Highest similarity first
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    async def refresh_for_game(
        self,
        game_id: int,
        limit: int | None = None,
    ) -> list[SimilarGame]:
        """
        Atomically computes and materializes the top-K recommendations for a single game.
        Deletes stale recommendations and inserts fresh ones in a clean transaction.
        """
        k = limit or self.limit
        matches = await self.find_similar_games(game_id=game_id, limit=k)

        # Atomic replacement of recommendations for this game
        stmt_del = delete(SimilarGame).where(SimilarGame.game_id == game_id)
        await self.db.execute(stmt_del)

        new_associations: list[SimilarGame] = []
        for similar_id, score in matches:
            if similar_id == game_id:
                # Invariant: never recommend self
                continue
            rec = SimilarGame(
                game_id=game_id,
                similar_game_id=similar_id,
                similarity_score=score,
                algorithm_version=self.algorithm_version,
            )
            self.db.add(rec)
            new_associations.append(rec)

        await self.db.flush()
        await self.db.commit()
        return new_associations

    async def rebuild_all(self, limit: int | None = None) -> dict[str, Any]:
        """
        Rebuilds recommendations for all embedded games in the catalog.
        Solves the stale recommendation problem by ensuring newly embedded games
        propagate into both forward and reverse recommendation lists.
        """
        start_time = time.perf_counter()
        logger.info("similarity_refresh_started: algorithm=%s", self.algorithm_version)

        stmt = select(GameEmbedding.game_id).order_by(GameEmbedding.game_id.asc())
        res = await self.db.execute(stmt)
        game_ids = list(res.scalars().all())

        total_associations = 0
        per_game_results: dict[int, int] = {}

        for gid in game_ids:
            associations = await self.refresh_for_game(game_id=gid, limit=limit)
            per_game_results[gid] = len(associations)
            total_associations += len(associations)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "similarity_refresh_completed: games=%d associations=%d duration_ms=%.2f",
            len(game_ids),
            total_associations,
            duration_ms,
        )

        return {
            "total_games": len(game_ids),
            "total_associations": total_associations,
            "duration_ms": duration_ms,
            "per_game": per_game_results,
        }
