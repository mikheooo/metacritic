from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FixedClock, reset_clock, set_clock
from app.models.crawl import CrawlRun, DailyGameProcessing
from app.models.game import Game
from app.services.crawler.dtos import BrowsePage, GameCandidate, GameDetails, PlatformScore
from app.services.crawler.ingestion_service import IngestionService
from app.workers.tasks import process_metacritic_batch


class SimpleMockSource:
    def __init__(self, count: int = 5) -> None:
        self.count = count

    async def get_new_releases(self) -> list[GameCandidate]:
        return [
            GameCandidate(
                title=f"Sample Game {i}",
                url=f"https://www.metacritic.com/game/sample-game-{i}/",
                external_id=f"sample-game-{i}",
            )
            for i in range(self.count)
        ]

    async def get_browse_page(self, page: int) -> Any:
        from app.services.crawler.dtos import BrowsePage
        return BrowsePage(candidates=[], page=page, has_next=False)

    async def get_game_details(self, url: str) -> GameDetails:
        from app.services.crawler.dtos import extract_canonical_slug
        slug = extract_canonical_slug(url)
        return GameDetails(
            external_id=slug,
            metacritic_url=f"https://www.metacritic.com/game/{slug}/",
            metacritic_slug=slug,
            title=slug.replace("-", " ").title(),
            cover_url=f"https://example.com/{slug}.jpg",
            developer="Studio Test",
            description=f"Description for {slug}",
            platforms=[PlatformScore("PC", "pc", metascore=88, userscore=8.0)],
        )


@pytest.fixture(autouse=True)
def clean_clock() -> None:
    yield
    reset_clock()


@pytest.mark.asyncio
async def test_crawler_dry_run_mode(db_session: AsyncSession) -> None:
    """Verify dry-run simulates selection without writing to database or advancing ledger."""
    set_clock(FixedClock(date(2026, 9, 7)))
    source = SimpleMockSource(count=3)
    service = IngestionService(db=db_session, source=source)

    result = await service.run_crawl(limit=3, dry_run=True)

    assert result.dry_run is True
    assert result.status == "dry_run"
    assert result.eligible_count == 3
    assert result.processed_count == 0
    assert len(result.candidates) == 3

    # Verify nothing was persisted to DB
    games_count = await db_session.scalar(select(func.count(Game.id)))
    assert games_count == 0

    daily_entries = await db_session.scalar(select(func.count(DailyGameProcessing.id)))
    assert daily_entries == 0

    crawl_runs = await db_session.scalar(select(func.count(CrawlRun.id)))
    assert crawl_runs == 0


@pytest.mark.asyncio
async def test_celery_task_integration(db_session: AsyncSession) -> None:
    """Verify the Celery process_metacritic_batch entrypoint dispatches cleanly."""
    with patch(
        "app.services.crawler.ingestion_service.MetacriticClient.get_new_releases"
    ) as mock_nr, patch(
        "app.services.crawler.ingestion_service.MetacriticClient.get_browse_page"
    ) as mock_bp, patch(
        "app.services.crawler.ingestion_service.MetacriticClient.get_game_details"
    ) as mock_details:
        cand = GameCandidate("Task Game", "https://www.metacritic.com/game/task-game/", "task-game")
        mock_nr.return_value = [cand]
        mock_bp.return_value = BrowsePage(candidates=[cand], page=1, has_next=False)
        mock_details.return_value = GameDetails(
            external_id="task-game",
            metacritic_url="https://www.metacritic.com/game/task-game/",
            metacritic_slug="task-game",
            title="Task Game",
            platforms=[PlatformScore("PC", "pc", metascore=80, userscore=7.5)],
        )

        res = process_metacritic_batch(limit=1, trigger_type="scheduled", dry_run=True)
        assert res["dry_run"] is True
        assert res["eligible_count"] == 1
        assert "Task Game" in res["candidates"]

