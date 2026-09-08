import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.review import Review
from app.services.ai.translator import ContentTranslator, get_translator, is_already_russian

logger = logging.getLogger(__name__)


def compute_text_hash(text: str) -> str:
    """Compute deterministic SHA-256 fingerprint of normalized source text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


@dataclass
class DescriptionTranslationResult:
    status: str  # "translated", "skipped_unchanged", "already_russian", "no_source", "error"
    error: str | None = None


@dataclass
class ReviewTranslationStats:
    processed: int = 0
    translated: int = 0
    skipped_unchanged: int = 0
    already_russian: int = 0
    failed: int = 0


class ContentTranslationService:
    """
    Coordinates translation of game descriptions and review snippets into Russian.
    Enforces strict SHA-256 fingerprinting for cost control and idempotency.
    Capped to displayed snippets (top N per category) to prevent unnecessary LLM cost.
    """

    def __init__(
        self,
        db: AsyncSession,
        translator: ContentTranslator | None = None,
    ) -> None:
        self.db = db
        self.translator = translator or get_translator()

    async def translate_game_description(self, game: Game) -> DescriptionTranslationResult:
        """
        Translate game description to Russian if missing or changed.
        Idempotent: skips unchanged content using SHA-256 hash.
        """
        if not game.description or not game.description.strip():
            return DescriptionTranslationResult(status="no_source")

        cleaned_text = game.description.strip()
        current_hash = compute_text_hash(cleaned_text)

        # Idempotency check: translation already exists and source hash matches
        if game.description_ru and game.description_source_hash == current_hash:
            return DescriptionTranslationResult(status="skipped_unchanged")

        # Check if source text is already predominantly Russian
        if is_already_russian(cleaned_text):
            game.description_ru = cleaned_text
            game.description_source_hash = current_hash
            await self.db.flush()
            return DescriptionTranslationResult(status="already_russian")

        try:
            translated = await self.translator.translate_text(
                cleaned_text,
                context_type="description",
            )
            game.description_ru = translated.strip()
            game.description_source_hash = current_hash
            await self.db.flush()
            return DescriptionTranslationResult(status="translated")
        except Exception as exc:
            logger.error(
                "Failed to translate description for game '%s' (id: %s): %s",
                game.title,
                game.id,
                exc,
                exc_info=True,
            )
            return DescriptionTranslationResult(status="error", error=str(exc))

    async def translate_game_reviews(
        self,
        game: Game,
        limit_per_type: int = 10,
    ) -> ReviewTranslationStats:
        """
        Translate top displayed reviews for a game (both critic and user).
        Limits translation to top N snippets to minimize LLM token expense.
        """
        stats = ReviewTranslationStats()

        for r_type in ("critic", "user"):
            stmt = (
                select(Review)
                .where(
                    Review.game_id == game.id,
                    Review.review_type == r_type,
                    Review.body.is_not(None),
                    Review.body != "",
                )
                .order_by(Review.rating.desc().nullslast(), Review.id.asc())
                .limit(limit_per_type)
            )
            res = await self.db.execute(stmt)
            reviews = list(res.scalars().all())

            for rev in reviews:
                stats.processed += 1
                if not rev.body or not rev.body.strip():
                    continue

                cleaned_body = rev.body.strip()
                current_hash = compute_text_hash(cleaned_body)

                # Skip if already translated with matching hash
                if rev.body_ru and rev.body_source_hash == current_hash:
                    stats.skipped_unchanged += 1
                    continue

                # Check if already Russian
                if is_already_russian(cleaned_body):
                    rev.body_ru = cleaned_body
                    rev.body_source_hash = current_hash
                    stats.already_russian += 1
                    continue

                try:
                    translated = await self.translator.translate_text(
                        cleaned_body,
                        context_type="review",
                    )
                    rev.body_ru = translated.strip()
                    rev.body_source_hash = current_hash
                    stats.translated += 1
                except Exception as exc:
                    stats.failed += 1
                    logger.warning(
                        "Failed to translate review id %s for game '%s': %s",
                        rev.id,
                        game.title,
                        exc,
                    )

        await self.db.flush()
        return stats

    async def translate_game_content(
        self,
        game: Game,
        limit_reviews_per_type: int = 10,
    ) -> dict[str, object]:
        """Translate both description and top reviews for a game."""
        desc_res = await self.translate_game_description(game)
        review_stats = await self.translate_game_reviews(
            game,
            limit_per_type=limit_reviews_per_type,
        )
        return {
            "description_status": desc_res.status,
            "reviews_processed": review_stats.processed,
            "reviews_translated": review_stats.translated,
            "reviews_skipped_unchanged": review_stats.skipped_unchanged,
            "reviews_already_russian": review_stats.already_russian,
            "reviews_failed": review_stats.failed,
        }
