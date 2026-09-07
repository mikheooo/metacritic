import asyncio
import logging

import httpx

from app.core.config import settings
from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    ReviewPage,
    normalize_canonical_url,
)
from app.services.crawler.parser import MetacriticParser

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


class MetacriticClient:
    """
    Production HTTP client for Metacritic with polite rate limiting,
    bounded concurrency, timeouts, and exponential backoff retry.
    """

    def __init__(
        self,
        base_url: str | None = None,
        rate_limit_delay: float | None = None,
        timeout: float | None = None,
        max_concurrency: int = 3,
    ) -> None:
        self.base_url = (base_url or settings.METACRITIC_BASE_URL).rstrip("/")
        self.rate_limit_delay = (
            rate_limit_delay if rate_limit_delay is not None else settings.CRAWLER_RATE_LIMIT_DELAY
        )
        self.timeout = timeout if timeout is not None else settings.CRAWLER_TIMEOUT
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _fetch(self, url: str, max_retries: int = 3) -> str:
        """Fetch URL with rate limiting, bounded concurrency, and exponential backoff."""
        client = await self._get_client()
        attempt = 0
        backoff = 1.0

        async with self._semaphore:
            if self.rate_limit_delay > 0:
                await asyncio.sleep(self.rate_limit_delay)

            while attempt <= max_retries:
                try:
                    logger.info("Fetching URL (attempt %d/%d): %s", attempt + 1, max_retries + 1, url)
                    response = await client.get(url)
                    if response.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "Transient HTTP %d received for %s. Retrying in %.1fs...",
                            response.status_code,
                            url,
                            backoff,
                        )
                        if attempt == max_retries:
                            response.raise_for_status()
                        await asyncio.sleep(backoff)
                        backoff *= 1.5
                        attempt += 1
                        continue

                    response.raise_for_status()
                    return response.text

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    logger.warning(
                        "Network/timeout error fetching %s: %s. Retrying in %.1fs...",
                        url,
                        exc,
                        backoff,
                    )
                    if attempt == max_retries:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    attempt += 1

        raise RuntimeError(f"Failed to fetch {url} after {max_retries} retries")

    async def get_new_releases(self) -> list[GameCandidate]:
        """Fetch candidates from Games -> New Releases section."""
        url = f"{self.base_url}/game/"
        html = await self._fetch(url)
        return MetacriticParser.parse_new_releases(html)

    async def get_browse_page(self, page: int = 1) -> BrowsePage:
        """Fetch paginated games from Browse -> Newest."""
        if page <= 1:
            url = f"{self.base_url}/browse/game/all/all/all-time/new/"
        else:
            url = f"{self.base_url}/browse/game/all/all/all-time/new/?page={page}"
        html = await self._fetch(url)
        return MetacriticParser.parse_browse_page(html, page=page)

    async def get_game_details(self, url: str) -> GameDetails:
        """Fetch full game details, media, and platform scores."""
        canonical_url = normalize_canonical_url(url)
        html = await self._fetch(canonical_url)
        return MetacriticParser.parse_game_details(html, canonical_url=canonical_url)

    async def get_critic_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        """Fetch critic reviews for a given game slug."""
        url = f"{self.base_url}/game/{slug}/critic-reviews/"
        params: list[str] = []
        if platform:
            params.append(f"platform={platform}")
        if page > 1:
            params.append(f"page={page}")
        if params:
            url = f"{url}?{'&'.join(params)}"
        html = await self._fetch(url)
        return MetacriticParser.parse_critic_reviews(html, game_slug=slug, page=page)

    async def get_user_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        """Fetch user reviews for a given game slug."""
        url = f"{self.base_url}/game/{slug}/user-reviews/"
        params: list[str] = []
        if platform:
            params.append(f"platform={platform}")
        if page > 1:
            params.append(f"page={page}")
        if params:
            url = f"{url}?{'&'.join(params)}"
        html = await self._fetch(url)
        return MetacriticParser.parse_user_reviews(html, game_slug=slug, page=page)

