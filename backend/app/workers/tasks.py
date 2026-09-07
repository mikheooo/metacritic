import asyncio
import concurrent.futures
import logging
from collections.abc import Coroutine
from typing import Any, cast

from app.db.session import AsyncSessionLocal
from app.services.crawler.ingestion_service import IngestionService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async_safely[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine safely from sync Celery worker or running event loops."""

    async def _wrapper() -> T:
        try:
            return await coro
        finally:
            from app.db.session import async_engine

            await async_engine.dispose()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return cast(T, executor.submit(asyncio.run, _wrapper()).result())
    return asyncio.run(_wrapper())


@celery_app.task(name="tasks.ping")
def ping() -> str:
    """Diagnostic Celery task verifying broker and worker connectivity."""
    logger.info("Executing diagnostic ping task")
    return "pong"


@celery_app.task(bind=True, name="tasks.process_metacritic_pipeline")
def process_metacritic_pipeline(
    self: Any,
    limit: int = 20,
    trigger_type: str = "scheduled",
    run_id: int | None = None,
) -> dict[str, Any]:
    """
    Canonical Celery task for Metacritic end-to-end processing pipeline.
    Orchestrates candidate discovery, game ingestion, reviews enrichment,
    AI summaries, semantic embeddings, and similarity cache rebuilding.
    Used by both Celery Beat hourly scheduler and manual 'Run Now' trigger.
    """
    task_id = getattr(self.request, "id", None) if hasattr(self, "request") else None
    logger.info(
        "Executing tasks.process_metacritic_pipeline (task_id=%s, limit=%d, trigger=%s, run_id=%s)",
        task_id,
        limit,
        trigger_type,
        run_id,
    )

    async def _execute() -> dict[str, Any]:
        from app.services.crawler.pipeline_service import MetacriticPipelineService

        async with AsyncSessionLocal() as db_session:
            service = MetacriticPipelineService(db=db_session)
            res = await service.run_pipeline(
                limit=limit,
                trigger_type=trigger_type,
                run_id=run_id,
                task_id=task_id,
            )
            return {
                "crawl_run_id": res.crawl_run_id,
                "status": res.status,
                "stage": res.stage,
                "discovered_count": res.discovered_count,
                "processed_count": res.processed_count,
                "failed_count": res.failed_count,
                "reviews_processed_count": res.reviews_processed_count,
                "summaries_generated_count": res.summaries_generated_count,
                "embeddings_generated_count": res.embeddings_generated_count,
                "errors": res.errors,
            }

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.process_metacritic_batch")
def process_metacritic_batch(
    limit: int = 20,
    trigger_type: str = "scheduled",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Celery task entrypoint for Metacritic ingestion.
    Delegates execution to the application IngestionService layer.
    """
    logger.info(
        "Starting Metacritic batch crawl task (limit=%d, trigger=%s, dry_run=%s)",
        limit,
        trigger_type,
        dry_run,
    )

    async def _execute() -> dict[str, Any]:
        async with AsyncSessionLocal() as db_session:
            service = IngestionService(db=db_session)
            result = await service.run_crawl(
                limit=limit,
                trigger_type=trigger_type,
                dry_run=dry_run,
            )
            return {
                "crawl_run_id": result.crawl_run_id,
                "status": result.status,
                "phase": result.phase,
                "processed_count": result.processed_count,
                "failed_count": result.failed_count,
                "eligible_count": result.eligible_count,
                "candidates": result.candidates,
                "errors": result.errors,
                "dry_run": result.dry_run,
            }

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.enrich_game_reviews")
def enrich_game_reviews(game_id: int) -> dict[str, Any]:
    """
    Celery task to ingest reviews and generate AI summaries for a specific game.
    """
    logger.info("Starting review enrichment task for game_id=%d", game_id)

    async def _execute() -> dict[str, Any]:
        from app.services.ai import ReviewEnrichmentService

        async with AsyncSessionLocal() as db_session:
            service = ReviewEnrichmentService(db=db_session)
            res = await service.enrich_and_summarize(game_id=game_id)
            return {
                "game_id": res.game_id,
                "critic_reviews_ingested": res.critic_reviews_ingested,
                "user_reviews_ingested": res.user_reviews_ingested,
                "critic_summary_status": res.critic_summary_status,
                "user_summary_status": res.user_summary_status,
                "critic_summary_id": res.critic_summary_id,
                "user_summary_id": res.user_summary_id,
                "errors": res.errors,
            }

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.summarize_game_reviews")
def summarize_game_reviews(game_id: int, review_type: str = "both") -> dict[str, Any]:
    """
    Celery task to summarize reviews (without re-ingesting) for a specific game.
    review_type: "critic", "user", or "both".
    """
    logger.info("Starting review summarization task for game_id=%d, type=%s", game_id, review_type)

    async def _execute() -> dict[str, Any]:
        from sqlalchemy import select

        from app.models.game import Game
        from app.services.ai import ReviewEnrichmentService

        async with AsyncSessionLocal() as db_session:
            stmt = select(Game).where(Game.id == game_id)
            game_res = await db_session.execute(stmt)
            game = game_res.scalar_one_or_none()
            if not game:
                raise ValueError(f"Game {game_id} not found")

            service = ReviewEnrichmentService(db=db_session)
            results = {}

            if review_type in ("critic", "both"):
                c_res = await service.summarize_game_reviews(game, "critic")
                results["critic"] = {
                    "status": c_res.status,
                    "summary_id": c_res.summary_id,
                    "fingerprint": c_res.input_fingerprint,
                    "error": c_res.error,
                }

            if review_type in ("user", "both"):
                u_res = await service.summarize_game_reviews(game, "user")
                results["user"] = {
                    "status": u_res.status,
                    "summary_id": u_res.summary_id,
                    "fingerprint": u_res.input_fingerprint,
                    "error": u_res.error,
                }

            await db_session.commit()
            return {"game_id": game_id, "results": results}

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.embed_game")
def embed_game(game_id: int, force: bool = False) -> dict[str, Any]:
    """
    Celery task to generate or refresh semantic embedding for a specific game.
    """
    logger.info("Starting embedding task for game_id=%d (force=%s)", game_id, force)

    async def _execute() -> dict[str, Any]:
        from app.services.ai import GameEmbeddingService

        async with AsyncSessionLocal() as db_session:
            service = GameEmbeddingService(db=db_session)
            res = await service.refresh_game_embedding(game_id=game_id, force=force)
            return {
                "game_id": res.game_id,
                "status": res.status,
                "provider": res.provider,
                "model": res.model,
                "dimensions": res.dimensions,
                "fingerprint": res.input_fingerprint,
                "input_tokens": res.input_tokens,
                "error": res.error,
            }

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.embed_all_games")
def embed_all_games(force: bool = False) -> dict[str, Any]:
    """
    Celery task to generate/refresh embeddings for all games in the catalog.
    """
    logger.info("Starting batch embedding task for all games (force=%s)", force)

    async def _execute() -> dict[str, Any]:
        from app.services.ai import GameEmbeddingService

        async with AsyncSessionLocal() as db_session:
            service = GameEmbeddingService(db=db_session)
            return await service.embed_all(force=force)

    return _run_async_safely(_execute())


@celery_app.task(name="tasks.rebuild_similar_games")
def rebuild_similar_games() -> dict[str, Any]:
    """
    Celery task to rebuild recommendation cache for all embedded games in the catalog.
    """
    logger.info("Starting similarity cache rebuild task")

    async def _execute() -> dict[str, Any]:
        from app.services.ai import SimilarGamesService

        async with AsyncSessionLocal() as db_session:
            service = SimilarGamesService(db=db_session)
            return await service.rebuild_all()

    return _run_async_safely(_execute())
