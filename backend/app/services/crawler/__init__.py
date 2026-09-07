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
from app.services.crawler.parser import (
    MetacriticParser,
    is_navigation_or_category_label,
    normalize_platform_name,
    normalize_platform_slug,
)
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
    "normalize_platform_name",
    "normalize_platform_slug",
    "is_navigation_or_category_label",
    "MetacriticClient",
    "CrawlLock",
    "CrawlAlreadyRunningError",
    "IngestionService",
    "IngestionResult",
]
