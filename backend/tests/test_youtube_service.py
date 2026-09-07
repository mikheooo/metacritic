import pytest
from sqlalchemy import select

from app.models.game import Game
from app.models.youtube import GameYouTubeVideo, YouTubeTranscript
from app.services.youtube.search_provider import (
    FakeYouTubeSearchProvider,
    YouTubeApiError,
    YouTubeVideoCandidate,
)
from app.services.youtube.service import YouTubeEnrichmentService
from app.services.youtube.summarizer import FakeVideoSummarizer
from app.services.youtube.transcript_provider import (
    FakeTranscriptProvider,
    TranscriptResult,
    TranscriptUnavailableError,
)


@pytest.mark.asyncio
async def test_search_refresh_ttl_skips_fresh(db_session: any) -> None:
    game = Game(
        title="Helldivers 2",
        metacritic_slug="helldivers-2",
        metacritic_url="https://metacritic.com/game/helldivers-2",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    cand = YouTubeVideoCandidate(
        video_id="hd2_vid",
        title="Helldivers 2 Super Helldive Gameplay Let's Play",
        channel_id="c1",
        channel_title="FreedomFighter",
        published_at=None,
        thumbnail_url="https://img/hd2.jpg",
        duration_seconds=3600,
        view_count=800_000,
        like_count=40_000,
        url="https://www.youtube.com/watch?v=hd2_vid",
        description="Spreading democracy gameplay",
    )

    search_provider = FakeYouTubeSearchProvider(canned_candidates=[cand])
    transcript_provider = FakeTranscriptProvider(
        canned_transcripts={
            "hd2_vid": TranscriptResult(
                text="Dropping into Malevelon Creek for liberty.",
                language="en",
                is_generated=False,
                provider="fake-transcript-provider",
                segment_count=20,
            )
        }
    )
    summarizer = FakeVideoSummarizer()

    service = YouTubeEnrichmentService(
        db=db_session,
        search_provider=search_provider,
        transcript_provider=transcript_provider,
        summarizer=summarizer,
    )

    # 1. First run: discovers, fetches transcript, generates summary
    res1 = await service.enrich_game(game.id)
    assert res1.status == "enriched"
    assert len(search_provider.searched_games) == 1

    # 2. Second run without force: skips search because refreshed_at is current (< 24h)
    res2 = await service.enrich_game(game.id, force=False)
    assert res2.status == "skipped_fresh"
    assert res2.video_id == "hd2_vid"
    # Search provider was NOT called again
    assert len(search_provider.searched_games) == 1


@pytest.mark.asyncio
async def test_failure_isolation_search_error_preserves_game(db_session: any) -> None:
    game = Game(
        title="Silent Hill 2",
        metacritic_slug="silent-hill-2",
        metacritic_url="https://metacritic.com/game/silent-hill-2",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    search_provider = FakeYouTubeSearchProvider(
        exception_to_raise=YouTubeApiError("Network timeout connecting to YouTube")
    )
    service = YouTubeEnrichmentService(
        db=db_session,
        search_provider=search_provider,
    )

    res = await service.enrich_game(game.id)
    assert res.status == "failed"
    assert "Network timeout" in (res.error or "")

    # Game still exists in database!
    stmt = select(Game).where(Game.id == game.id)
    g_res = await db_session.execute(stmt)
    assert g_res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_failure_isolation_transcript_unavailable_persists_metadata(db_session: any) -> None:
    game = Game(
        title="Final Fantasy VII Rebirth",
        metacritic_slug="final-fantasy-vii-rebirth",
        metacritic_url="https://metacritic.com/game/final-fantasy-vii-rebirth",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    cand = YouTubeVideoCandidate(
        video_id="ff7_vid",
        title="Final Fantasy VII Rebirth Full Gameplay Walkthrough Part 1",
        channel_id="c1",
        channel_title="CloudStrife",
        published_at=None,
        thumbnail_url="https://img/ff7.jpg",
        duration_seconds=7200,
        view_count=1_200_000,
        like_count=50_000,
        url="https://www.youtube.com/watch?v=ff7_vid",
        description="Exploring Kalm and Grasslands",
    )

    search_provider = FakeYouTubeSearchProvider(canned_candidates=[cand])
    # No transcript available
    transcript_provider = FakeTranscriptProvider(
        exception_to_raise=TranscriptUnavailableError("Transcripts are disabled for this video")
    )

    service = YouTubeEnrichmentService(
        db=db_session,
        search_provider=search_provider,
        transcript_provider=transcript_provider,
    )

    res = await service.enrich_game(game.id)
    assert res.status == "transcript_unavailable"
    assert res.video_id == "ff7_vid"

    # Verify GameYouTubeVideo is persisted with status transcript_unavailable
    stmt = select(GameYouTubeVideo).where(GameYouTubeVideo.game_id == game.id)
    v_res = await db_session.execute(stmt)
    video_row = v_res.scalar_one_or_none()
    assert video_row is not None
    assert video_row.status == "transcript_unavailable"
    assert video_row.selection_rank == 1


@pytest.mark.asyncio
async def test_failure_isolation_llm_failure_preserves_transcript(db_session: any) -> None:
    game = Game(
        title="Tekken 8",
        metacritic_slug="tekken-8",
        metacritic_url="https://metacritic.com/game/tekken-8",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    cand = YouTubeVideoCandidate(
        video_id="t8_vid",
        title="Tekken 8 Story Mode Gameplay Playthrough",
        channel_id="c1",
        channel_title="Fighter",
        published_at=None,
        thumbnail_url="https://img/t8.jpg",
        duration_seconds=4000,
        view_count=600_000,
        like_count=30_000,
        url="https://www.youtube.com/watch?v=t8_vid",
        description="Tekken 8 full story",
    )

    search_provider = FakeYouTubeSearchProvider(canned_candidates=[cand])
    transcript_provider = FakeTranscriptProvider(
        canned_transcripts={
            "t8_vid": TranscriptResult(
                text="Jin and Kazuya clash in the ultimate battle.",
                language="en",
                is_generated=False,
                provider="fake-transcript-provider",
                segment_count=15,
            )
        }
    )

    class FailingSummarizer:
        provider = "failing-llm"
        model = "fake-model"
        prompt_version = "v1"
        language = "ru"

        async def summarize_video_transcript(self, *args: any, **kwargs: any) -> None:
            raise RuntimeError("LLM rate limit reached 429")

    service = YouTubeEnrichmentService(
        db=db_session,
        search_provider=search_provider,
        transcript_provider=transcript_provider,
        summarizer=FailingSummarizer(),  # type: ignore[arg-type]
    )

    res = await service.enrich_game(game.id)
    assert res.summary_status == "failed"

    # Transcript is preserved in DB!
    stmt = (
        select(YouTubeTranscript)
        .join(GameYouTubeVideo, YouTubeTranscript.game_youtube_video_id == GameYouTubeVideo.id)
        .where(GameYouTubeVideo.game_id == game.id)
    )
    t_res = await db_session.execute(stmt)
    transcript_row = t_res.scalar_one_or_none()
    assert transcript_row is not None
    assert "Jin and Kazuya clash" in transcript_row.text
