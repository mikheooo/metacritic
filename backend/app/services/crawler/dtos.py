import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


def normalize_canonical_url(url: str) -> str:
    """
    Normalize Metacritic game URL into canonical format:
    https://www.metacritic.com/game/<slug>/
    Strips query parameters, anchors, duplicate slashes, and ensures trailing slash.
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    if not path.startswith("/game/"):
        # If relative slug passed, prepend /game/
        clean_slug = path.strip("/")
        path = f"/game/{clean_slug}"
    # Extract only the game slug part (e.g. /game/elden-ring)
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "game":
        slug = parts[1].lower()
        return f"https://www.metacritic.com/game/{slug}/"
    return f"https://www.metacritic.com{path}/"


def extract_canonical_slug(url_or_slug: str) -> str:
    """
    Extract canonical slug from URL or raw slug string.
    e.g. 'https://www.metacritic.com/game/elden-ring/?platform=ps5' -> 'elden-ring'
    """
    canonical = normalize_canonical_url(url_or_slug)
    match = re.search(r"/game/([^/]+)/", canonical)
    if match:
        return match.group(1).lower()
    return url_or_slug.strip("/").split("/")[-1].lower()


@dataclass(frozen=True)
class GameCandidate:
    title: str
    url: str
    external_id: str
    release_date: str | None = None
    cover_url: str | None = None


@dataclass
class PlatformScore:
    platform_name: str
    platform_slug: str
    metascore: int | None = None
    userscore: float | None = None


@dataclass
class GameDetails:
    external_id: str
    metacritic_url: str
    metacritic_slug: str
    title: str
    cover_url: str | None = None
    developer: str | None = None
    description: str | None = None
    trailer_url: str | None = None
    platforms: list[PlatformScore] = field(default_factory=list)


@dataclass
class BrowsePage:
    candidates: list[GameCandidate]
    page: int
    has_next: bool = False
    total_pages: int | None = None


@dataclass
class ReviewItem:
    external_id: str
    review_type: str  # "critic" or "user"
    author: str | None
    score: float | None
    body: str
    published_at: str | None
    platform_slug: str | None
    source_url: str | None = None
    sentiment_category: str = "mixed"  # "positive", "mixed", "negative"
    content_hash: str = ""


@dataclass
class ReviewPage:
    reviews: list[ReviewItem]
    current_page: int
    has_next_page: bool = False
    total_pages: int | None = None


@dataclass(frozen=True)
class ReviewForSummary:
    external_id: str
    review_type: str
    author: str | None
    score: float | None
    body: str
    platform_slug: str | None
    sentiment_category: str
    content_hash: str
