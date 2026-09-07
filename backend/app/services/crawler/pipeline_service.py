import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_current_date, get_current_datetime
from app.core.config import settings
from app.models.crawl import CrawlRun, CrawlRunEvent
from app.models.game import Game
from app.schemas.crawl import PipelineStage
from app.services.ai import GameEmbeddingService, ReviewEnrichmentService, SimilarGamesService
from app.services.crawler.client import MetacriticClient
from app.services.crawler.ingestion_service import IngestionService
from app.services.crawler.lock import CrawlAlreadyRunningError, CrawlLock
from app.services.crawler.source import MetacriticSource

logger = logging.getLogger(__name__)

# Pattern to detect potential sensitive keys
SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|secret|token|password|auth)", re.IGNORECASE)


def sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Strips secrets, raw embedding vectors, large text dumps, HTML,
    and prompts from event payloads.
    """
    if payload is None:
        return None

    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        # Strip secret keys
        if SENSITIVE_KEY_RE.search(key):
            continue

        # Strip vector arrays or large numeric collections
        if key in ("vector", "embedding", "raw_vector", "html", "raw_html", "full_prompt"):
            continue

        # Truncate strings to safe size
        if isinstance(value, str):
            if len(value) > 250:
                sanitized[key] = value[:247] + "..."
            else:
                sanitized[key] = value
        elif isinstance(value, (int, float, bool)) or value is None:
            sanitized[key] = value
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)
        elif isinstance(value, (list, tuple)):
            # If list contains numbers/strings, keep reasonable length
            if len(value) > 10:
                sanitized[key] = [str(x)[:50] for x in value[:10]] + [f"...+{len(value)-10} more"]
            else:
                sanitized[key] = value
        else:
            sanitized[key] = str(value)[:100]

    return sanitized


@dataclass
class PipelineExecutionResult:
    crawl_run_id: int | None
    status: str
    stage: str
    target_count: int
    discovered_count: int
    processed_count: int
    failed_count: int
    reviews_processed_count: int
    summaries_generated_count: int
    embeddings_generated_count: int
    errors: list[str] = field(default_factory=list)


class MetacriticPipelineService:
    """
    Canonical production orchestrator for Metacritic ingestion, review enrichment,
    AI summaries, semantic embeddings, and similarity cache rebuilding.
    Enforces per-game failure isolation boundaries, daily ledger correctness,
    cost controls, and durable event stream persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
        source: MetacriticSource | None = None,
        enrichment_service: ReviewEnrichmentService | None = None,
        embedding_service: GameEmbeddingService | None = None,
        similarity_service: SimilarGamesService | None = None,
    ) -> None:
        self.db = db
        self.source = source or MetacriticClient()
        self.ingestion_service = IngestionService(db=self.db, source=self.source)
        self.enrichment_service = enrichment_service or ReviewEnrichmentService(
            db=self.db, source=self.source
        )
        self.embedding_service = embedding_service or GameEmbeddingService(db=self.db)
        self.similarity_service = similarity_service or SimilarGamesService(db=self.db)

    async def emit_event(
        self,
        crawl_run_id: int,
        event_type: str,
        stage: str,
        message: str,
        game_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CrawlRunEvent:
        """Persist a sanitized event to the append-only crawl_run_events table."""
        clean_payload = sanitize_payload(payload)
        now = datetime.now(UTC)
        event = CrawlRunEvent(
            crawl_run_id=crawl_run_id,
            event_type=event_type,
            stage=stage,
            game_id=game_id,
            message=message,
            payload=clean_payload,
            created_at=now,
        )
        self.db.add(event)
        await self.db.flush()
        logger.info(
            "[Run #%d][%s][%s] %s (game_id=%s)",
            crawl_run_id,
            stage,
            event_type,
            message,
            game_id,
        )
        return event

    async def run_pipeline(
        self,
        limit: int | None = None,
        trigger_type: str = "scheduled",
        run_id: int | None = None,
        task_id: str | None = None,
    ) -> PipelineExecutionResult:
        """
        Execute the full Metacritic pipeline under the authoritative Redis distributed lock.
        """
        batch_limit = limit or settings.CRAWL_BATCH_LIMIT
        today = get_current_date()
        errors: list[str] = []

        # 1. Acquire Distributed Concurrency Lock
        try:
            async with CrawlLock():
                now = get_current_datetime()
                crawl_run: CrawlRun

                # Fetch existing run (if pre-created in pending state by API) or create new
                if run_id:
                    stmt = select(CrawlRun).where(CrawlRun.id == run_id)
                    res = await self.db.execute(stmt)
                    run_obj = res.scalar_one_or_none()
                    if not run_obj:
                        raise ValueError(f"CrawlRun #{run_id} not found in database")
                    crawl_run = run_obj
                    crawl_run.status = "running"
                    crawl_run.current_stage = PipelineStage.DISCOVERING.value
                    crawl_run.started_at = now
                    crawl_run.heartbeat_at = now
                    if task_id:
                        crawl_run.task_id = task_id
                else:
                    crawl_run = CrawlRun(
                        task_id=task_id,
                        status="running",
                        trigger_type=trigger_type,
                        target_count=batch_limit,
                        discovered_count=0,
                        processed_count=0,
                        failed_count=0,
                        reviews_processed_count=0,
                        summaries_generated_count=0,
                        embeddings_generated_count=0,
                        current_stage=PipelineStage.DISCOVERING.value,
                        started_at=now,
                        heartbeat_at=now,
                        created_at=now,
                    )
                    self.db.add(crawl_run)
                    await self.db.commit()
                    await self.db.refresh(crawl_run)

                await self.emit_event(
                    crawl_run_id=crawl_run.id,
                    event_type="run_started",
                    stage=PipelineStage.DISCOVERING.value,
                    message=f"Metacritic pipeline started (trigger: {trigger_type}, limit: {batch_limit})",
                    payload={"trigger_type": trigger_type, "limit": batch_limit},
                )
                await self.db.commit()

                # 2. Candidate Discovery Phase
                await self.emit_event(
                    crawl_run_id=crawl_run.id,
                    event_type="discovery_started",
                    stage=PipelineStage.DISCOVERING.value,
                    message="Discovering candidate games according to daily cursor semantics",
                )
                await self.db.commit()

                try:
                    daily_state = await self.ingestion_service.get_or_create_daily_state(today)
                    processed_today = await self.ingestion_service.get_processed_ids_today(today)

                    candidates, new_phase, new_page = (
                        await self.ingestion_service.collect_eligible_candidates(
                            limit=batch_limit,
                            processing_date=today,
                            state=daily_state,
                            processed_today=processed_today,
                        )
                    )

                    crawl_run.discovered_count = len(candidates)
                    crawl_run.heartbeat_at = get_current_datetime()
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="discovery_completed",
                        stage=PipelineStage.DISCOVERING.value,
                        message=f"Discovered {len(candidates)} eligible games for processing",
                        payload={"discovered_count": len(candidates), "phase": new_phase, "page": new_page},
                    )
                    await self.db.commit()

                except Exception as exc:
                    err_msg = f"Candidate discovery fatal failure: {exc}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)
                    crawl_run.status = "failed"
                    crawl_run.current_stage = PipelineStage.FAILED.value
                    crawl_run.error_summary = err_msg
                    crawl_run.finished_at = get_current_datetime()
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="run_failed",
                        stage=PipelineStage.FAILED.value,
                        message=err_msg,
                        payload={"error": str(exc)},
                    )
                    await self.db.commit()
                    return PipelineExecutionResult(
                        crawl_run_id=crawl_run.id,
                        status="failed",
                        stage=PipelineStage.FAILED.value,
                        target_count=batch_limit,
                        discovered_count=0,
                        processed_count=0,
                        failed_count=0,
                        reviews_processed_count=0,
                        summaries_generated_count=0,
                        embeddings_generated_count=0,
                        errors=errors,
                    )

                # 3. Per-Game Processing Loop with Isolated Failure Boundaries
                for candidate in candidates:
                    game_had_error = False
                    game_id: int | None = None
                    game_title = candidate.title

                    crawl_run.current_stage = PipelineStage.INGESTING.value
                    crawl_run.current_game_title = game_title
                    crawl_run.heartbeat_at = get_current_datetime()

                    # --- Substage A: Game Ingestion ---
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="game_started",
                        stage=PipelineStage.INGESTING.value,
                        message=f"Processing candidate '{game_title}'",
                        payload={"title": game_title, "url": candidate.url},
                    )
                    await self.db.commit()

                    try:
                        game_details = await self.source.get_game_details(candidate.url)
                        async with self.db.begin_nested():
                            game = await self.ingestion_service.upsert_game_details(
                                details=game_details,
                                crawl_run_id=crawl_run.id,
                                processing_date=today,
                            )
                        await self.db.commit()

                        game_id = game.id
                        crawl_run.current_game_id = game.id
                        crawl_run.current_game_title = game.title
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="game_persisted",
                            stage=PipelineStage.INGESTING.value,
                            message=f"Game '{game.title}' persisted successfully",
                            game_id=game.id,
                            payload={"title": game.title, "slug": game.metacritic_slug},
                        )
                        await self.db.commit()

                    except Exception as exc:
                        await self.db.rollback()
                        err_msg = f"Game ingestion failed for '{game_title}': {exc}"
                        logger.error(err_msg, exc_info=True)
                        errors.append(err_msg)
                        crawl_run.failed_count += 1
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="game_failed",
                            stage=PipelineStage.INGESTING.value,
                            message=err_msg,
                            payload={"error": str(exc)},
                        )
                        await self.db.commit()
                        continue  # Cannot proceed to reviews/summaries/embedding for unpersisted game

                    # Re-query game to have fresh session state
                    stmt_g = select(Game).where(Game.id == game_id)
                    res_g = await self.db.execute(stmt_g)
                    game = res_g.scalar_one()

                    # --- Substage B: Reviews Enrichment ---
                    crawl_run.current_stage = PipelineStage.REVIEWS.value
                    crawl_run.heartbeat_at = get_current_datetime()
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="reviews_started",
                        stage=PipelineStage.REVIEWS.value,
                        message=f"Fetching reviews for '{game.title}'",
                        game_id=game.id,
                    )
                    await self.db.commit()

                    c_cnt = 0
                    u_cnt = 0
                    try:
                        c_cnt = await self.enrichment_service.ingest_reviews_for_type(game, "critic")
                        u_cnt = await self.enrichment_service.ingest_reviews_for_type(game, "user")
                        await self.db.commit()

                        crawl_run.reviews_processed_count += (c_cnt + u_cnt)
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="reviews_completed",
                            stage=PipelineStage.REVIEWS.value,
                            message=f"Reviews ingested for '{game.title}' (critic: {c_cnt}, user: {u_cnt})",
                            game_id=game.id,
                            payload={"critic_reviews": c_cnt, "user_reviews": u_cnt},
                        )
                        await self.db.commit()

                    except Exception as exc:
                        await self.db.rollback()
                        game_had_error = True
                        err_msg = f"Review ingestion error for '{game.title}': {exc}"
                        logger.error(err_msg, exc_info=True)
                        errors.append(err_msg)
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="reviews_failed",
                            stage=PipelineStage.REVIEWS.value,
                            message=err_msg,
                            game_id=game.id,
                            payload={"error": str(exc)},
                        )
                        await self.db.commit()

                    # --- Substage C: AI Summarization ---
                    crawl_run.current_stage = PipelineStage.SUMMARIZING.value
                    crawl_run.heartbeat_at = get_current_datetime()

                    # Summarize critic reviews
                    try:
                        c_sum = await self.enrichment_service.summarize_game_reviews(game, "critic")
                        if c_sum.status == "generated":
                            crawl_run.summaries_generated_count += 1
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_completed",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"Generated critic review AI summary for '{game.title}'",
                                game_id=game.id,
                                payload={"review_type": "critic", "status": "generated"},
                            )
                        elif c_sum.status == "skipped_unchanged":
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_skipped",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"Skipped critic summary for '{game.title}' (unchanged fingerprint)",
                                game_id=game.id,
                                payload={"review_type": "critic", "status": "skipped_unchanged"},
                            )
                        elif c_sum.status == "error":
                            game_had_error = True
                            errors.append(f"Critic summary error for '{game.title}': {c_sum.error}")
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_failed",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"Critic summary failed: {c_sum.error}",
                                game_id=game.id,
                                payload={"review_type": "critic", "error": c_sum.error},
                            )

                        # Summarize user reviews
                        u_sum = await self.enrichment_service.summarize_game_reviews(game, "user")
                        if u_sum.status == "generated":
                            crawl_run.summaries_generated_count += 1
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_completed",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"Generated user review AI summary for '{game.title}'",
                                game_id=game.id,
                                payload={"review_type": "user", "status": "generated"},
                            )
                        elif u_sum.status == "skipped_unchanged":
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_skipped",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"Skipped user summary for '{game.title}' (unchanged fingerprint)",
                                game_id=game.id,
                                payload={"review_type": "user", "status": "skipped_unchanged"},
                            )
                        elif u_sum.status == "error":
                            game_had_error = True
                            errors.append(f"User summary error for '{game.title}': {u_sum.error}")
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="summary_failed",
                                stage=PipelineStage.SUMMARIZING.value,
                                message=f"User summary failed: {u_sum.error}",
                                game_id=game.id,
                                payload={"review_type": "user", "error": u_sum.error},
                            )

                        await self.db.commit()

                    except Exception as exc:
                        await self.db.rollback()
                        game_had_error = True
                        err_msg = f"Summarization unexpected error for '{game.title}': {exc}"
                        logger.error(err_msg, exc_info=True)
                        errors.append(err_msg)
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="summary_failed",
                            stage=PipelineStage.SUMMARIZING.value,
                            message=err_msg,
                            game_id=game.id,
                            payload={"error": str(exc)},
                        )
                        await self.db.commit()

                    # --- Substage D: Semantic Embedding ---
                    crawl_run.current_stage = PipelineStage.EMBEDDING.value
                    crawl_run.heartbeat_at = get_current_datetime()
                    try:
                        emb_res = await self.embedding_service.refresh_game_embedding(game.id)
                        if emb_res.status == "generated":
                            crawl_run.embeddings_generated_count += 1
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="embedding_generated",
                                stage=PipelineStage.EMBEDDING.value,
                                message=f"Generated embedding for '{game.title}'",
                                game_id=game.id,
                                payload={"provider": emb_res.provider, "model": emb_res.model},
                            )
                        elif emb_res.status == "skipped_unchanged":
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="embedding_skipped",
                                stage=PipelineStage.EMBEDDING.value,
                                message=f"Skipped embedding for '{game.title}' (unchanged fingerprint)",
                                game_id=game.id,
                                payload={"status": "skipped_unchanged"},
                            )
                        elif emb_res.status == "failed":
                            game_had_error = True
                            errors.append(f"Embedding failed for '{game.title}': {emb_res.error}")
                            await self.emit_event(
                                crawl_run_id=crawl_run.id,
                                event_type="embedding_failed",
                                stage=PipelineStage.EMBEDDING.value,
                                message=f"Embedding generation failed: {emb_res.error}",
                                game_id=game.id,
                                payload={"error": emb_res.error},
                            )

                        await self.db.commit()

                    except Exception as exc:
                        await self.db.rollback()
                        game_had_error = True
                        err_msg = f"Embedding error for '{game.title}': {exc}"
                        logger.error(err_msg, exc_info=True)
                        errors.append(err_msg)
                        await self.emit_event(
                            crawl_run_id=crawl_run.id,
                            event_type="embedding_failed",
                            stage=PipelineStage.EMBEDDING.value,
                            message=err_msg,
                            game_id=game.id,
                            payload={"error": str(exc)},
                        )
                        await self.db.commit()

                    # Increment accurate counters
                    if game_had_error:
                        crawl_run.failed_count += 1
                    else:
                        crawl_run.processed_count += 1
                    await self.db.commit()

                # 4. Batch-Level Similarity Cache Rebuild (Executed Once)
                crawl_run.current_stage = PipelineStage.SIMILARITY.value
                crawl_run.current_game_id = None
                crawl_run.current_game_title = None
                crawl_run.heartbeat_at = get_current_datetime()
                await self.emit_event(
                    crawl_run_id=crawl_run.id,
                    event_type="similarity_started",
                    stage=PipelineStage.SIMILARITY.value,
                    message="Rebuilding similarity recommendations cache for all embedded games",
                )
                await self.db.commit()

                sim_error = False
                try:
                    sim_result = await self.similarity_service.rebuild_all()
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="similarity_completed",
                        stage=PipelineStage.SIMILARITY.value,
                        message=f"Similarity cache rebuild completed ({sim_result.get('total_associations', 0)} links created)",
                        payload={
                            "total_associations": sim_result.get("total_associations", 0),
                            "total_games": sim_result.get("total_games", 0),
                        },
                    )
                    await self.db.commit()
                except Exception as exc:
                    sim_error = True
                    err_msg = f"Similarity rebuild failed: {exc}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)
                    await self.emit_event(
                        crawl_run_id=crawl_run.id,
                        event_type="similarity_failed",
                        stage=PipelineStage.SIMILARITY.value,
                        message=err_msg,
                        payload={"error": str(exc)},
                    )
                    await self.db.commit()

                # 5. Advance Daily Cursor
                try:
                    daily_state = await self.ingestion_service.get_or_create_daily_state(today)
                    daily_state.phase = new_phase
                    daily_state.browse_page = new_page
                    daily_state.updated_at = get_current_datetime()
                    await self.db.commit()
                except Exception as exc:
                    logger.warning("Failed to commit daily state update: %s", exc)

                # 6. Finalize Run Status
                final_status = "completed"
                if crawl_run.failed_count > 0 and crawl_run.processed_count > 0:
                    final_status = "partial"
                elif crawl_run.failed_count > 0 and crawl_run.processed_count == 0:
                    final_status = "failed"
                elif sim_error:
                    final_status = "partial"

                crawl_run.status = final_status
                crawl_run.current_stage = final_status
                crawl_run.finished_at = get_current_datetime()
                crawl_run.heartbeat_at = get_current_datetime()
                if errors:
                    crawl_run.error_summary = "; ".join(errors)[:500]

                final_event_type = f"run_{final_status}"
                await self.emit_event(
                    crawl_run_id=crawl_run.id,
                    event_type=final_event_type,
                    stage=final_status,
                    message=f"Pipeline execution finished with status: {final_status} ({crawl_run.processed_count}/{crawl_run.discovered_count} games successful)",
                    payload={
                        "processed_count": crawl_run.processed_count,
                        "failed_count": crawl_run.failed_count,
                        "discovered_count": crawl_run.discovered_count,
                        "reviews_processed_count": crawl_run.reviews_processed_count,
                        "summaries_generated_count": crawl_run.summaries_generated_count,
                        "embeddings_generated_count": crawl_run.embeddings_generated_count,
                    },
                )
                await self.db.commit()

                return PipelineExecutionResult(
                    crawl_run_id=crawl_run.id,
                    status=final_status,
                    stage=final_status,
                    target_count=batch_limit,
                    discovered_count=crawl_run.discovered_count,
                    processed_count=crawl_run.processed_count,
                    failed_count=crawl_run.failed_count,
                    reviews_processed_count=crawl_run.reviews_processed_count,
                    summaries_generated_count=crawl_run.summaries_generated_count,
                    embeddings_generated_count=crawl_run.embeddings_generated_count,
                    errors=errors,
                )

        except CrawlAlreadyRunningError as exc:
            logger.warning("Pipeline run blocked by concurrency lock: %s", exc)
            if run_id:
                # Fail pre-created run with conflict explanation
                stmt = select(CrawlRun).where(CrawlRun.id == run_id)
                res = await self.db.execute(stmt)
                run_obj = res.scalar_one_or_none()
                if run_obj:
                    run_obj.status = "failed"
                    run_obj.current_stage = PipelineStage.FAILED.value
                    run_obj.error_summary = f"Lock conflict: {exc}"
                    run_obj.finished_at = get_current_datetime()
                    await self.emit_event(
                        crawl_run_id=run_obj.id,
                        event_type="run_failed",
                        stage=PipelineStage.FAILED.value,
                        message=f"Pipeline aborted: {exc}",
                    )
                    await self.db.commit()
            raise
