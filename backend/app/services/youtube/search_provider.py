import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from app.core.config import settings
from app.models.game import Game

logger = logging.getLogger(__name__)

# ISO 8601 duration regex: PT#H#M#S
ISO8601_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def parse_iso8601_duration(duration_str: str | None) -> int | None:
    """Parse ISO 8601 duration string (e.g. PT1H23M45S) into total seconds."""
    if not duration_str:
        return None
    match = ISO8601_DURATION_RE.match(duration_str)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class YouTubeVideoCandidate:
    video_id: str
    title: str
    channel_id: str | None
    channel_title: str | None
    published_at: datetime | None
    thumbnail_url: str | None
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    url: str
    description: str


class YouTubeError(Exception):
    """Base error for YouTube operations."""


class YouTubeConfigError(YouTubeError):
    """Raised when YouTube API configuration/key is missing or invalid."""


class YouTubeQuotaError(YouTubeError):
    """Raised when YouTube API quota is exceeded (403 quotaExceeded)."""


class YouTubeApiError(YouTubeError):
    """Raised on non-quota HTTP or network errors when calling YouTube API."""


class YouTubeSearchProvider(Protocol):
    """Contract for discovering YouTube Let's Play candidate videos."""

    async def search_lets_plays(
        self,
        game: Game,
    ) -> list[YouTubeVideoCandidate]: ...


class YouTubeDataApiProvider:
    """
    Official Google YouTube Data API v3 search provider.
    Uses search.list with type=video and videos.list for accurate statistics and durations.
    """

    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or settings.YOUTUBE_API_KEY
        self.max_results = max_results or settings.YOUTUBE_SEARCH_RESULTS_LIMIT
        self.timeout = timeout

    def build_search_query(self, game_title: str) -> str:
        """Deterministic search query builder."""
        cleaned_title = game_title.strip()
        return f'"{cleaned_title}" gameplay lets play'

    async def search_lets_plays(self, game: Game) -> list[YouTubeVideoCandidate]:
        if not self.api_key:
            raise YouTubeConfigError(
                "YOUTUBE_API_KEY is not configured. YouTube discovery cannot proceed."
            )

        query = self.build_search_query(game.title)
        logger.info(
            "Executing YouTube Data API search for game '%s' (query: %s)", game.title, query
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 1. Search videos
            search_params: dict[str, str | int] = {
                "part": "snippet",
                "type": "video",
                "maxResults": min(self.max_results, 50),
                "q": query,
                "key": self.api_key,
            }
            try:
                resp = await client.get(self.SEARCH_URL, params=search_params)
            except httpx.RequestError as exc:
                raise YouTubeApiError(f"Network error calling YouTube search API: {exc}") from exc

            if resp.status_code == 403:
                body = resp.text
                if "quotaExceeded" in body or "dailyLimitExceeded" in body:
                    raise YouTubeQuotaError("YouTube Data API quota exceeded (403 quotaExceeded)")
                raise YouTubeApiError(f"YouTube search API returned 403: {body}")
            elif resp.status_code != 200:
                raise YouTubeApiError(
                    f"YouTube search API returned status {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            items = data.get("items", [])
            if not items:
                logger.info("No YouTube search candidates found for '%s'", game.title)
                return []

            video_ids = [
                item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")
            ]
            if not video_ids:
                return []

            # 2. Fetch video metadata, contentDetails (duration), and statistics (views, likes)
            videos_params = {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(video_ids),
                "key": self.api_key,
            }
            try:
                vid_resp = await client.get(self.VIDEOS_URL, params=videos_params)
            except httpx.RequestError as exc:
                raise YouTubeApiError(f"Network error calling YouTube videos API: {exc}") from exc

            if vid_resp.status_code == 403:
                body = vid_resp.text
                if "quotaExceeded" in body or "dailyLimitExceeded" in body:
                    raise YouTubeQuotaError("YouTube Data API quota exceeded on videos.list")
                raise YouTubeApiError(f"YouTube videos API returned 403: {body}")
            elif vid_resp.status_code != 200:
                raise YouTubeApiError(
                    f"YouTube videos API returned status {vid_resp.status_code}: {vid_resp.text}"
                )

            vid_data = vid_resp.json()
            vid_items = vid_data.get("items", [])

            candidates: list[YouTubeVideoCandidate] = []
            for v in vid_items:
                vid_id = v.get("id")
                if not vid_id:
                    continue
                snippet = v.get("snippet", {})
                content_details = v.get("contentDetails", {})
                statistics = v.get("statistics", {})

                title = snippet.get("title", "")
                description = snippet.get("description", "")
                channel_id = snippet.get("channelId")
                channel_title = snippet.get("channelTitle")
                published_str = snippet.get("publishedAt")
                published_at: datetime | None = None
                if published_str:
                    try:
                        published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except ValueError:
                        published_at = None

                thumbnails = snippet.get("thumbnails", {})
                # Pick highest quality thumbnail available
                thumb_url = (
                    thumbnails.get("maxres", {}).get("url")
                    or thumbnails.get("standard", {}).get("url")
                    or thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

                duration_str = content_details.get("duration")
                duration_seconds = parse_iso8601_duration(duration_str)

                view_count_raw = statistics.get("viewCount")
                view_count = int(view_count_raw) if view_count_raw is not None else None

                like_count_raw = statistics.get("likeCount")
                like_count = int(like_count_raw) if like_count_raw is not None else None

                candidates.append(
                    YouTubeVideoCandidate(
                        video_id=vid_id,
                        title=title,
                        channel_id=channel_id,
                        channel_title=channel_title,
                        published_at=published_at,
                        thumbnail_url=thumb_url,
                        duration_seconds=duration_seconds,
                        view_count=view_count,
                        like_count=like_count,
                        url=f"https://www.youtube.com/watch?v={vid_id}",
                        description=description,
                    )
                )

            return candidates


class FakeYouTubeSearchProvider:
    """Hermetic test provider for YouTube candidate searches."""

    def __init__(
        self,
        canned_candidates: list[YouTubeVideoCandidate] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        self.canned_candidates: list[YouTubeVideoCandidate] = canned_candidates or []
        self.exception_to_raise = exception_to_raise
        self.searched_games: list[Game] = []

    async def search_lets_plays(self, game: Game) -> list[YouTubeVideoCandidate]:
        self.searched_games.append(game)
        if self.exception_to_raise:
            raise self.exception_to_raise
        return list(self.canned_candidates)
