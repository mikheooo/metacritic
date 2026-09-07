import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_session_factory
from app.core.config import settings
from app.models.crawl import CrawlRun, CrawlRunEvent
from app.schemas.crawl import (
    CrawlRunEventRead,
    CrawlRunRead,
    MonitorStatusResponse,
    SchedulerStatus,
    WorkerStatus,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["Monitor"])


def get_deterministic_next_run() -> datetime:
    """Calculate the deterministic next hourly scheduled crawl time in UTC."""
    now = datetime.now(UTC)
    scheduled_minute = settings.CRAWL_SCHEDULE_MINUTE
    if now.minute < scheduled_minute:
        candidate = now.replace(minute=scheduled_minute, second=0, microsecond=0)
    else:
        candidate = (now + timedelta(hours=1)).replace(
            minute=scheduled_minute, second=0, microsecond=0
        )
    return candidate


async def check_celery_worker_status() -> WorkerStatus:
    """
    Check if Celery worker is actively reachable via inspect/ping.
    Runs in a thread executor with a strict 0.8s timeout to ensure non-blocking behavior.
    """
    def _ping_sync() -> tuple[bool, list[str]]:
        try:
            res = celery_app.control.ping(timeout=0.8)
            if res and isinstance(res, list):
                worker_names: list[str] = []
                for entry in res:
                    if isinstance(entry, dict):
                        worker_names.extend(entry.keys())
                return (len(worker_names) > 0, worker_names)
            return (False, [])
        except Exception as exc:
            logger.debug("Celery worker ping error: %s", exc)
            return (False, [])

    loop = asyncio.get_running_loop()
    try:
        online, workers = await asyncio.wait_for(
            loop.run_in_executor(None, _ping_sync),
            timeout=1.2,
        )
        return WorkerStatus(online=online, workers=workers)
    except Exception:
        return WorkerStatus(online=False, workers=[])


@router.get("/status", response_model=MonitorStatusResponse)
async def get_monitor_status(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve system monitoring snapshot: scheduler configuration,
    worker reachability, currently active run, and the last completed/failed run.
    """
    # 1. Worker status
    worker = await check_celery_worker_status()

    # 2. Active run
    stmt_active = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.events))
        .where(CrawlRun.status.in_(["pending", "running"]))
        .order_by(desc(CrawlRun.id))
        .limit(1)
    )
    res_active = await db.execute(stmt_active)
    active_run = res_active.scalar_one_or_none()

    # 3. Last finished run
    stmt_last = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.events))
        .where(CrawlRun.status.in_(["completed", "partial", "failed"]))
        .order_by(desc(CrawlRun.id))
        .limit(1)
    )
    res_last = await db.execute(stmt_last)
    last_run = res_last.scalar_one_or_none()

    # 4. Last scheduled run timestamp
    stmt_sched = (
        select(CrawlRun.started_at)
        .where(CrawlRun.trigger_type == "scheduled", CrawlRun.started_at.isnot(None))
        .order_by(desc(CrawlRun.id))
        .limit(1)
    )
    res_sched = await db.execute(stmt_sched)
    last_scheduled_at = res_sched.scalar_one_or_none()

    # 5. Scheduler status
    scheduler = SchedulerStatus(
        enabled=settings.CRAWL_SCHEDULE_ENABLED,
        timezone=settings.CELERY_TIMEZONE,
        next_run_at=get_deterministic_next_run() if settings.CRAWL_SCHEDULE_ENABLED else None,
        last_run_at=last_scheduled_at,
    )

    return MonitorStatusResponse(
        scheduler=scheduler,
        worker=worker,
        active_run=CrawlRunRead.model_validate(active_run) if active_run else None,
        last_run=CrawlRunRead.model_validate(last_run) if last_run else None,
    )


@router.get("/runs", response_model=list[CrawlRunRead])
async def list_monitor_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve durable history of crawl runs, ordered by id descending."""
    stmt = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.events))
        .order_by(desc(CrawlRun.id))
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(stmt)
    runs = res.scalars().all()
    return [CrawlRunRead.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=CrawlRunRead)
async def get_monitor_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve full details of a specific crawl run, including its chronological events."""
    stmt = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.events))
        .where(CrawlRun.id == run_id)
    )
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"CrawlRun #{run_id} not found")
    return CrawlRunRead.model_validate(run)


@router.get("/stream")
async def monitor_stream(
    request: Request,
    last_event_id: int | None = Query(default=None, alias="last_event_id"),
    header_last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    max_iterations: int | None = Query(default=None, include_in_schema=False),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> StreamingResponse:
    """
    Realtime Server-Sent Events (SSE) stream for pipeline monitoring.
    - Sends initial system snapshot
    - Reconnection support via Last-Event-ID header or query parameter
    - Streams new append-only CrawlRunEvents with durable IDs
    - Periodic keep-alive comments
    - Uses short-lived database queries to avoid long open transactions.
    """
    cursor_id = last_event_id
    if cursor_id is None and header_last_event_id:
        try:
            cursor_id = int(header_last_event_id)
        except ValueError:
            cursor_id = None

    async def event_generator() -> AsyncGenerator[str, None]:
        nonlocal cursor_id

        # 1. Send initial snapshot
        try:
            async with session_factory() as session:
                worker = await check_celery_worker_status()
                stmt_active = (
                    select(CrawlRun)
                    .options(selectinload(CrawlRun.events))
                    .where(CrawlRun.status.in_(["pending", "running"]))
                    .order_by(desc(CrawlRun.id))
                    .limit(1)
                )
                res_active = await session.execute(stmt_active)
                active_run = res_active.scalar_one_or_none()

                stmt_last = (
                    select(CrawlRun)
                    .options(selectinload(CrawlRun.events))
                    .where(CrawlRun.status.in_(["completed", "partial", "failed"]))
                    .order_by(desc(CrawlRun.id))
                    .limit(1)
                )
                res_last = await session.execute(stmt_last)
                last_run = res_last.scalar_one_or_none()

                snapshot = MonitorStatusResponse(
                    scheduler=SchedulerStatus(
                        enabled=settings.CRAWL_SCHEDULE_ENABLED,
                        timezone=settings.CELERY_TIMEZONE,
                        next_run_at=get_deterministic_next_run() if settings.CRAWL_SCHEDULE_ENABLED else None,
                    ),
                    worker=worker,
                    active_run=CrawlRunRead.model_validate(active_run) if active_run else None,
                    last_run=CrawlRunRead.model_validate(last_run) if last_run else None,
                )
                yield f"event: snapshot\ndata: {snapshot.model_dump_json()}\n\n"
        except Exception as exc:
            logger.error("Error generating SSE initial snapshot: %s", exc)

        # 2. Determine initial event cursor
        if cursor_id is None:
            # If no cursor provided, find the highest existing event id
            async with session_factory() as session:
                stmt_max = select(CrawlRunEvent.id).order_by(desc(CrawlRunEvent.id)).limit(1)
                res_max = await session.execute(stmt_max)
                max_id = res_max.scalar_one_or_none()
                cursor_id = max_id or 0

        # 3. Stream loop with short-lived session per poll
        ping_counter = 0
        iteration = 0
        try:
            while True:
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1

                # Disconnect check
                if await request.is_disconnected():
                    break

                try:
                    async with session_factory() as session:
                        stmt_ev = (
                            select(CrawlRunEvent)
                            .where(CrawlRunEvent.id > cursor_id)
                            .order_by(CrawlRunEvent.id.asc())
                            .limit(50)
                        )
                        res_ev = await session.execute(stmt_ev)
                        events = res_ev.scalars().all()

                        for ev in events:
                            dto = CrawlRunEventRead.model_validate(ev)
                            yield f"id: {ev.id}\nevent: event\ndata: {dto.model_dump_json()}\n\n"
                            cursor_id = ev.id

                    ping_counter += 1
                    if ping_counter >= 15:
                        yield ": ping\n\n"
                        ping_counter = 0

                except Exception as exc:
                    logger.error("Error in SSE event stream loop: %s", exc)

                await asyncio.sleep(0.5)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            logger.info("SSE client stream ended cleanly")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
