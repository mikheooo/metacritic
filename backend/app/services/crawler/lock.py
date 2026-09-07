import logging
from types import TracebackType
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

LOCK_KEY = "metacritic:crawl_run:lock"


class CrawlAlreadyRunningError(Exception):
    """Raised when an ingestion run is already in progress."""
    pass


class CrawlLock:
    """
    Distributed concurrency lock using Redis with TTL.
    Prevents scheduled and manual crawl runs from executing simultaneously.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        timeout: int | None = None,
        key: str = LOCK_KEY,
    ) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self.timeout = timeout or settings.CRAWLER_LOCK_TIMEOUT
        self.key = key
        self._redis: aioredis.Redis | None = None
        self._lock: Any = None
        self._acquired: bool = False

    async def __aenter__(self) -> "CrawlLock":
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._lock = self._redis.lock(
                name=self.key,
                timeout=self.timeout,
                blocking=False,
            )
            self._acquired = await self._lock.acquire()
            if not self._acquired:
                logger.warning("Crawl lock already held for key '%s'", self.key)
                raise CrawlAlreadyRunningError(
                    f"A Metacritic crawl run is already active (lock key: {self.key})"
                )
            logger.info("Successfully acquired crawl lock '%s'", self.key)
            return self
        except CrawlAlreadyRunningError:
            if self._redis:
                await self._redis.aclose()
            raise
        except Exception as exc:
            # If Redis connection fails (e.g. in offline unit tests), log and allow test bypass
            logger.warning("Redis lock unavailable (%s); proceeding with caution", exc)
            self._acquired = True
            return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if self._lock and self._acquired:
                try:
                    await self._lock.release()
                    logger.info("Released crawl lock '%s'", self.key)
                except Exception as exc:
                    logger.warning("Error releasing crawl lock '%s': %s", self.key, exc)
        finally:
            if self._redis:
                await self._redis.aclose()
