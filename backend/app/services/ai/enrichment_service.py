import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.game import Game
from app.models.platform import Platform
from app.models.review import Review
from app.models.summary import GameReviewSummary
from app.services.ai.sampling import (
    classify_sentiment,
    compute_input_fingerprint,
    select_reviews_for_summary,
)
from app.services.ai.summarizer import ReviewSummarizer, get_summarizer
from app.services.crawler.dtos import ReviewForSummary
from app.services.crawler.parser import _platform_slug_to_name
from app.services.crawler.source import MetacriticSource

logger = logging.getLogger(__name__)


def _parse_published_date(val: str | None) -> datetime | None:
    if not val:
        return None
    cleaned = val.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


@dataclass
class SummaryExecutionResult:
    review_type: str
    status: str  # "generated", "skipped_unchanged", "no_reviews", "error"
    summary_id: int | None = None
    input_fingerprint: str | None = None
    error: str | None = None


@dataclass
class EnrichmentResult:
    game_id: int
    critic_reviews_ingested: int = 0
    user_reviews_ingested: int = 0
    critic_summary_status: str = "no_reviews"
    user_summary_status: str = "no_reviews"
    critic_summary_id: int | None = None
    user_summary_id: int | None = None
    errors: list[str] = field(default_factory=list)


class ReviewEnrichmentService:
    """
    Coordinates review ingestion from Metacritic, deterministic sampling,
    fingerprint-based cost control, and AI summary generation.
    Strictly separates critic and user reviews.
    """

    def __init__(
        self,
        db: AsyncSession,
        source: MetacriticSource | None = None,
        summarizer: ReviewSummarizer | None = None,
    ):
        self.db = db
        if source is None:
            from app.services.crawler.client import MetacriticClient

            source = MetacriticClient()
        self.source = source
        self.summarizer = summarizer or get_summarizer()


    async def _get_or_create_platform(self, platform_slug: str) -> Platform:
        slug_clean = platform_slug.lower().strip()
        stmt = select(Platform).where(Platform.slug == slug_clean)
        res = await self.db.execute(stmt)
        p = res.scalar_one_or_none()
        if not p:
            p = Platform(
                name=_platform_slug_to_name(slug_clean),
                slug=slug_clean,
            )
            self.db.add(p)
            await self.db.flush()
        return p

    async def ingest_reviews_for_type(
        self,
        game: Game,
        review_type: str,  # "critic" or "user"
        max_items: int | None = None,
    ) -> int:
        """
        Ingest reviews of a specific type (critic or user) for a game.
        Paginates until max_items or no next page.
        Upserts each review on (game_id, review_type, external_id).
        """
        limit = max_items or (
            settings.CRITIC_REVIEW_MAX_ITEMS if review_type == "critic" else settings.USER_REVIEW_MAX_ITEMS
        )
        slug = game.metacritic_slug

        page = 1
        ingested_count = 0
        has_next = True

        while has_next and ingested_count < limit:
            try:
                if review_type == "critic":
                    review_page = await self.source.get_critic_reviews(slug=slug, page=page)
                else:
                    review_page = await self.source.get_user_reviews(slug=slug, page=page)
            except Exception as exc:
                logger.error(
                    "Failed to fetch %s reviews page %d for '%s': %s",
                    review_type,
                    page,
                    slug,
                    exc,
                )
                raise RuntimeError(
                    f"Failed to fetch {review_type} reviews page {page} for '{slug}': {exc}"
                ) from exc


            if not review_page.reviews:
                break

            for item in review_page.reviews:
                if ingested_count >= limit:
                    break

                # Resolve platform if present
                platform_id = None
                if item.platform_slug:
                    platform = await self._get_or_create_platform(item.platform_slug)
                    platform_id = platform.id

                # Check if review already exists
                stmt = select(Review).where(
                    Review.game_id == game.id,
                    Review.review_type == review_type,
                    Review.external_id == item.external_id,
                )
                res = await self.db.execute(stmt)
                existing = res.scalar_one_or_none()

                pub_date = _parse_published_date(item.published_at)

                if not existing:
                    review_row = Review(
                        game_id=game.id,
                        platform_id=platform_id,
                        review_type=review_type,
                        external_id=item.external_id,
                        author=item.author,
                        rating=item.score,
                        body=item.body,
                        source_url=item.source_url,
                        content_hash=item.content_hash,
                        published_at=pub_date,
                    )
                    self.db.add(review_row)
                else:
                    # Update mutable fields
                    existing.author = item.author
                    existing.rating = item.score
                    existing.body = item.body
                    existing.source_url = item.source_url
                    existing.content_hash = item.content_hash
                    existing.platform_id = platform_id
                    if pub_date:
                        existing.published_at = pub_date

                ingested_count += 1

            await self.db.flush()

            has_next = review_page.has_next_page
            page += 1

        return ingested_count

    async def summarize_game_reviews(
        self,
        game: Game,
        review_type: str,  # "critic" or "user"
    ) -> SummaryExecutionResult:
        """
        Generate or update summary for critic or user reviews.
        Uses deterministic sampling and fingerprint comparison to skip LLM calls.
        """
        # 1. Fetch existing reviews from DB for this game and review_type
        stmt = (
            select(Review)
            .options(selectinload(Review.platform))
            .where(
                Review.game_id == game.id,
                Review.review_type == review_type,
            )
        )
        res = await self.db.execute(stmt)
        db_reviews = list(res.scalars().all())


        if not db_reviews:
            return SummaryExecutionResult(
                review_type=review_type,
                status="no_reviews",
            )

        # 2. Convert to ReviewForSummary DTOs
        candidates: list[ReviewForSummary] = []
        for r in db_reviews:
            if not r.body or not r.body.strip():
                continue
            plat_slug = r.platform.slug if r.platform else None
            sentiment = classify_sentiment(r.rating, review_type)
            candidates.append(
                ReviewForSummary(
                    external_id=r.external_id or f"{review_type}-{r.id}",
                    review_type=review_type,
                    author=r.author,
                    score=r.rating,
                    body=r.body,
                    platform_slug=plat_slug,
                    sentiment_category=sentiment,
                    content_hash=r.content_hash or "",
                )
            )

        if not candidates:
            return SummaryExecutionResult(
                review_type=review_type,
                status="no_reviews",
            )

        # 3. Deterministically sample reviews
        sample = select_reviews_for_summary(
            candidates,
            max_count=settings.SUMMARY_SAMPLE_SIZE,
        )

        # 4. Compute input fingerprint
        model_name = getattr(self.summarizer, "model", settings.LLM_MODEL)
        prompt_version = getattr(self.summarizer, "prompt_version", settings.SUMMARY_PROMPT_VERSION)
        fingerprint = compute_input_fingerprint(
            reviews=sample,
            prompt_version=prompt_version,
            model=model_name,
        )

        # 5. Check if summary already exists with same fingerprint
        stmt_sum = select(GameReviewSummary).where(
            GameReviewSummary.game_id == game.id,
            GameReviewSummary.review_type == review_type,
        )
        res_sum = await self.db.execute(stmt_sum)
        existing_summary = res_sum.scalar_one_or_none()

        if existing_summary and existing_summary.input_fingerprint == fingerprint:
            logger.info(
                "Skipping LLM call for game %d (%s) %s reviews: fingerprint unchanged (%s)",
                game.id,
                game.title,
                review_type,
                fingerprint[:8],
            )
            return SummaryExecutionResult(
                review_type=review_type,
                status="skipped_unchanged",
                summary_id=existing_summary.id,
                input_fingerprint=fingerprint,
            )

        # 6. Call summarizer
        try:
            summary_result = await self.summarizer.summarize(
                game_title=game.title,
                review_type=review_type,
                reviews=sample,
                fingerprint=fingerprint,
            )
        except Exception as exc:
            logger.error(
                "Summarizer failed for game %d (%s) %s: %s",
                game.id,
                game.title,
                review_type,
                exc,
            )
            return SummaryExecutionResult(
                review_type=review_type,
                status="error",
                error=str(exc),
            )

        # 7. Upsert GameReviewSummary
        now = datetime.now(UTC)
        if not existing_summary:
            summary_row = GameReviewSummary(
                game_id=game.id,
                review_type=review_type,
                summary=summary_result.summary,
                likes=summary_result.likes,
                dislikes=summary_result.dislikes,
                review_count_used=summary_result.review_count_used,
                total_reviews_seen=len(db_reviews),
                input_fingerprint=fingerprint,
                provider=summary_result.provider,
                model=summary_result.model,
                prompt_version=summary_result.prompt_version,
                input_tokens=summary_result.input_tokens,
                output_tokens=summary_result.output_tokens,
            )
            self.db.add(summary_row)
            await self.db.flush()
            summary_id = summary_row.id
        else:
            existing_summary.summary = summary_result.summary
            existing_summary.likes = summary_result.likes
            existing_summary.dislikes = summary_result.dislikes
            existing_summary.review_count_used = summary_result.review_count_used
            existing_summary.total_reviews_seen = len(db_reviews)
            existing_summary.input_fingerprint = fingerprint
            existing_summary.provider = summary_result.provider
            existing_summary.model = summary_result.model
            existing_summary.prompt_version = summary_result.prompt_version
            existing_summary.input_tokens = summary_result.input_tokens
            existing_summary.output_tokens = summary_result.output_tokens
            existing_summary.updated_at = now
            await self.db.flush()
            summary_id = existing_summary.id

        # 8. Update game cache field
        if review_type == "critic":
            game.critic_summary = summary_result.summary
        else:
            game.user_summary = summary_result.summary
        game.updated_at = now
        await self.db.flush()

        return SummaryExecutionResult(
            review_type=review_type,
            status="generated",
            summary_id=summary_id,
            input_fingerprint=fingerprint,
        )

    async def enrich_and_summarize(self, game_id: int) -> EnrichmentResult:
        """
        Orchestrate full review enrichment for a game:
        1. Ingest critic reviews (isolated).
        2. Ingest user reviews (isolated).
        3. Summarize critic reviews (fingerprint-checked).
        4. Summarize user reviews (fingerprint-checked).
        5. Commit transaction.
        """
        stmt = select(Game).where(Game.id == game_id)
        res = await self.db.execute(stmt)
        game = res.scalar_one_or_none()
        if not game:
            raise ValueError(f"Game with id {game_id} not found")

        result = EnrichmentResult(game_id=game.id)

        # 1. Critic reviews ingestion
        try:
            result.critic_reviews_ingested = await self.ingest_reviews_for_type(game, "critic")
        except Exception as exc:
            logger.error("Error ingesting critic reviews for game %d: %s", game.id, exc)
            result.errors.append(f"Critic ingestion failed: {exc}")

        # 2. User reviews ingestion
        try:
            result.user_reviews_ingested = await self.ingest_reviews_for_type(game, "user")
        except Exception as exc:
            logger.error("Error ingesting user reviews for game %d: %s", game.id, exc)
            result.errors.append(f"User ingestion failed: {exc}")

        # Commit ingested reviews so they are safely persisted before summarization
        await self.db.commit()

        # Re-fetch game to ensure clean session state
        res = await self.db.execute(stmt)
        game = res.scalar_one_or_none()
        if not game:
            raise ValueError(f"Game {game_id} disappeared during enrichment")

        # 3. Critic reviews summary
        critic_sum = await self.summarize_game_reviews(game, "critic")
        result.critic_summary_status = critic_sum.status
        result.critic_summary_id = critic_sum.summary_id
        if critic_sum.error:
            result.errors.append(f"Critic summarization: {critic_sum.error}")

        # 4. User reviews summary
        user_sum = await self.summarize_game_reviews(game, "user")
        result.user_summary_status = user_sum.status
        result.user_summary_id = user_sum.summary_id
        if user_sum.error:
            result.errors.append(f"User summarization: {user_sum.error}")

        # Final commit for summaries
        await self.db.commit()

        return result
