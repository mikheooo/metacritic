import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlRun
from app.services.crawler.lock import CrawlAlreadyRunningError, CrawlLock
from app.services.crawler.pipeline_service import MetacriticPipelineService


@pytest.mark.asyncio
async def test_active_run_in_db_blocks_new_manual_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verify concurrency protection:
    When an active run (status='running') exists in the DB,
    POST /api/crawler/run rejects with HTTP 409 Conflict and reports the active_run_id.
    """
    # Create active run
    active_run = CrawlRun(
        status="running",
        trigger_type="scheduled",
        target_count=20,
        current_stage="ingesting",
    )
    db_session.add(active_run)
    await db_session.commit()
    await db_session.refresh(active_run)

    # Attempt to trigger Run Now without body
    resp = await client.post("/api/crawler/run")
    assert resp.status_code == 409
    data = resp.json()
    assert "already active" in data["detail"]
    assert data["active_run_id"] == active_run.id


@pytest.mark.asyncio
async def test_pending_run_in_db_blocks_new_manual_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verify concurrency protection:
    When a pending run (status='pending') exists in the DB,
    POST /api/crawler/run rejects with HTTP 409 Conflict.
    """
    pending_run = CrawlRun(
        status="pending",
        trigger_type="manual",
        target_count=20,
        current_stage="queued",
    )
    db_session.add(pending_run)
    await db_session.commit()
    await db_session.refresh(pending_run)

    resp = await client.post("/api/crawler/run")
    assert resp.status_code == 409
    data = resp.json()
    assert data["active_run_id"] == pending_run.id


@pytest.mark.asyncio
async def test_redis_lock_blocks_concurrent_pipeline_execution(db_session: AsyncSession) -> None:
    """
    Verify distributed lock semantics:
    If CrawlLock is already acquired by another worker/process,
    a secondary attempt to run pipeline raises CrawlAlreadyRunningError.
    """
    # Hold lock manually
    async with CrawlLock():
        service = MetacriticPipelineService(db=db_session)
        with pytest.raises(CrawlAlreadyRunningError):
            await service.run_pipeline(limit=20, trigger_type="scheduled")


@pytest.mark.asyncio
async def test_manual_lock_blocks_scheduled_task_execution(db_session: AsyncSession) -> None:
    """
    Verify bidirectional lock collision:
    When manual pipeline holds distributed lock, scheduled pipeline run
    is blocked and raises CrawlAlreadyRunningError.
    """
    async with CrawlLock():
        service = MetacriticPipelineService(db=db_session)
        with pytest.raises(CrawlAlreadyRunningError):
            await service.run_pipeline(limit=20, trigger_type="scheduled")
