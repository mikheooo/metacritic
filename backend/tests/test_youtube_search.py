from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.game import Game
from app.services.youtube.search_provider import (
    YouTubeApiError,
    YouTubeConfigError,
    YouTubeDataApiProvider,
    YouTubeQuotaError,
    parse_iso8601_duration,
)


def test_parse_iso8601_duration() -> None:
    assert parse_iso8601_duration(None) is None
    assert parse_iso8601_duration("") is None
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT12M30S") == 12 * 60 + 30
    assert parse_iso8601_duration("PT1H15M") == 3600 + 15 * 60
    assert parse_iso8601_duration("PT2H30M45S") == 2 * 3600 + 30 * 60 + 45
    assert parse_iso8601_duration("INVALID") is None


def test_build_search_query_deterministic() -> None:
    provider = YouTubeDataApiProvider(api_key="test_key")
    query = provider.build_search_query("Elden Ring: Shadow of the Erdtree")
    assert query == '"Elden Ring: Shadow of the Erdtree" gameplay lets play'


@pytest.mark.asyncio
async def test_search_missing_api_key_raises_config_error() -> None:
    provider = YouTubeDataApiProvider(api_key=None)
    provider.api_key = None
    game = Game(
        id=1,
        title="Hades II",
        metacritic_slug="hades-ii",
        metacritic_url="https://metacritic.com/game/hades-ii",
    )

    with pytest.raises(YouTubeConfigError) as exc_info:
        await provider.search_lets_plays(game)
    assert "YOUTUBE_API_KEY is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_search_lets_plays_success() -> None:
    provider = YouTubeDataApiProvider(api_key="mock_api_key", max_results=5)
    game = Game(
        id=10,
        title="Balatro",
        metacritic_slug="balatro",
        metacritic_url="https://metacritic.com/game/balatro",
    )

    # Mock HTTP responses for search.list and videos.list
    search_json = {
        "items": [
            {"id": {"videoId": "vid123"}},
            {"id": {"videoId": "vid456"}},
        ]
    }
    videos_json = {
        "items": [
            {
                "id": "vid123",
                "snippet": {
                    "title": "Balatro - Full Run Gameplay Let's Play Part 1",
                    "description": "Playing Balatro poker roguelike walkthrough.",
                    "channelId": "chan1",
                    "channelTitle": "DeckBuilderPro",
                    "publishedAt": "2024-03-01T12:00:00Z",
                    "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/vid123/hqdefault.jpg"}},
                },
                "contentDetails": {"duration": "PT45M10S"},
                "statistics": {"viewCount": "125000", "likeCount": "4500"},
            },
            {
                "id": "vid456",
                "snippet": {
                    "title": "Balatro - Insane Joker Build Walkthrough",
                    "description": "Full gameplay playthrough.",
                    "channelId": "chan2",
                    "channelTitle": "RogueGamer",
                    "publishedAt": "2024-03-02T15:30:00Z",
                    "thumbnails": {
                        "medium": {"url": "https://i.ytimg.com/vi/vid456/mqdefault.jpg"}
                    },
                },
                "contentDetails": {"duration": "PT1H10M"},
                "statistics": {"viewCount": "350000", "likeCount": "12000"},
            },
        ]
    }

    mock_resp_search = MagicMock()
    mock_resp_search.status_code = 200
    mock_resp_search.json.return_value = search_json

    mock_resp_videos = MagicMock()
    mock_resp_videos.status_code = 200
    mock_resp_videos.json.return_value = videos_json

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_resp_search, mock_resp_videos]
        candidates = await provider.search_lets_plays(game)

        assert len(candidates) == 2
        assert mock_get.call_count == 2

        # Verify search call parameters
        first_call_params = mock_get.call_args_list[0].kwargs["params"]
        assert first_call_params["type"] == "video"
        assert first_call_params["q"] == '"Balatro" gameplay lets play'
        assert first_call_params["key"] == "mock_api_key"

        # Verify candidate 1
        c1 = candidates[0]
        assert c1.video_id == "vid123"
        assert c1.title == "Balatro - Full Run Gameplay Let's Play Part 1"
        assert c1.channel_title == "DeckBuilderPro"
        assert c1.view_count == 125000
        assert c1.like_count == 4500
        assert c1.duration_seconds == 45 * 60 + 10
        assert c1.url == "https://www.youtube.com/watch?v=vid123"

        # Verify candidate 2
        c2 = candidates[1]
        assert c2.video_id == "vid456"
        assert c2.view_count == 350000
        assert c2.duration_seconds == 70 * 60


@pytest.mark.asyncio
async def test_search_quota_exceeded_raises_quota_error() -> None:
    provider = YouTubeDataApiProvider(api_key="mock_key")
    game = Game(
        id=1,
        title="Elden Ring",
        metacritic_slug="elden-ring",
        metacritic_url="https://metacritic.com/game/elden-ring",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(YouTubeQuotaError) as exc_info:
            await provider.search_lets_plays(game)
        assert "quota exceeded" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_search_network_error_raises_api_error() -> None:
    provider = YouTubeDataApiProvider(api_key="mock_key")
    game = Game(
        id=1,
        title="Elden Ring",
        metacritic_slug="elden-ring",
        metacritic_url="https://metacritic.com/game/elden-ring",
    )

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Connection timed out")):
        with pytest.raises(YouTubeApiError) as exc_info:
            await provider.search_lets_plays(game)
        assert "Network error" in str(exc_info.value)
