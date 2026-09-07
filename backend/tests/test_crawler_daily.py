from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FixedClock, reset_clock, set_clock
from app.models.crawl import DailyCrawlState, DailyGameProcessing
from app.models.game import Game
from app.models.platform import GamePlatform
from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    PlatformScore,
)
from app.services.crawler.ingestion_service import IngestionService
from app.services.crawler.lock import CrawlAlreadyRunningError, CrawlLock


class MockMetacriticSource:
    """Mock source providing controllable candidates and details for testing."""

    def __init__(self) -> None:
        self.new_releases_list: list[GameCandidate] = []
        self.browse_pages: dict[int, list[GameCandidate]] = {}
        self.game_details_map: dict[str, GameDetails] = {}
        self.fail_on_slugs: set[str] = set()

    def add_game(
        self,
        slug: str,
        title: str,
        metascore: int | None = 80,
        userscore: float | None = 7.5,
        platform_slug: str = "pc",
    ) -> None:
        self.game_details_map[slug] = GameDetails(
            external_id=slug,
            metacritic_url=f"https://www.metacritic.com/game/{slug}/",
            metacritic_slug=slug,
            title=title,
            cover_url=f"https://img.example.com/{slug}.jpg",
            developer="Test Dev",
            description=f"Description for {title}",
            platforms=[
                PlatformScore(
                    platform_name=platform_slug.upper(),
                    platform_slug=platform_slug,
                    metascore=metascore,
                    userscore=userscore,
                )
            ],
        )

    async def get_new_releases(self) -> list[GameCandidate]:
        return list(self.new_releases_list)

    async def get_browse_page(self, page: int) -> BrowsePage:
        candidates = self.browse_pages.get(page, [])
        has_next = (page + 1) in self.browse_pages
        return BrowsePage(candidates=candidates, page=page, has_next=has_next)

    async def get_game_details(self, url: str) -> GameDetails:
        from app.services.crawler.dtos import extract_canonical_slug
        slug = extract_canonical_slug(url)
        if slug in self.fail_on_slugs:
            raise ValueError(f"Simulated network/parsing failure for game: {slug}")
        if slug in self.game_details_map:
            return self.game_details_map[slug]
        # Default synthetic details
        return GameDetails(
            external_id=slug,
            metacritic_url=f"https://www.metacritic.com/game/{slug}/",
            metacritic_slug=slug,
            title=slug.replace("-", " ").title(),
            platforms=[PlatformScore("PC", "pc", metascore=75, userscore=7.0)],
        )


@pytest.fixture(autouse=True)
def clean_clock() -> None:
    yield
    reset_clock()


# --- TEST 1 ---
@pytest.mark.asyncio
async def test_01_first_run_of_new_day_starts_with_new_releases(db_session: AsyncSession) -> None:
    """Test 1: First run of a new calendar day begins at phase 'new_releases'."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    for i in range(5):
        slug = f"nr-game-{i}"
        source.add_game(slug, f"NR Game {i}")
        source.new_releases_list.append(
            GameCandidate(f"NR Game {i}", f"https://www.metacritic.com/game/{slug}/", slug)
        )

    service = IngestionService(db=db_session, source=source)
    result = await service.run_crawl(limit=5)

    assert result.status == "completed"
    assert result.processed_count == 5

    # Check state recorded in DB
    state = await service.get_or_create_daily_state(date(2026, 9, 7))
    assert state.phase == "browse"  # Advanced to browse after new_releases completed
    assert state.browse_page == 1


# --- TEST 2 ---
@pytest.mark.asyncio
async def test_02_second_run_same_day_progresses_to_browse(db_session: AsyncSession) -> None:
    """Test 2: Second run on the same calendar day continues into Browse pages."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    # 5 New Releases
    for i in range(5):
        slug = f"nr-game-{i}"
        source.add_game(slug, f"NR Game {i}")
        source.new_releases_list.append(
            GameCandidate(f"NR Game {i}", f"https://www.metacritic.com/game/{slug}/", slug)
        )

    # Browse Page 1 has 5 different games
    page1_cands = []
    for i in range(5):
        slug = f"browse-game-p1-{i}"
        source.add_game(slug, f"Browse Game P1-{i}")
        page1_cands.append(GameCandidate(f"Browse Game P1-{i}", f"https://www.metacritic.com/game/{slug}/", slug))
    source.browse_pages[1] = page1_cands

    service = IngestionService(db=db_session, source=source)

    # Run 1: processes New Releases
    res1 = await service.run_crawl(limit=5)
    assert res1.processed_count == 5

    # Run 2: same day -> should process Browse page 1
    res2 = await service.run_crawl(limit=5)
    assert res2.processed_count == 5
    assert res2.phase == "browse"
    assert "Browse Game P1-0" in res2.candidates


# --- TEST 3 ---
@pytest.mark.asyncio
async def test_03_same_game_in_new_releases_and_browse_only_processed_once(
    db_session: AsyncSession,
) -> None:
    """Test 3: If a game appears in both New Releases and Browse, it is only processed once today."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    shared_slug = "overlap-game"
    source = MockMetacriticSource()
    source.add_game(shared_slug, "Overlap Game")
    source.new_releases_list = [
        GameCandidate("Overlap Game", f"https://www.metacritic.com/game/{shared_slug}/", shared_slug)
    ]
    source.browse_pages[1] = [
        GameCandidate("Overlap Game", f"https://www.metacritic.com/game/{shared_slug}/", shared_slug),
        GameCandidate("Other Game", "https://www.metacritic.com/game/other-game/", "other-game"),
    ]
    source.add_game("other-game", "Other Game")

    service = IngestionService(db=db_session, source=source)
    res = await service.run_crawl(limit=10)

    # Overlap Game processed only once
    assert res.processed_count == 2
    assert res.candidates.count("Overlap Game") == 1

    # Verify daily ledger count
    stmt = select(func.count(DailyGameProcessing.id)).where(
        DailyGameProcessing.game_external_id == shared_slug
    )
    count = await db_session.scalar(stmt)
    assert count == 1


# --- TEST 4 ---
@pytest.mark.asyncio
async def test_04_crawler_advances_through_browse_pages_to_reach_target(
    db_session: AsyncSession,
) -> None:
    """Test 4: First browse page has 12 already processed games -> crawler advances to next page until 20 collected."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    # Mark 12 games as already processed today in daily ledger
    for i in range(12):
        slug = f"old-game-{i}"
        source.add_game(slug, f"Old Game {i}")
        db_session.add(DailyGameProcessing(processing_date=date(2026, 9, 7), game_external_id=slug))
    await db_session.commit()

    # Browse Page 1: 12 old games + 3 new games
    p1 = [GameCandidate(f"Old Game {i}", f"https://www.metacritic.com/game/old-game-{i}/", f"old-game-{i}") for i in range(12)]
    for i in range(3):
        slug = f"new-p1-game-{i}"
        source.add_game(slug, f"New P1 Game {i}")
        p1.append(GameCandidate(f"New P1 Game {i}", f"https://www.metacritic.com/game/{slug}/", slug))
    source.browse_pages[1] = p1

    # Browse Page 2: 25 new games
    p2 = []
    for i in range(25):
        slug = f"new-p2-game-{i}"
        source.add_game(slug, f"New P2 Game {i}")
        p2.append(GameCandidate(f"New P2 Game {i}", f"https://www.metacritic.com/game/{slug}/", slug))
    source.browse_pages[2] = p2

    # Set state directly to browse page 1
    state = DailyCrawlState(processing_date=date(2026, 9, 7), phase="browse", browse_page=1)
    db_session.add(state)
    await db_session.commit()

    service = IngestionService(db=db_session, source=source)
    result = await service.run_crawl(limit=20)

    # 3 from page 1 + 17 from page 2 = 20 total eligible
    assert result.processed_count == 20
    assert result.status == "completed"


# --- TEST 5 ---
@pytest.mark.asyncio
async def test_05_batch_interrupted_leaves_successful_and_remaining_eligible(
    db_session: AsyncSession,
) -> None:
    """Test 5: Partial failure: successful games are kept and remaining eligible games can run later."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    for i in range(4):
        slug = f"interrupted-game-{i}"
        source.add_game(slug, f"Game {i}")
        source.new_releases_list.append(GameCandidate(f"Game {i}", f"https://www.metacritic.com/game/{slug}/", slug))

    # Make game 2 fail
    source.fail_on_slugs.add("interrupted-game-2")

    service = IngestionService(db=db_session, source=source)
    res = await service.run_crawl(limit=4)

    assert res.status == "partial"
    assert res.processed_count == 3
    assert res.failed_count == 1

    # In a second run, games 0, 1, 3 are already processed; failed game 2 is still eligible!
    source.fail_on_slugs.clear()  # fix failure
    res2 = await service.run_crawl(limit=4)
    assert res2.processed_count == 1
    assert "Game 2" in res2.candidates


# --- TEST 6 ---
@pytest.mark.asyncio
async def test_06_failed_game_not_recorded_as_successfully_processed(
    db_session: AsyncSession,
) -> None:
    """Test 6: A failed game is NOT recorded in DailyGameProcessing."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    source.add_game("faulty-game", "Faulty Game")
    source.new_releases_list = [
        GameCandidate("Faulty Game", "https://www.metacritic.com/game/faulty-game/", "faulty-game")
    ]
    source.fail_on_slugs.add("faulty-game")

    service = IngestionService(db=db_session, source=source)
    res = await service.run_crawl(limit=1)

    assert res.failed_count == 1
    stmt = select(DailyGameProcessing).where(DailyGameProcessing.game_external_id == "faulty-game")
    record = await db_session.scalar(stmt)
    assert record is None


# --- TEST 7 ---
@pytest.mark.asyncio
async def test_07_same_game_next_calendar_day_eligible_again(db_session: AsyncSession) -> None:
    """Test 7: A game processed on Day 1 is eligible again on Day 2."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    source.add_game("chrono-trigger", "Chrono Trigger")
    source.new_releases_list = [
        GameCandidate("Chrono Trigger", "https://www.metacritic.com/game/chrono-trigger/", "chrono-trigger")
    ]

    service = IngestionService(db=db_session, source=source)
    res1 = await service.run_crawl(limit=1)
    assert res1.processed_count == 1

    # Day 1 second attempt -> 0 processed
    res_same_day = await service.run_crawl(limit=1)
    assert res_same_day.processed_count == 0

    # Advance clock to Day 2
    clock.advance(days=1)
    assert clock.today() == date(2026, 9, 8)

    # Day 2 attempt -> eligible again!
    res_day2 = await service.run_crawl(limit=1)
    assert res_day2.processed_count == 1


# --- TEST 8 ---
@pytest.mark.asyncio
async def test_08_existing_game_discovered_next_day_updates_without_duplication(
    db_session: AsyncSession,
) -> None:
    """Test 8: Existing game is UPDATED upon subsequent day ingestion without creating duplicate Game rows."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    source.add_game("elden-ring", "Elden Ring v1")
    source.new_releases_list = [
        GameCandidate("Elden Ring v1", "https://www.metacritic.com/game/elden-ring/", "elden-ring")
    ]

    service = IngestionService(db=db_session, source=source)
    await service.run_crawl(limit=1)

    # Update description in source for next day
    clock.advance(days=1)
    source.game_details_map["elden-ring"].title = "Elden Ring (Updated)"

    await service.run_crawl(limit=1)

    # Check that exactly ONE Game row exists with updated title
    stmt = select(Game).where(Game.metacritic_slug == "elden-ring")
    games = (await db_session.execute(stmt)).scalars().all()
    assert len(games) == 1
    assert games[0].title == "Elden Ring (Updated)"


# --- TEST 9 ---
@pytest.mark.asyncio
async def test_09_score_changed_updates_game_platform(db_session: AsyncSession) -> None:
    """Test 9: When scores change on Metacritic, existing GamePlatform scores are updated."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    source.add_game("baldurs-gate-3", "Baldurs Gate 3", metascore=90, userscore=8.5, platform_slug="pc")
    source.new_releases_list = [
        GameCandidate("Baldurs Gate 3", "https://www.metacritic.com/game/baldurs-gate-3/", "baldurs-gate-3")
    ]

    service = IngestionService(db=db_session, source=source)
    await service.run_crawl(limit=1)

    # Verify initial score
    stmt = select(GamePlatform).join(Game).where(Game.metacritic_slug == "baldurs-gate-3")
    gp = await db_session.scalar(stmt)
    assert gp.metascore == 90
    assert gp.userscore == 8.5

    # Day 2: score changes to Metascore 96, Userscore 9.0
    clock.advance(days=1)
    source.game_details_map["baldurs-gate-3"].platforms[0].metascore = 96
    source.game_details_map["baldurs-gate-3"].platforms[0].userscore = 9.0

    await service.run_crawl(limit=1)

    await db_session.refresh(gp)
    assert gp.metascore == 96
    assert gp.userscore == 9.0


# --- TEST 10 ---
@pytest.mark.asyncio
async def test_10_simultaneous_crawls_one_acquires_lock(db_session: AsyncSession) -> None:
    """Test 10: Two simultaneous crawl invocations cannot run concurrently."""
    # Test CrawlLock directly
    lock1 = CrawlLock(key="test:crawl:lock")
    lock2 = CrawlLock(key="test:crawl:lock")

    async with lock1:
        # Second lock attempt must fail
        with pytest.raises(CrawlAlreadyRunningError):
            async with lock2:
                pass


# --- TEST 11 ---
@pytest.mark.asyncio
async def test_11_page_content_changes_between_runs_daily_ledger_prevents_dups(
    db_session: AsyncSession,
) -> None:
    """Test 11: Even if external page items shift between runs, daily ledger guarantees no duplicates."""
    clock = FixedClock(date(2026, 9, 7))
    set_clock(clock)

    source = MockMetacriticSource()
    source.add_game("game-a", "Game A")
    source.add_game("game-b", "Game B")
    source.add_game("game-c", "Game C")

    # Run 1: page 1 has Game A and B
    source.browse_pages[1] = [
        GameCandidate("Game A", "https://www.metacritic.com/game/game-a/", "game-a"),
        GameCandidate("Game B", "https://www.metacritic.com/game/game-b/", "game-b"),
    ]

    # Set state to browse
    state = DailyCrawlState(processing_date=date(2026, 9, 7), phase="browse", browse_page=1)
    db_session.add(state)
    await db_session.commit()

    service = IngestionService(db=db_session, source=source)
    res1 = await service.run_crawl(limit=2)
    assert res1.processed_count == 2

    # Metacritic page reorders or inserts new game: page 1 now has Game B and Game C
    source.browse_pages[1] = [
        GameCandidate("Game B", "https://www.metacritic.com/game/game-b/", "game-b"),  # already processed
        GameCandidate("Game C", "https://www.metacritic.com/game/game-c/", "game-c"),  # new
    ]
    # Reset cursor to test ledger defense
    state.browse_page = 1
    await db_session.commit()

    res2 = await service.run_crawl(limit=2)
    # Only Game C should be processed; Game B is skipped by daily ledger!
    assert res2.processed_count == 1
    assert res2.candidates == ["Game C"]
