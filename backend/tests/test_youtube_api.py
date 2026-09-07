import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.youtube import GameYouTubeVideo, YouTubeSummary, YouTubeTranscript


@pytest.mark.asyncio
async def test_game_detail_api_returns_lets_play_without_raw_transcript(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # 1. Create a Game with YouTube Let's Play, Transcript, and Summary
    game = Game(
        title="Persona 3 Reload",
        metacritic_slug="persona-3-reload",
        metacritic_url="https://metacritic.com/game/persona-3-reload",
    )
    db_session.add(game)
    await db_session.flush()

    video = GameYouTubeVideo(
        game_id=game.id,
        youtube_video_id="p3r_123",
        url="https://www.youtube.com/watch?v=p3r_123",
        title="Persona 3 Reload Full Playthrough - Part 1",
        channel_id="chan_p3r",
        channel_title="AtlusMaster",
        thumbnail_url="https://img.youtube.com/vi/p3r_123/hqdefault.jpg",
        duration_seconds=7200,
        view_count=1_234_567,
        like_count=65_000,
        search_query='"Persona 3 Reload" gameplay lets play',
        selection_rank=1,
        selection_reason="Most-viewed relevant candidate with an accessible transcript",
        status="enriched",
    )
    db_session.add(video)
    await db_session.flush()

    transcript = YouTubeTranscript(
        game_youtube_video_id=video.id,
        provider="youtube-transcript-api",
        language="en",
        is_generated=True,
        text="A very long full secret raw transcript text containing 5000 words that must not be exposed.",
        text_hash="abc123hash",
        segment_count=120,
    )
    db_session.add(transcript)

    summary = YouTubeSummary(
        game_youtube_video_id=video.id,
        summary="Блогер проходит вступительную главу, исследует Тартар и высоко оценивает обновлённый UI.",
        key_points=[
            "Великолепный визуальный стиль и анимация меню",
            "Динамичная пошаговая боевая система с переключением персон",
            "Отличная перезапись классического саундтрека",
        ],
        provider="openrouter",
        model="openai/gpt-4o-mini",
        prompt_version="v1",
        summary_language="ru",
        input_fingerprint="fp_summary_123",
        input_tokens=1500,
        output_tokens=250,
    )
    db_session.add(summary)
    await db_session.commit()

    # 2. Call GET /api/games/{id}
    resp = await client.get(f"/api/games/{game.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert "lets_play" in data
    lp = data["lets_play"]
    assert lp is not None
    assert lp["youtube_video_id"] == "p3r_123"
    assert lp["title"] == "Persona 3 Reload Full Playthrough - Part 1"
    assert lp["channel_title"] == "AtlusMaster"
    assert lp["url"] == "https://www.youtube.com/watch?v=p3r_123"
    assert lp["thumbnail_url"] == "https://img.youtube.com/vi/p3r_123/hqdefault.jpg"
    assert lp["view_count"] == 1_234_567
    assert lp["duration_seconds"] == 7200
    assert lp["status"] == "enriched"
    assert lp["selection_rank"] == 1

    # Transcript metadata check
    assert "transcript" in lp
    assert lp["transcript"]["language"] == "en"
    assert lp["transcript"]["is_generated"] is True
    assert lp["transcript"]["provider"] == "youtube-transcript-api"

    # Raw transcript text MUST NOT be exposed in the response
    assert "text" not in lp["transcript"]
    assert "A very long full secret raw transcript" not in str(data)

    # Summary check
    assert "summary" in lp
    assert "Блогер проходит вступительную главу" in lp["summary"]["text"]
    assert len(lp["summary"]["key_points"]) == 3
    assert lp["summary"]["provider"] == "openrouter"
    assert lp["summary"]["model"] == "openai/gpt-4o-mini"
    assert lp["summary"]["prompt_version"] == "v1"


@pytest.mark.asyncio
async def test_game_detail_api_empty_lets_play_when_not_enriched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    game = Game(
        title="Unenriched Game",
        metacritic_slug="unenriched-game",
        metacritic_url="https://metacritic.com/game/unenriched-game",
    )
    db_session.add(game)
    await db_session.commit()

    resp = await client.get(f"/api/games/{game.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert "lets_play" in data
    assert data["lets_play"] is None
