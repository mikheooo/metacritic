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
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return cast(T, executor.submit(asyncio.run, coro).result())
    return asyncio.run(coro)


@celery_app.task(name="tasks.ping")
def ping() -> str:
    """Diagnostic Celery task verifying broker and worker connectivity."""
    logger.info("Executing diagnostic ping task")
    return "pong"


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
