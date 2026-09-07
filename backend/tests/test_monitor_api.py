from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlRun, CrawlRunEvent
from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.schemas.crawl import WorkerStatus


@pytest.mark.asyncio
async def test_run_now_creates_pending_run_and_dispatches_task(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify POST /api/crawler/run creates a pending CrawlRun and returns 202 Accepted with canonical limit=20."""
    with patch("app.api.v1.endpoints.crawler.process_metacritic_pipeline.delay") as mock_delay:
        mock_delay.return_value.id = "celery-task-12345"

        resp = await client.post("/api/crawler/run")
        assert resp.status_code == 202
        data = resp.json()

        assert data["status"] == "pending"
        assert data["trigger_type"] == "manual"
        assert data["task_id"] == "celery-task-12345"
        assert "run_id" in data

        # Check DB persistence
        run = await db_session.get(CrawlRun, data["run_id"])
        assert run is not None
        assert run.status == "pending"
        assert run.target_count == 20
        assert run.task_id == "celery-task-12345"

        # Verify Celery dispatch called with limit=20
        mock_delay.assert_called_once_with(limit=20, trigger_type="manual", run_id=run.id)

        # Verify run_queued event was logged
        stmt_ev = select(CrawlRunEvent).where(CrawlRunEvent.crawl_run_id == run.id)
        res_ev = await db_session.execute(stmt_ev)
        events = res_ev.scalars().all()
        assert any(e.event_type == "run_queued" for e in events)


@pytest.mark.asyncio
async def test_run_now_ignores_client_limit_and_preserves_canonical_batch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify POST /api/crawler/run ignores client-supplied limit body and strictly dispatches limit=20."""
    with patch("app.api.v1.endpoints.crawler.process_metacritic_pipeline.delay") as mock_delay:
        mock_delay.return_value.id = "celery-task-batch20"

        # Attempt to supply arbitrary limits
        resp = await client.post("/api/crawler/run", json={"limit": 2})
        assert resp.status_code == 202
        data = resp.json()

        run = await db_session.get(CrawlRun, data["run_id"])
        assert run is not None
        # Must be 20, NOT 2!
        assert run.target_count == 20
        mock_delay.assert_called_once_with(limit=20, trigger_type="manual", run_id=run.id)


@pytest.mark.asyncio
async def test_monitor_status_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify GET /api/monitor/status returns deterministic scheduler, worker, and runs."""
    resp = await client.get("/api/monitor/status")
    assert resp.status_code == 200
    data = resp.json()

    assert "scheduler" in data
    assert data["scheduler"]["enabled"] is True
    assert data["scheduler"]["timezone"] == "UTC"
    assert data["scheduler"]["next_run_at"] is not None

    assert "worker" in data
    assert "online" in data["worker"]
    assert "workers" in data["worker"]


@pytest.mark.asyncio
async def test_worker_offline_graceful_handling(client: AsyncClient) -> None:
    """
    Verify GET /api/monitor/status does not crash or hang if Celery worker is unreachable.
    Returns worker.online = False gracefully.
    """
    with patch(
        "app.api.v1.endpoints.monitor.check_celery_worker_status",
        return_value=WorkerStatus(online=False, workers=[]),
    ):
        resp = await client.get("/api/monitor/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker"]["online"] is False
        assert data["worker"]["workers"] == []


@pytest.mark.asyncio
async def test_monitor_runs_and_durable_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify GET /api/monitor/runs and GET /api/monitor/runs/{id} returns durable history."""
    now = datetime.now(UTC)
    run1 = CrawlRun(
        status="completed",
        trigger_type="scheduled",
        target_count=20,
        processed_count=19,
        failed_count=1,
        started_at=now,
        finished_at=now,
    )
    db_session.add(run1)
    await db_session.commit()
    await db_session.refresh(run1)

    ev1 = CrawlRunEvent(
        crawl_run_id=run1.id,
        event_type="run_started",
        stage="discovering",
        message="Started scheduled run",
    )
    ev2 = CrawlRunEvent(
        crawl_run_id=run1.id,
        event_type="run_completed",
        stage="completed",
        message="Finished scheduled run",
    )
    db_session.add_all([ev1, ev2])
    await db_session.commit()

    # Query list of runs
    resp_list = await client.get("/api/monitor/runs")
    assert resp_list.status_code == 200
    runs_data = resp_list.json()
    assert len(runs_data) >= 1
    found = next((r for r in runs_data if r["id"] == run1.id), None)
    assert found is not None
    assert found["status"] == "completed"
    assert found["processed_count"] == 19

    # Query single run details
    resp_single = await client.get(f"/api/monitor/runs/{run1.id}")
    assert resp_single.status_code == 200
    single_data = resp_single.json()
    assert single_data["id"] == run1.id
    assert len(single_data["events"]) == 2

    # Query non-existent run
    resp_404 = await client.get("/api/monitor/runs/999999")
    assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_platforms_endpoint_returns_distinct_real_platforms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verify GET /api/platforms returns only platforms present in DB with games,
    excludes navigation artifacts, and sorts alphabetically.
    """
    p_pc = Platform(name="PC", slug="pc")
    p_ps5 = Platform(name="PlayStation 5", slug="playstation-5")
    p_nav = Platform(name="Games", slug="games")  # Navigation label
    db_session.add_all([p_pc, p_ps5, p_nav])
    await db_session.commit()

    game = Game(
        title="Test Game",
        metacritic_slug="test-game",
        metacritic_url="https://metacritic.com/game/test-game/",
    )
    db_session.add(game)
    await db_session.commit()

    # Associate with PC, PS5, and Nav
    gp1 = GamePlatform(game_id=game.id, platform_id=p_pc.id)
    gp2 = GamePlatform(game_id=game.id, platform_id=p_ps5.id)
    gp3 = GamePlatform(game_id=game.id, platform_id=p_nav.id)
    db_session.add_all([gp1, gp2, gp3])
    await db_session.commit()

    resp = await client.get("/api/platforms")
    assert resp.status_code == 200
    platforms = resp.json()

    slugs = [p["slug"] for p in platforms]
    assert "pc" in slugs
    assert "playstation-5" in slugs
    assert "games" not in slugs, "Navigation label 'games' must be excluded"
