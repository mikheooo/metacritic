from datetime import UTC, datetime

import pytest

from app.models.game import Game
from app.services.youtube.relevance import (
    evaluate_candidate_relevance,
    sort_candidates_by_views,
)
from app.services.youtube.search_provider import (
    FakeYouTubeSearchProvider,
    YouTubeVideoCandidate,
)
from app.services.youtube.service import YouTubeEnrichmentService
from app.services.youtube.summarizer import FakeVideoSummarizer
from app.services.youtube.transcript_provider import (
    FakeTranscriptProvider,
    TranscriptResult,
)


def make_candidate(
    vid_id: str,
    title: str,
    views: int,
    duration: int = 3600,
    desc: str = "Gameplay playthrough",
) -> YouTubeVideoCandidate:
    return YouTubeVideoCandidate(
        video_id=vid_id,
        title=title,
        channel_id="c1",
        channel_title="Gamer",
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        thumbnail_url=f"https://img/{vid_id}.jpg",
        duration_seconds=duration,
        view_count=views,
        like_count=views // 20,
        url=f"https://www.youtube.com/watch?v={vid_id}",
        description=desc,
    )


def test_relevance_filter_rejects_trailers_ost_reviews_and_unrelated() -> None:
    game_title = "Metaphor: ReFantazio"

    # Relevant Let's Play
    cand_valid = make_candidate(
        "v1", "Metaphor: ReFantazio - Full Gameplay Walkthrough Part 1", 500_000
    )
    res_valid = evaluate_candidate_relevance(cand_valid, game_title)
    assert res_valid.is_relevant is True

    # Trailer
    cand_trailer = make_candidate(
        "v2", "Metaphor: ReFantazio - Official Launch Trailer", 20_000_000
    )
    res_trailer = evaluate_candidate_relevance(cand_trailer, game_title)
    assert res_trailer.is_relevant is False
    assert "trailer" in res_trailer.reason.lower()

    # OST / Soundtrack
    cand_ost = make_candidate(
        "v3", "Metaphor: ReFantazio - Original Soundtrack OST Full Album", 1_000_000
    )
    res_ost = evaluate_candidate_relevance(cand_ost, game_title)
    assert res_ost.is_relevant is False
    assert "soundtrack" in res_ost.reason.lower()

    # Review
    cand_review = make_candidate(
        "v4", "Metaphor: ReFantazio - Before You Buy Video Review", 3_000_000
    )
    res_review = evaluate_candidate_relevance(cand_review, game_title)
    assert res_review.is_relevant is False
    assert "review" in res_review.reason.lower()

    # Short / Clip
    cand_short = make_candidate(
        "v5", "Crazy Metaphor gameplay moment #shorts", 10_000_000, duration=45
    )
    res_short = evaluate_candidate_relevance(cand_short, game_title)
    assert res_short.is_relevant is False

    # Unrelated title
    cand_unrelated = make_candidate("v6", "Elden Ring Nightreign Gameplay Walkthrough", 50_000_000)
    res_unrelated = evaluate_candidate_relevance(cand_unrelated, game_title)
    assert res_unrelated.is_relevant is False


def test_synthetic_candidate_selection_popular_relevant_over_higher_views() -> None:
    """
    Synthetic candidates:
    A: relevant, 100k views
    B: relevant, 5M views
    C: trailer, 20M views
    D: unrelated, 50M views
    Expected: B selected (not C/D, and B > A by views).
    """
    game_title = "Metaphor: ReFantazio"

    cand_a = make_candidate("cand_A", "Metaphor: ReFantazio Gameplay Part 1", 100_000)
    cand_b = make_candidate("cand_B", "Metaphor: ReFantazio Full Playthrough Let's Play", 5_000_000)
    cand_c = make_candidate("cand_C", "Metaphor: ReFantazio Official Launch Trailer", 20_000_000)
    cand_d = make_candidate("cand_D", "Grand Theft Auto VI Gameplay Leak Walkthrough", 50_000_000)

    all_candidates = [cand_a, cand_b, cand_c, cand_d]

    # Filter relevant
    relevant = [
        c for c in all_candidates if evaluate_candidate_relevance(c, game_title).is_relevant
    ]
    assert len(relevant) == 2
    assert {c.video_id for c in relevant} == {"cand_A", "cand_B"}

    # Sort by views DESC
    sorted_relevant = sort_candidates_by_views(relevant)
    assert len(sorted_relevant) == 2
    assert sorted_relevant[0].video_id == "cand_B"
    assert sorted_relevant[1].video_id == "cand_A"


@pytest.mark.asyncio
async def test_transcript_fallback_selects_rank_2_when_top1_unavailable(db_session: any) -> None:
    """
    Most popular relevant A -> transcript unavailable
    Next relevant B -> transcript available
    Expected: B selected, selection_rank = 2, reason recorded.
    """
    game = Game(
        title="Astro Bot",
        metacritic_slug="astro-bot",
        metacritic_url="https://metacritic.com/game/astro-bot",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    cand_top1 = make_candidate("vid_top1", "Astro Bot 100% Walkthrough Gameplay Part 1", 10_000_000)
    cand_top2 = make_candidate("vid_top2", "Astro Bot Let's Play Full Game Playthrough", 2_000_000)

    search_provider = FakeYouTubeSearchProvider(canned_candidates=[cand_top1, cand_top2])

    # Transcript available only for cand_top2
    transcript_provider = FakeTranscriptProvider(
        canned_transcripts={
            "vid_top2": TranscriptResult(
                text="Welcome to Astro Bot today we are exploring world one.",
                language="en",
                is_generated=False,
                provider="fake-transcript-provider",
                segment_count=45,
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

    result = await service.enrich_game(game_id=game.id)

    assert result.status == "enriched"
    assert result.video_id == "vid_top2"
    assert result.selection_rank == 2
    assert "Rank #2" in (result.selection_reason or "")
    assert result.transcript_status == "fetched"
    assert result.summary_status == "generated"
