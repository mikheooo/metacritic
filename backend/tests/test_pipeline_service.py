from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FixedClock, reset_clock, set_clock
from app.models.crawl import CrawlRun, CrawlRunEvent, DailyCrawlState, DailyGameProcessing
from app.models.game import Game
from app.services.ai import GameEmbeddingService, ReviewEnrichmentService, SimilarGamesService
from app.services.ai.embedding_provider import FakeEmbeddingProvider
from app.services.ai.summarizer import FakeReviewSummarizer
from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    PlatformScore,
    ReviewItem,
    ReviewPage,
)
from app.services.crawler.pipeline_service import MetacriticPipelineService


class MockComprehensiveSource:
    """Mock Metacritic source supporting candidates, details, and paginated reviews."""

    def __init__(self) -> None:
        self.new_releases_list: list[GameCandidate] = []
        self.browse_pages: dict[int, list[GameCandidate]] = {}
        self.game_details_map: dict[str, GameDetails] = {}
        self.critic_reviews_map: dict[str, list[ReviewItem]] = {}
        self.user_reviews_map: dict[str, list[ReviewItem]] = {}
        self.fail_reviews_on_slugs: set[str] = set()

    def add_game(
        self,
        slug: str,
        title: str,
        metascore: int = 85,
        userscore: float = 8.2,
        platform_slug: str = "pc",
    ) -> None:
        self.game_details_map[slug] = GameDetails(
            external_id=slug,
            metacritic_url=f"https://www.metacritic.com/game/{slug}/",
            metacritic_slug=slug,
            title=title,
            cover_url=f"https://img.example.com/{slug}.jpg",
            developer="Studio Test",
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
        # Add sample critic and user review
        self.critic_reviews_map[slug] = [
            ReviewItem(
                external_id=f"c-{slug}-1",
                review_type="critic",
                author="Critic A",
                score=85.0,
                body=f"Excellent gameplay in {title}.",
                published_at="2026-01-10",
                platform_slug=platform_slug,
            )
        ]
        self.user_reviews_map[slug] = [
            ReviewItem(
                external_id=f"u-{slug}-1",
                review_type="user",
                author="User X",
                score=8.5,
                body=f"Loved playing {title}, great music.",
                published_at="2026-01-11",
                platform_slug=platform_slug,
            )
        ]

    async def get_new_releases(self) -> list[GameCandidate]:
        return list(self.new_releases_list)

    async def get_browse_page(self, page: int) -> BrowsePage:
        candidates = self.browse_pages.get(page, [])
        return BrowsePage(
            page=page,
            has_next=page in self.browse_pages and (page + 1) in self.browse_pages,
            candidates=candidates,
        )

    async def get_game_details(self, url: str) -> GameDetails:
        slug = url.strip("/").split("/")[-1]
        if slug in self.game_details_map:
            return self.game_details_map[slug]
        raise ValueError(f"Game not found for url: {url}")

    async def get_critic_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        if slug in self.fail_reviews_on_slugs:
            raise RuntimeError(f"Simulated critic review fetch failure for {slug}")
        reviews = self.critic_reviews_map.get(slug, []) if page == 1 else []
        return ReviewPage(reviews=reviews, current_page=page, has_next_page=False)

    async def get_user_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        if slug in self.fail_reviews_on_slugs:
            raise RuntimeError(f"Simulated user review fetch failure for {slug}")
        reviews = self.user_reviews_map.get(slug, []) if page == 1 else []
        return ReviewPage(reviews=reviews, current_page=page, has_next_page=False)


@pytest.fixture
def mock_source() -> MockComprehensiveSource:
    source = MockComprehensiveSource()
    for i in range(1, 6):
        slug = f"game-{i}"
        source.add_game(slug=slug, title=f"Game #{i}", metascore=80 + i)
        source.new_releases_list.append(
            GameCandidate(title=f"Game #{i}", url=f"https://www.metacritic.com/game/{slug}/", external_id=slug)
        )
    return source


@pytest.fixture
def mock_pipeline_service(
    db_session: AsyncSession, mock_source: MockComprehensiveSource
) -> MetacriticPipelineService:
    summarizer = FakeReviewSummarizer()
    enrichment = ReviewEnrichmentService(db=db_session, source=mock_source, summarizer=summarizer)
    embedding_provider = FakeEmbeddingProvider()
    embedding = GameEmbeddingService(db=db_session, provider=embedding_provider)
    similarity = SimilarGamesService(db=db_session)
    return MetacriticPipelineService(
        db=db_session,
        source=mock_source,
        enrichment_service=enrichment,
        embedding_service=embedding,
        similarity_service=similarity,
    )


@pytest.mark.asyncio
async def test_full_pipeline_success(
    db_session: AsyncSession, mock_pipeline_service: MetacriticPipelineService
) -> None:
    """Verify full orchestration: discovery -> ingestion -> reviews -> summaries -> embedding -> similarity."""
    clock = FixedClock(date(2026, 9, 1))
    set_clock(clock)
    try:
        result = await mock_pipeline_service.run_pipeline(limit=3, trigger_type="scheduled")

        assert result.status == "completed"
        assert result.discovered_count == 3
        assert result.processed_count == 3
        assert result.failed_count == 0
        assert result.reviews_processed_count == 6  # 3 games * (1 critic + 1 user)
        assert result.summaries_generated_count == 6  # 3 games * (1 critic + 1 user)
        assert result.embeddings_generated_count == 3

        # Verify CrawlRun database record
        assert result.crawl_run_id is not None
        stmt = select(CrawlRun).where(CrawlRun.id == result.crawl_run_id)
        res = await db_session.execute(stmt)
        run = res.scalar_one()

        assert run.status == "completed"
        assert run.trigger_type == "scheduled"
        assert run.target_count == 3
        assert run.processed_count == 3
        assert run.finished_at is not None

        # Verify event persistence
        stmt_ev = select(CrawlRunEvent).where(CrawlRunEvent.crawl_run_id == run.id).order_by(CrawlRunEvent.id.asc())
        res_ev = await db_session.execute(stmt_ev)
        events = res_ev.scalars().all()

        event_types = [e.event_type for e in events]
        assert "run_started" in event_types
        assert "discovery_started" in event_types
        assert "discovery_completed" in event_types
        assert "game_started" in event_types
        assert "game_persisted" in event_types
        assert "reviews_started" in event_types
        assert "reviews_completed" in event_types
        assert "summary_completed" in event_types
        assert "embedding_generated" in event_types
        assert "similarity_started" in event_types
        assert "similarity_completed" in event_types
        assert "run_completed" in event_types

    finally:
        reset_clock()


@pytest.mark.asyncio
async def test_daily_semantics_through_scheduled_runs(
    db_session: AsyncSession, mock_source: MockComprehensiveSource, mock_pipeline_service: MetacriticPipelineService
) -> None:
    """
    Verify Stage 2 daily semantics invariant works through MetacriticPipelineService:
    1. First run of day -> New Releases
    2. Second run of same day -> Browse
    3. Next calendar day -> New Releases again
    """
    # Setup browse page with additional games
    mock_source.browse_pages[1] = [
        GameCandidate(title=f"Browse #{i}", url=f"https://www.metacritic.com/game/browse-{i}/", external_id=f"browse-{i}")
        for i in range(1, 4)
    ]
    for i in range(1, 4):
        mock_source.add_game(slug=f"browse-{i}", title=f"Browse #{i}")

    # Day 1: Run #1 (New Releases)
    set_clock(FixedClock(date(2026, 9, 1)))
    try:
        res1 = await mock_pipeline_service.run_pipeline(limit=3, trigger_type="scheduled")
        assert res1.status == "completed"

        # Verify phase advanced to browse
        stmt = select(DailyCrawlState).where(DailyCrawlState.processing_date == date(2026, 9, 1))
        state1 = (await db_session.execute(stmt)).scalar_one()
        assert state1.phase == "browse"

        # Day 1: Run #2 (Browse)
        res2 = await mock_pipeline_service.run_pipeline(limit=3, trigger_type="scheduled")
        assert res2.status == "completed"
        # Games processed in run #2 should be the browse candidates
        stmt_proc = select(DailyGameProcessing.game_external_id).where(
            DailyGameProcessing.crawl_run_id == res2.crawl_run_id
        )
        proc_slugs = (await db_session.execute(stmt_proc)).scalars().all()
        assert all(slug.startswith("browse-") for slug in proc_slugs)

        # Day 2: Next calendar day resets to New Releases
        set_clock(FixedClock(date(2026, 9, 2)))
        res3 = await mock_pipeline_service.run_pipeline(limit=2, trigger_type="scheduled")
        assert res3.status == "completed"

        stmt_state2 = select(DailyCrawlState).where(DailyCrawlState.processing_date == date(2026, 9, 2))
        state2 = (await db_session.execute(stmt_state2)).scalar_one()
        assert state2.phase == "browse"  # Advanced from new_releases

        # Check duplicate audit for both days
        stmt_dups = (
            select(DailyGameProcessing.processing_date, DailyGameProcessing.game_external_id)
            .group_by(DailyGameProcessing.processing_date, DailyGameProcessing.game_external_id)
            .having(func.count(DailyGameProcessing.id) > 1)
        )
        dups = (await db_session.execute(stmt_dups)).all()
        assert len(dups) == 0, "No game can be processed more than once on the same calendar day"

    finally:
        reset_clock()


@pytest.mark.asyncio
async def test_manual_vs_scheduled_equivalence(
    db_session: AsyncSession, mock_pipeline_service: MetacriticPipelineService
) -> None:
    """Verify manual and scheduled executions use the exact same pipeline service and logic."""
    clock = FixedClock(date(2026, 9, 1))
    set_clock(clock)
    try:
        res_sched = await mock_pipeline_service.run_pipeline(limit=2, trigger_type="scheduled")
        assert res_sched.status == "completed"

        # Check trigger type
        stmt_s = select(CrawlRun.trigger_type).where(CrawlRun.id == res_sched.crawl_run_id)
        trig_s = (await db_session.execute(stmt_s)).scalar_one()
        assert trig_s == "scheduled"

        res_man = await mock_pipeline_service.run_pipeline(limit=2, trigger_type="manual")
        assert res_man.status == "completed"

        stmt_m = select(CrawlRun.trigger_type).where(CrawlRun.id == res_man.crawl_run_id)
        trig_m = (await db_session.execute(stmt_m)).scalar_one()
        assert trig_m == "manual"

    finally:
        reset_clock()


@pytest.mark.asyncio
async def test_downstream_review_failure_isolation(
    db_session: AsyncSession, mock_source: MockComprehensiveSource, mock_pipeline_service: MetacriticPipelineService
) -> None:
    """
    Verify failure boundary:
    When downstream review enrichment fails for Game #1,
    Game #1 remains persisted, error is isolated, other games continue, and status becomes 'partial'.
    """
    set_clock(FixedClock(date(2026, 9, 1)))
    mock_source.fail_reviews_on_slugs.add("game-1")

    try:
        res = await mock_pipeline_service.run_pipeline(limit=2, trigger_type="scheduled")

        assert res.status == "partial"
        assert res.failed_count == 1  # game-1 had downstream error
        assert res.processed_count == 1  # game-2 succeeded

        # Game-1 MUST remain persisted in the database!
        stmt = select(Game).where(Game.metacritic_slug == "game-1")
        game1 = (await db_session.execute(stmt)).scalar_one_or_none()
        assert game1 is not None, "Game #1 must not be rolled back due to downstream review failure"

        # Verify reviews_failed event recorded
        stmt_ev = select(CrawlRunEvent).where(
            CrawlRunEvent.crawl_run_id == res.crawl_run_id,
            CrawlRunEvent.event_type == "reviews_failed",
        )
        rev_ev = (await db_session.execute(stmt_ev)).scalar_one_or_none()
        assert rev_ev is not None

    finally:
        reset_clock()


@pytest.mark.asyncio
async def test_cost_control_skips_recorded_in_events(
    db_session: AsyncSession, mock_pipeline_service: MetacriticPipelineService
) -> None:
    """
    Verify that reprocessing existing games uses SHA-256 fingerprint cost controls
    to skip LLM and embedding calls, recording skip events rather than failures.
    """
    set_clock(FixedClock(date(2026, 9, 1)))
    try:
        # Run 1: generates summaries and embeddings
        res1 = await mock_pipeline_service.run_pipeline(limit=1, trigger_type="scheduled")
        assert res1.summaries_generated_count == 2
        assert res1.embeddings_generated_count == 1

        # Advance to next day so the same game becomes eligible again
        set_clock(FixedClock(date(2026, 9, 2)))
        res2 = await mock_pipeline_service.run_pipeline(limit=1, trigger_type="scheduled")
        assert res2.status == "completed"

        # Second run: unchanged review input and game text -> skipped!
        assert res2.summaries_generated_count == 0
        assert res2.embeddings_generated_count == 0

        # Verify summary_skipped and embedding_skipped events were emitted
        stmt_ev = select(CrawlRunEvent.event_type).where(
            CrawlRunEvent.crawl_run_id == res2.crawl_run_id
        )
        types = (await db_session.execute(stmt_ev)).scalars().all()
        assert "summary_skipped" in types
        assert "embedding_skipped" in types

    finally:
        reset_clock()
