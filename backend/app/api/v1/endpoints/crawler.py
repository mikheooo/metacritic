import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.models.crawl import CrawlRun, CrawlRunEvent
from app.schemas.crawl import PipelineStage, RunNowResponse
from app.services.crawler.lock import LOCK_KEY
from app.workers.tasks import process_metacritic_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawler", tags=["Crawler"])


@router.post("/run", status_code=status.HTTP_202_ACCEPTED, response_model=RunNowResponse)
async def trigger_run_now(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Manually trigger an on-demand Metacritic pipeline run.
    Always dispatches canonical production batch limit (settings.CRAWL_BATCH_LIMIT = 20).
    Enforces concurrency protection: if a run is currently pending or running,
    or the Redis distributed lock is held, returns HTTP 409 Conflict without creating a fake run.
    """
    limit = settings.CRAWL_BATCH_LIMIT

    # 1. Check for existing active runs in database
    stmt = (
        select(CrawlRun)
        .where(CrawlRun.status.in_(["pending", "running"]))
        .order_by(CrawlRun.id.desc())
    )
    res = await db.execute(stmt)
    active_run = res.scalar_one_or_none()

    if active_run:
        logger.warning(
            "Rejecting manual run: CrawlRun #%d is already in status '%s'",
            active_run.id,
            active_run.status,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "A Metacritic processing run is already active",
                "active_run_id": active_run.id,
            },
        )

    # 2. Check Redis distributed lock status directly
    try:
        r = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        is_locked = await r.exists(LOCK_KEY)
        await r.aclose()
        if is_locked:
            logger.warning("Rejecting manual run: Redis lock '%s' is held", LOCK_KEY)
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "A Metacritic processing run is already active",
                    "active_run_id": None,
                },
            )
    except Exception as exc:
        logger.warning(
            "Could not check Redis lock status directly (%s); proceeding with DB guard", exc
        )

    # 3. Create pending CrawlRun and initial event
    run = CrawlRun(
        status="pending",
        trigger_type="manual",
        target_count=limit,
        current_stage=PipelineStage.QUEUED.value,
        discovered_count=0,
        processed_count=0,
        failed_count=0,
    )
    db.add(run)
    await db.flush()

    event = CrawlRunEvent(
        crawl_run_id=run.id,
        event_type="run_queued",
        stage=PipelineStage.QUEUED.value,
        message=f"Manual pipeline run queued (target_count={limit})",
        payload={"limit": limit, "trigger_type": "manual"},
    )
    db.add(event)
    await db.commit()
    await db.refresh(run)

    # 4. Dispatch Celery task
    task_id = None
    try:
        task = process_metacritic_pipeline.delay(
            limit=limit,
            trigger_type="manual",
            run_id=run.id,
        )
        task_id = task.id
        run.task_id = task_id
        await db.commit()
    except Exception as exc:
        logger.error("Failed to enqueue Celery task: %s", exc)
        run.status = "failed"
        run.error_summary = f"Worker dispatch failure: {exc}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to dispatch run to background worker: {exc}",
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "run_id": run.id,
            "task_id": task_id,
            "status": "pending",
            "trigger_type": "manual",
        },
    )
