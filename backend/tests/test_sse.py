import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlRun, CrawlRunEvent


@pytest.mark.asyncio
async def test_sse_stream_snapshot_and_content_type(client: AsyncClient) -> None:
    """Verify GET /api/monitor/stream returns text/event-stream and initial snapshot event."""
    response = await client.get("/api/monitor/stream?max_iterations=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: snapshot" in response.text
    assert "data: {" in response.text


@pytest.mark.asyncio
async def test_sse_stream_reconnect_cursor_with_last_event_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verify SSE reconnection cursor semantics:
    When Last-Event-ID header is supplied, events with id > Last-Event-ID are delivered.
    """
    # Create run and events
    run = CrawlRun(status="running", trigger_type="scheduled", target_count=20)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    ev1 = CrawlRunEvent(
        crawl_run_id=run.id,
        event_type="discovery_started",
        stage="discovering",
        message="Discovery started",
    )
    ev2 = CrawlRunEvent(
        crawl_run_id=run.id,
        event_type="discovery_completed",
        stage="discovering",
        message="Discovery completed",
    )
    db_session.add_all([ev1, ev2])
    await db_session.commit()
    await db_session.refresh(ev1)
    await db_session.refresh(ev2)

    # Reconnect with cursor = ev1.id via header (should receive ev2, but not ev1)
    headers = {"Last-Event-ID": str(ev1.id)}
    response = await client.get("/api/monitor/stream?max_iterations=2", headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert f"id: {ev2.id}" in response.text
    assert "discovery_completed" in response.text
    assert f"id: {ev1.id}" not in response.text

    # Reconnect with cursor via query parameter
    resp_param = await client.get(
        f"/api/monitor/stream?last_event_id={ev1.id}&max_iterations=2"
    )
    assert resp_param.status_code == 200
    assert f"id: {ev2.id}" in resp_param.text
    assert f"id: {ev1.id}" not in resp_param.text

