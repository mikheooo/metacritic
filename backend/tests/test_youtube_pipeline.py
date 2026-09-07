from datetime import date

import pytest
from sqlalchemy import select

from app.core.clock import FixedClock, reset_clock, set_clock
from app.models.crawl import CrawlRun, CrawlRunEvent
from app.models.youtube import GameYouTubeVideo
from app.services.ai import GameEmbeddingService, ReviewEnrichmentService, SimilarGamesService
from app.services.ai.embedding_provider import FakeEmbeddingProvider
from app.services.ai.summarizer import FakeReviewSummarizer
from app.services.crawler.dtos import GameCandidate
from app.services.crawler.pipeline_service import MetacriticPipelineService
from app.services.youtube import (
    FakeTranscriptProvider,
    FakeVideoSummarizer,
    FakeYouTubeSearchProvider,
    TranscriptResult,
    YouTubeEnrichmentService,
    YouTubeVideoCandidate,
)
from tests.test_pipeline_service import MockComprehensiveSource


@pytest.fixture(autouse=True)
def setup_clock():
    set_clock(FixedClock(date(2026, 4, 15)))
    yield
    reset_clock()


@pytest.mark.asyncio
async def test_full_pipeline_integrates_youtube_substage(db_session: any) -> None:
    source = MockComprehensiveSource()
    source.add_game(slug="dragons-dogma-2", title="Dragon's Dogma 2")
    source.new_releases_list.append(
        GameCandidate(
            title="Dragon's Dogma 2",
            url="https://www.metacritic.com/game/dragons-dogma-2/",
            external_id="dragons-dogma-2",
        )
    )

    enrichment_service = ReviewEnrichmentService(
        db=db_session,
        source=source,
        summarizer=FakeReviewSummarizer(),
    )
    embedding_service = GameEmbeddingService(
        db=db_session,
        provider=FakeEmbeddingProvider(),
    )
    similarity_service = SimilarGamesService(db=db_session)

    # Setup Fake YouTube enrichment
    cand = YouTubeVideoCandidate(
        video_id="dd2_play",
        title="Dragon's Dogma 2 Gameplay Walkthrough Part 1",
        channel_id="chan_dd2",
        channel_title="ArisenPro",
        published_at=None,
        thumbnail_url="https://img/dd2.jpg",
        duration_seconds=5400,
        view_count=1_500_000,
        like_count=75_000,
        url="https://www.youtube.com/watch?v=dd2_play",
        description="Epic gameplay in Vermund",
    )
    search_provider = FakeYouTubeSearchProvider(canned_candidates=[cand])
    transcript_provider = FakeTranscriptProvider(
        canned_transcripts={
            "dd2_play": TranscriptResult(
                text="The dragon took our heart. Today we customize our Pawn and venture forth into the kingdom.",
                language="en",
                is_generated=False,
                provider="fake-transcript-provider",
                segment_count=30,
            )
        }
    )
    video_summarizer = FakeVideoSummarizer()

    youtube_service = YouTubeEnrichmentService(
        db=db_session,
        search_provider=search_provider,
        transcript_provider=transcript_provider,
        summarizer=video_summarizer,
    )

    pipeline = MetacriticPipelineService(
        db=db_session,
        source=source,
        enrichment_service=enrichment_service,
        embedding_service=embedding_service,
        similarity_service=similarity_service,
        youtube_service=youtube_service,
    )

    result = await pipeline.run_pipeline(limit=1, trigger_type="scheduled")

    assert result.status == "completed"
    assert result.processed_count == 1
    assert result.youtube_processed_count == 1

    # Check CrawlRun record in DB
    stmt_run = select(CrawlRun).where(CrawlRun.id == result.crawl_run_id)
    run_obj = (await db_session.execute(stmt_run)).scalar_one()
    assert run_obj.youtube_processed_count == 1

    # Check YouTube events
    stmt_events = (
        select(CrawlRunEvent)
        .where(CrawlRunEvent.crawl_run_id == result.crawl_run_id)
        .order_by(CrawlRunEvent.id.asc())
    )
    events = (await db_session.execute(stmt_events)).scalars().all()
    event_types = [e.event_type for e in events]
    stages = [e.stage for e in events]

    assert "youtube" in stages
    assert "youtube_search_started" in event_types
    assert "youtube_video_selected" in event_types
    assert "youtube_transcript_fetched" in event_types
    assert "youtube_summary_generated" in event_types

    # Check DB record GameYouTubeVideo
    stmt_vid = select(GameYouTubeVideo).where(GameYouTubeVideo.youtube_video_id == "dd2_play")
    vid_obj = (await db_session.execute(stmt_vid)).scalar_one_or_none()
    assert vid_obj is not None
    assert vid_obj.status == "enriched"
    assert vid_obj.summary is not None
    assert vid_obj.transcript is not None
