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


@pytest.mark.asyncio
async def test_manual_run_cooldown_rate_limiting(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verify abuse protection cooldown:
    When a run finished recently (< MANUAL_RUN_COOLDOWN_SECONDS),
    POST /api/crawler/run rejects with HTTP 429 Too Many Requests.
    When the cooldown window expires, new manual runs are accepted.
    """
    from datetime import UTC, datetime, timedelta
    from unittest.mock import patch

    # 1. Simulate a run that finished 10 seconds ago
    recent_run = CrawlRun(
        status="completed",
        trigger_type="manual",
        target_count=20,
        current_stage="completed",
        started_at=datetime.now(UTC) - timedelta(seconds=30),
        finished_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    db_session.add(recent_run)
    await db_session.commit()

    with patch("app.core.config.settings.MANUAL_RUN_COOLDOWN_SECONDS", 60):
        resp = await client.post("/api/crawler/run")
        assert resp.status_code == 429
        data = resp.json()
        assert "cooldown" in data["detail"].lower()
        assert "retry_after_seconds" in data
        assert data["retry_after_seconds"] > 0

    # 2. Simulate expired cooldown (> 60s ago)
    recent_run.finished_at = datetime.now(UTC) - timedelta(seconds=70)
    await db_session.commit()

    with (
        patch("app.core.config.settings.MANUAL_RUN_COOLDOWN_SECONDS", 60),
        patch("app.api.v1.endpoints.crawler.process_metacritic_pipeline.delay") as mock_delay,
    ):
        mock_delay.return_value.id = "cooldown-bypass-task"
        resp = await client.post("/api/crawler/run")
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"
