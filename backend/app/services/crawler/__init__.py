from app.services.crawler.client import MetacriticClient
from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    PlatformScore,
    extract_canonical_slug,
    normalize_canonical_url,
)
from app.services.crawler.ingestion_service import IngestionResult, IngestionService
from app.services.crawler.lock import CrawlAlreadyRunningError, CrawlLock
from app.services.crawler.parser import MetacriticParser
from app.services.crawler.source import MetacriticSource

__all__ = [
    "GameCandidate",
    "PlatformScore",
    "GameDetails",
    "BrowsePage",
    "normalize_canonical_url",
    "extract_canonical_slug",
    "MetacriticSource",
    "MetacriticParser",
    "MetacriticClient",
    "CrawlLock",
    "CrawlAlreadyRunningError",
    "IngestionService",
    "IngestionResult",
]
