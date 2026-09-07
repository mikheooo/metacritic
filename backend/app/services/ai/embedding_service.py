import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.embedding import GameEmbedding
from app.models.game import Game
from app.models.platform import GamePlatform
from app.services.ai.embedding_builder import (
    build_game_embedding_text,
    compute_embedding_fingerprint,
)
from app.services.ai.embedding_provider import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingRefreshResult:
    game_id: int
    status: str  # "generated", "skipped_unchanged", "failed"
    provider: str | None = None
    model: str | None = None
    dimensions: int | None = None
    input_fingerprint: str | None = None
    input_tokens: int | None = None
    error: str | None = None


def validate_vector(vector: list[float], expected_dimensions: int) -> None:
    """
    Validates that the embedding vector is non-empty, matches expected dimensions,
    and consists entirely of finite float values (no NaN, no Infinity).
    """
    if not vector:
        raise ValueError("Vector cannot be empty.")
    if len(vector) != expected_dimensions:
        raise ValueError(
            f"Vector dimension mismatch: expected {expected_dimensions}, got {len(vector)}"
        )
    for i, val in enumerate(vector):
        if not isinstance(val, (int, float)):
            raise ValueError(f"Vector component at index {i} is not a float: {type(val)}")
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Vector component at index {i} is not finite: {val}")


class GameEmbeddingService:
    """
    Application service managing the generation, validation, cost control,
    and persistence of game semantic embeddings in PostgreSQL/pgvector.
    """

    def __init__(
        self,
        db: AsyncSession,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or get_embedding_provider()

    async def refresh_game_embedding(
        self,
        game_id: int,
        force: bool = False,
    ) -> EmbeddingRefreshResult:
        """
        Refreshes or generates a semantic embedding for a single game.
        Enforces SHA-256 fingerprint cost-control (skips API call if unchanged).
        """
        start_time = time.perf_counter()
        logger.info(
            "embedding_started: game_id=%d provider=%s model=%s",
            game_id,
            self.provider.provider,
            self.provider.model,
        )

        # 1. Load Game with relationships
        stmt = (
            select(Game)
            .options(
                selectinload(Game.game_platforms).selectinload(GamePlatform.platform),
                selectinload(Game.review_summaries),
            )
            .where(Game.id == game_id)
        )
        res = await self.db.execute(stmt)
        game = res.scalar_one_or_none()
        if not game:
            logger.error("embedding_failed: Game with id %d not found", game_id)
            return EmbeddingRefreshResult(
                game_id=game_id,
                status="failed",
                error=f"Game with id {game_id} not found",
            )

        # 2. Build canonical embedding text & fingerprint
        canonical_text = build_game_embedding_text(game)
        if not canonical_text or not canonical_text.strip():
            logger.warning("embedding_failed: Game %d produced empty canonical text", game_id)
            return EmbeddingRefreshResult(
                game_id=game_id,
                status="failed",
                error="Produced empty canonical embedding text",
            )

        fingerprint = compute_embedding_fingerprint(
            canonical_text=canonical_text,
            provider=self.provider.provider,
            model=self.provider.model,
            dimensions=self.provider.dimensions,
            input_version=settings.EMBEDDING_INPUT_VERSION,
        )

        # 3. Check existing GameEmbedding row
        stmt_existing = select(GameEmbedding).where(GameEmbedding.game_id == game_id)
        res_existing = await self.db.execute(stmt_existing)
        existing_embedding = res_existing.scalar_one_or_none()

        if existing_embedding and existing_embedding.input_fingerprint == fingerprint and not force:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "embedding_skipped_unchanged: game_id=%d provider=%s model=%s fingerprint=%s latency_ms=%.2f",
                game_id,
                existing_embedding.provider,
                existing_embedding.model,
                fingerprint[:16],
                latency_ms,
            )
            return EmbeddingRefreshResult(
                game_id=game_id,
                status="skipped_unchanged",
                provider=existing_embedding.provider,
                model=existing_embedding.model,
                dimensions=existing_embedding.dimensions,
                input_fingerprint=fingerprint,
                input_tokens=existing_embedding.input_tokens,
            )

        # 4. Generate new embedding via provider
        try:
            embed_res = await self.provider.embed(canonical_text)
            validate_vector(embed_res.vector, self.provider.dimensions)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "embedding_failed: game_id=%d provider=%s model=%s error=%s latency_ms=%.2f",
                game_id,
                self.provider.provider,
                self.provider.model,
                exc,
                latency_ms,
            )
            return EmbeddingRefreshResult(
                game_id=game_id,
                status="failed",
                error=str(exc),
            )

        # 5. Persist embedding in PostgreSQL/pgvector
        now = datetime.now(UTC)
        if not existing_embedding:
            new_embedding = GameEmbedding(
                game_id=game_id,
                embedding=embed_res.vector,
                provider=self.provider.provider,
                model=self.provider.model,
                dimensions=self.provider.dimensions,
                input_fingerprint=fingerprint,
                input_version=settings.EMBEDDING_INPUT_VERSION,
                input_tokens=embed_res.input_tokens,
                generated_at=now,
                updated_at=now,
            )
            self.db.add(new_embedding)
        else:
            existing_embedding.embedding = embed_res.vector
            existing_embedding.provider = self.provider.provider
            existing_embedding.model = self.provider.model
            existing_embedding.dimensions = self.provider.dimensions
            existing_embedding.input_fingerprint = fingerprint
            existing_embedding.input_version = settings.EMBEDDING_INPUT_VERSION
            existing_embedding.input_tokens = embed_res.input_tokens
            existing_embedding.generated_at = now
            existing_embedding.updated_at = now

        await self.db.flush()
        await self.db.commit()

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "embedding_generated: game_id=%d provider=%s model=%s dimensions=%d input_tokens=%s latency_ms=%.2f",
            game_id,
            self.provider.provider,
            self.provider.model,
            self.provider.dimensions,
            embed_res.input_tokens,
            latency_ms,
        )

        return EmbeddingRefreshResult(
            game_id=game_id,
            status="generated",
            provider=self.provider.provider,
            model=self.provider.model,
            dimensions=self.provider.dimensions,
            input_fingerprint=fingerprint,
            input_tokens=embed_res.input_tokens,
        )

    async def embed_all(self, force: bool = False) -> dict[str, Any]:
        """
        Iterates across all games currently stored in PostgreSQL and refreshes their embeddings.
        Maintains isolated error boundaries per game.
        """
        stmt = select(Game.id).order_by(Game.id.asc())
        res = await self.db.execute(stmt)
        game_ids = list(res.scalars().all())

        generated_count = 0
        skipped_count = 0
        failed_count = 0
        results: list[dict[str, Any]] = []

        for gid in game_ids:
            try:
                res_single = await self.refresh_game_embedding(gid, force=force)
                if res_single.status == "generated":
                    generated_count += 1
                elif res_single.status == "skipped_unchanged":
                    skipped_count += 1
                else:
                    failed_count += 1

                results.append({
                    "game_id": gid,
                    "status": res_single.status,
                    "provider": res_single.provider,
                    "model": res_single.model,
                    "dimensions": res_single.dimensions,
                    "error": res_single.error,
                })
            except Exception as exc:
                failed_count += 1
                results.append({
                    "game_id": gid,
                    "status": "failed",
                    "error": str(exc),
                })

        return {
            "total": len(game_ids),
            "generated": generated_count,
            "skipped_unchanged": skipped_count,
            "failed": failed_count,
            "results": results,
        }
