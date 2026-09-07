from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FixedClock, reset_clock, set_clock
from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    PlatformScore,
)
from app.services.crawler.ingestion_service import IngestionService


class MockMetacriticSource:
    def __init__(self) -> None:
        self.new_releases_list: list[GameCandidate] = []
        self.browse_pages: dict[int, list[GameCandidate]] = {}
        self.game_details_map: dict[str, GameDetails] = {}

    def add_game(self, slug: str, title: str) -> None:
        self.game_details_map[slug] = GameDetails(
            external_id=slug,
            metacritic_url=f"https://www.metacritic.com/game/{slug}/",
            metacritic_slug=slug,
            title=title,
            platforms=[PlatformScore("PC", "pc", metascore=80, userscore=8.0)],
        )

    async def get_new_releases(self) -> list[GameCandidate]:
        return list(self.new_releases_list)

    async def get_browse_page(self, page: int) -> BrowsePage:
        candidates = self.browse_pages.get(page, [])
        return BrowsePage(
            candidates=candidates,
            page=page,
            has_next=page in self.browse_pages,
        )

    async def get_game_details(self, canonical_url: str) -> GameDetails:
        slug = canonical_url.rstrip("/").split("/")[-1]
        return self.game_details_map[slug]


@pytest.fixture(autouse=True)
def clean_clock() -> None:
    yield
    reset_clock()


@pytest.mark.asyncio
async def test_production_limit_20_daily_cursor_semantics(db_session: AsyncSession) -> None:
    """
    Stage 2 Regression Guard:
    Standard production run uses limit = 20.
    1. First run of the day -> candidates originate from New Releases.
    2. Subsequent run on the same day -> continues into Browse newest (Page 1).
    3. Third run on the same day -> advances to Browse newest (Page 2).
    4. Next day -> starts again with New Releases.
    """
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()

    # 1. 20 New Releases
    for i in range(20):
        slug = f"prod-nr-game-{i}"
        source.add_game(slug, f"Prod NR Game {i}")
        source.new_releases_list.append(
            GameCandidate(f"Prod NR Game {i}", f"https://www.metacritic.com/game/{slug}/", slug)
        )

    # 2. Browse Page 1: 20 games
    p1 = []
    for i in range(20):
        slug = f"prod-browse-p1-game-{i}"
        source.add_game(slug, f"Prod Browse P1 Game {i}")
        p1.append(
            GameCandidate(f"Prod Browse P1 Game {i}", f"https://www.metacritic.com/game/{slug}/", slug)
        )
    source.browse_pages[1] = p1

    # 3. Browse Page 2: 20 games
    p2 = []
    for i in range(20):
        slug = f"prod-browse-p2-game-{i}"
        source.add_game(slug, f"Prod Browse P2 Game {i}")
        p2.append(
            GameCandidate(f"Prod Browse P2 Game {i}", f"https://www.metacritic.com/game/{slug}/", slug)
        )
    source.browse_pages[2] = p2

    service = IngestionService(db=db_session, source=source)

    # --- RUN 1: First run of Day 1 (Production limit = 20) ---
    res1 = await service.run_crawl(limit=20)
    assert res1.status == "completed"
    assert res1.processed_count == 20
    assert len(res1.candidates) == 20
    # Every single candidate must originate from New Releases
    for i in range(20):
        assert f"Prod NR Game {i}" in res1.candidates
    assert "Prod Browse P1 Game 0" not in res1.candidates

    # State check: phase advanced to browse
    state1 = await service.get_or_create_daily_state(date(2026, 9, 7))
    assert state1.phase == "browse"

    # --- RUN 2: Second run of Day 1 (Production limit = 20) ---
    res2 = await service.run_crawl(limit=20)
    assert res2.status == "completed"
    assert res2.processed_count == 20
    assert len(res2.candidates) == 20
    assert res2.phase == "browse"
    # Every single candidate must originate from Browse Page 1
    for i in range(20):
        assert f"Prod Browse P1 Game {i}" in res2.candidates
    assert "Prod NR Game 0" not in res2.candidates

    # --- RUN 3: Third run of Day 1 -> progresses to Browse Page 2 ---
    res3 = await service.run_crawl(limit=20)
    assert res3.status == "completed"
    assert res3.processed_count == 20
    assert len(res3.candidates) == 20
    assert res3.phase == "browse"
    # Every single candidate must originate from Browse Page 2
    for i in range(20):
        assert f"Prod Browse P2 Game {i}" in res3.candidates
    assert "Prod Browse P1 Game 0" not in res3.candidates

    # --- RUN 4: Next Calendar Day (Day 2) -> Resets to New Releases ---
    clock.advance(days=1)
    assert clock.today() == date(2026, 9, 8)

    # Day 2 run 1 starts with New Releases
    res4 = await service.run_crawl(limit=20)
    assert res4.status == "completed"
    assert res4.processed_count == 20
    assert len(res4.candidates) == 20
    # Must originate from New Releases on Day 2
    assert "Prod NR Game 0" in res4.candidates
    assert "Prod Browse P1 Game 0" not in res4.candidates
