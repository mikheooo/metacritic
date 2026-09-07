import hashlib
import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from app.services.crawler.dtos import (
    BrowsePage,
    GameCandidate,
    GameDetails,
    PlatformScore,
    ReviewItem,
    ReviewPage,
    extract_canonical_slug,
    normalize_canonical_url,
)

logger = logging.getLogger(__name__)


def _clean_text(val: str | None) -> str | None:
    if not val:
        return None
    cleaned = re.sub(r"\s+", " ", val).strip()
    return cleaned if cleaned else None


def _get_attr(elem: Any, attr: str) -> str | None:
    if elem is None:
        return None
    val = elem.get(attr)
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    if isinstance(val, str):
        return val
    return None


def _find_by_testid(container: Any, testid: str) -> Any:
    if container is None:
        return None
    return container.find(None, attrs={"data-testid": testid})


def _find_all_by_testid(container: Any, testid: str) -> list[Any]:
    if container is None:
        return []
    return list(container.find_all(None, attrs={"data-testid": testid}))


def _get_meta_content(soup: BeautifulSoup, **attrs: Any) -> str | None:
    attrs_dict: dict[str, Any] = dict(attrs)
    tag = soup.find("meta", attrs=attrs_dict)
    return _get_attr(tag, "content")


def _parse_score_int(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("tbd", "na", "n/a", "--", ""):
        return None
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _parse_score_float(val: str | None) -> float | None:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("tbd", "na", "n/a", "--", ""):
        return None
    try:
        return round(float(cleaned), 1)
    except (ValueError, TypeError):
        return None


SLUG_ALIASES: dict[str, str] = {
    "ps5": "playstation-5",
    "ps4": "playstation-4",
    "ps3": "playstation-3",
    "ps2": "playstation-2",
    "ps1": "playstation",
    "playstation-5": "playstation-5",
    "playstation-4": "playstation-4",
    "playstation-3": "playstation-3",
    "playstation-2": "playstation-2",
    "playstation": "playstation",
    "xbox-series-x": "xbox-series-x",
    "xbox-series-s": "xbox-series-s",
    "xbox-one": "xbox-one",
    "xbox-360": "xbox-360",
    "xbox": "xbox",
    "switch": "nintendo-switch",
    "nintendo-switch": "nintendo-switch",
    "switch-2": "nintendo-switch-2",
    "nintendo-switch-2": "nintendo-switch-2",
    "pc": "pc",
    "ios": "ios",
    "android": "android",
}

PLATFORM_CANONICAL_NAMES: dict[str, str] = {
    "pc": "PC",
    "playstation-5": "PlayStation 5",
    "playstation-4": "PlayStation 4",
    "playstation-3": "PlayStation 3",
    "playstation-2": "PlayStation 2",
    "playstation": "PlayStation",
    "xbox-series-x": "Xbox Series X",
    "xbox-series-s": "Xbox Series S",
    "xbox-one": "Xbox One",
    "xbox-360": "Xbox 360",
    "xbox": "Xbox",
    "nintendo-switch": "Nintendo Switch",
    "nintendo-switch-2": "Nintendo Switch 2",
    "wii-u": "Wii U",
    "wii": "Wii",
    "gamecube": "GameCube",
    "nintendo-64": "Nintendo 64",
    "3ds": "Nintendo 3DS",
    "ds": "Nintendo DS",
    "ios": "iOS",
    "android": "Android",
}

NAVIGATION_CATEGORY_PATTERN = re.compile(
    r"^(new|best|upcoming|top|all|popular|recent|latest)\s+.*games?|"
    r"^games\s+(on|for|by|in)\s+.*|"
    r"^based\s+on\s+.*|"
    r"^browse\b|"
    r"^view\s+all\b|"
    r"^see\s+all\b|"
    r"^read\s+all\b",
    re.IGNORECASE,
)


def is_navigation_or_category_label(text: str | None) -> bool:
    """Defensively detect navigation, category, review count, or browse labels."""
    if not text:
        return True
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    return bool(NAVIGATION_CATEGORY_PATTERN.search(cleaned))


def normalize_platform_slug(slug: str) -> str:
    """Normalize a platform slug to its canonical form."""
    cleaned = re.sub(r"[^a-zA-Z0-9\-]", "", slug.strip().lower().replace(" ", "-").replace("_", "-"))
    return SLUG_ALIASES.get(cleaned, cleaned)


def normalize_platform_name(name: str, slug: str | None = None) -> str:
    """
    Normalize platform name to canonical form.
    If slug is provided, uses canonical mapping for that slug.
    If name matches a known alias or formatted string, normalizes it.
    """
    if slug:
        norm_slug = normalize_platform_slug(slug)
        if norm_slug in PLATFORM_CANONICAL_NAMES:
            return PLATFORM_CANONICAL_NAMES[norm_slug]

    clean_name = _clean_text(name) or ""
    slug_cand = normalize_platform_slug(clean_name.lower().replace(" ", "-"))
    if slug_cand in PLATFORM_CANONICAL_NAMES:
        return PLATFORM_CANONICAL_NAMES[slug_cand]

    return clean_name.title() if clean_name else "Unknown"


def _platform_slug_to_name(slug: str) -> str:
    """Format platform slug to a clean human-readable name."""
    return normalize_platform_name(slug, slug=slug)


class MetacriticParser:
    """
    Pure parser functions for extracting domain DTOs from raw HTML.
    Independent of HTTP transport and database layers.
    """

    @staticmethod
    def parse_new_releases(html: str) -> list[GameCandidate]:
        """Extract game candidates from New Releases section."""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[GameCandidate] = []
        seen_ids: set[str] = set()

        # Primary: find product cards (data-testid="product-card")
        cards = _find_all_by_testid(soup, "product-card")
        if not cards:
            # Fallback: search for product cards by class or section
            cards = list(soup.find_all(class_=re.compile(r"c-productCard|productCard", re.I)))

        for card in cards:
            link = card.find("a", href=re.compile(r"^/game/"))
            href = _get_attr(link, "href")
            if not href:
                continue

            slug = extract_canonical_slug(href)
            if not slug or slug in seen_ids:
                continue

            # Title
            title_elem = _find_by_testid(card, "product-card-title") or card.find(
                re.compile(r"^h[1-6]$")
            )
            title = _clean_text(title_elem.get_text() if title_elem else "") or slug.replace("-", " ").title()

            seen_ids.add(slug)
            candidates.append(
                GameCandidate(
                    title=title,
                    url=normalize_canonical_url(href),
                    external_id=slug,
                )
            )

        # If no cards found via testids, search links in new releases section
        if not candidates:
            for a in soup.find_all("a", href=re.compile(r"^/game/[^/?#]+/?$")):
                href = _get_attr(a, "href")
                if not href:
                    continue
                slug = extract_canonical_slug(href)
                link_title = _clean_text(a.get_text())
                if slug and link_title and slug not in seen_ids and not any(k in href for k in ["critic-reviews", "user-reviews"]):
                    seen_ids.add(slug)
                    candidates.append(
                        GameCandidate(
                            title=link_title,
                            url=normalize_canonical_url(href),
                            external_id=slug,
                        )
                    )

        return candidates

    @staticmethod
    def parse_browse_page(html: str, page: int = 1) -> BrowsePage:
        """Extract game candidates and pagination state from Browse page."""
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[GameCandidate] = []
        seen_ids: set[str] = set()

        # Primary: cards with data-testid="filter-results"
        cards = _find_all_by_testid(soup, "filter-results")
        if not cards:
            cards = list(soup.find_all(class_=re.compile(r"c-finderProductCard", re.I)))

        for card in cards:
            link = card.find("a", href=re.compile(r"^/game/"))
            href = _get_attr(link, "href")
            if not href:
                continue

            slug = extract_canonical_slug(href)
            if not slug or slug in seen_ids:
                continue

            # Title: data-testid="product-title" or data-title attribute or h3
            title_elem = _find_by_testid(card, "product-title") or card.find(
                re.compile(r"^h[1-6]$")
            )
            card_title_attr = _get_attr(card, "data-title")
            title = (
                _clean_text(card_title_attr)
                or _clean_text(title_elem.get_text() if title_elem else "")
                or slug.replace("-", " ").title()
            )

            # Date
            date_elem = card.find(class_=re.compile(r"release-date", re.I))
            release_date = _clean_text(date_elem.get_text() if date_elem else None)

            seen_ids.add(slug)
            candidates.append(
                GameCandidate(
                    title=title,
                    url=normalize_canonical_url(href),
                    external_id=slug,
                    release_date=release_date,
                )
            )

        # Pagination detection
        next_arrow = _find_by_testid(soup, "pagination-arrow-next")
        has_next = False
        if next_arrow is not None:
            disabled_attr = _get_attr(next_arrow, "disabled")
            class_attr = _get_attr(next_arrow, "class") or ""
            has_next = not bool(disabled_attr) and "disabled" not in class_attr

        # Total pages extraction if visible
        total_pages = None
        for page_span in soup.find_all(class_=re.compile(r"c-navigation-pagination__page|pagination__item")):
            content = _clean_text(page_span.get_text())
            if content and content.isdigit():
                num = int(content)
                if total_pages is None or num > total_pages:
                    total_pages = num

        return BrowsePage(
            candidates=candidates,
            page=page,
            has_next=has_next or (len(candidates) > 0 and (total_pages is None or page < total_pages)),
            total_pages=total_pages,
        )

    @staticmethod
    def parse_game_details(html: str, canonical_url: str) -> GameDetails:
        """Extract full game details, media, developer, and platform scores."""
        soup = BeautifulSoup(html, "html.parser")
        slug = extract_canonical_slug(canonical_url)
        normalized_url = normalize_canonical_url(canonical_url)

        # 1. Parse JSON-LD Schema.org metadata if present
        ld_data: dict = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "VideoGame":
                    ld_data = data
                    break
            except Exception:
                continue

        # 2. Title
        hero_title_elem = _find_by_testid(soup, "hero-title")
        title = (
            _clean_text(ld_data.get("name"))
            or _clean_text(hero_title_elem.get_text() if hero_title_elem else None)
            or _clean_text(_get_meta_content(soup, property="og:title"))
            or slug.replace("-", " ").title()
        )

        # 3. Developer
        developer = None
        dev_container = _find_by_testid(soup, "hero-summary-developer")
        if dev_container:
            dev_link = dev_container.find("a")
            if dev_link:
                developer = _clean_text(dev_link.get_text())
            else:
                developer = _clean_text(dev_container.get_text().replace("Developer:", ""))
        elif "author" in ld_data and isinstance(ld_data["author"], dict):
            developer = _clean_text(ld_data["author"].get("name"))

        # 4. Description
        description = (
            _clean_text(ld_data.get("description"))
            or _clean_text(_get_meta_content(soup, property="og:description"))
            or _clean_text(_get_meta_content(soup, name="description"))
        )

        # 5. Cover URL
        cover_url = (
            _clean_text(ld_data.get("image"))
            or _clean_text(_get_meta_content(soup, property="og:image"))
        )

        # 6. Trailer URL
        trailer_url = None
        trailer_container = _find_by_testid(soup, "featured-trailer")
        if trailer_container:
            iframe = trailer_container.find("iframe")
            video = trailer_container.find("video")
            if iframe and _get_attr(iframe, "src"):
                trailer_url = _get_attr(iframe, "src")
            elif video and _get_attr(video, "src"):
                trailer_url = _get_attr(video, "src")

        # 7. Platforms & Scores
        platforms_dict: dict[str, PlatformScore] = {}

        # Primary platform in hero
        primary_platform_name = "PC"
        primary_platform_slug = "pc"
        selector_elem = _find_by_testid(soup, "platform-selector")
        if selector_elem:
            label_span = selector_elem.find("span", title=True)
            if label_span:
                span_title = _get_attr(label_span, "title")
                if span_title:
                    primary_platform_name = span_title.strip()
                    primary_platform_slug = span_title.lower().replace(" ", "-")

        # Extract Metascore & User score from hero score cards
        metascore = None
        userscore = None
        score_cards = _find_all_by_testid(soup, "product-score")
        for card in score_cards:
            header = _find_by_testid(card, "global-score-header")
            value_elem = _find_by_testid(card, "global-score-value")
            if not header or not value_elem:
                continue
            header_text = header.get_text().strip().lower()
            val_text = value_elem.get_text().strip()
            if "metascore" in header_text:
                metascore = _parse_score_int(val_text)
            elif "user" in header_text:
                userscore = _parse_score_float(val_text)

        platforms_dict[primary_platform_slug] = PlatformScore(
            platform_name=primary_platform_name,
            platform_slug=primary_platform_slug,
            metascore=metascore,
            userscore=userscore,
        )

        # Discover additional platforms strictly within game platform containers
        platform_containers = []
        if selector_elem:
            platform_containers.append(selector_elem)
        all_platforms_elem = _find_by_testid(soup, "all-platforms")
        if all_platforms_elem:
            platform_containers.append(all_platforms_elem)
        for class_pat in ("c-gameDetails_Platforms", "c-gamePlatforms", "game-platforms"):
            for elem in soup.find_all(class_=re.compile(class_pat, re.I)):
                if elem not in platform_containers:
                    platform_containers.append(elem)

        for container in platform_containers:
            for a in container.find_all("a", href=re.compile(r"platform=([a-zA-Z0-9\-]+)")):
                href = _get_attr(a, "href") or ""
                if "/browse/" in href or "/search/" in href:
                    continue
                match = re.search(r"platform=([a-zA-Z0-9\-]+)", href)
                if not match:
                    continue
                raw_slug = match.group(1).lower()
                p_slug = normalize_platform_slug(raw_slug)

                link_text = _clean_text(a.get_text())
                if link_text and not is_navigation_or_category_label(link_text):
                    p_name = normalize_platform_name(link_text, slug=p_slug)
                else:
                    p_name = normalize_platform_name(p_slug, slug=p_slug)

                if p_slug not in platforms_dict:
                    platforms_dict[p_slug] = PlatformScore(
                        platform_name=p_name,
                        platform_slug=p_slug,
                        metascore=None,
                        userscore=None,
                    )

        return GameDetails(
            external_id=slug,
            metacritic_url=normalized_url,
            metacritic_slug=slug,
            title=title,
            cover_url=cover_url,
            developer=developer,
            description=description,
            trailer_url=trailer_url,
            platforms=list(platforms_dict.values()),
        )

    @staticmethod
    def _parse_reviews_page(
        html: str,
        game_slug: str,
        review_type: str,  # "critic" or "user"
        page: int = 1,
    ) -> ReviewPage:
        from app.services.ai.sampling import classify_sentiment

        soup = BeautifulSoup(html, "html.parser")
        cards = _find_all_by_testid(soup, "review-card")
        if not cards:
            cards = list(soup.find_all(class_=re.compile(r"c-siteReview|c-reviewCard", re.I)))

        reviews: list[ReviewItem] = []
        for card in cards:
            # 1. Date
            date_elem = _find_by_testid(card, "review-card-date") or card.find(class_=re.compile(r"c-siteReviewHeader_publicationDate|date", re.I))
            published_at = _clean_text(date_elem.get_text()) if date_elem else None

            # 2. Header / Author / Score
            header_elem = _find_by_testid(card, "review-card-header") or card.find(class_=re.compile(r"c-siteReviewHeader", re.I))

            score: float | None = None
            score_elem = card.find(class_=re.compile(r"c-siteReviewScore")) or card.find(attrs={"aria-label": re.compile(r"score", re.I)})
            if score_elem:
                aria_lbl = _get_attr(score_elem, "aria-label") or ""
                match_aria = re.search(r"(\d+(?:\.\d+)?)\s+out\s+of", aria_lbl)
                if match_aria:
                    try:
                        score = float(match_aria.group(1))
                    except ValueError:
                        score = None
                else:
                    span_score = score_elem.find("span")
                    score_val = span_score.get_text().strip() if span_score else score_elem.get_text().strip()
                    score = _parse_score_float(score_val)

            # Author name (strip score text from header if present)
            author: str | None = None
            if header_elem:
                h_clone = BeautifulSoup(str(header_elem), "html.parser")
                for s_badge in h_clone.find_all(class_=re.compile(r"c-siteReviewScore")):
                    s_badge.decompose()
                author = _clean_text(h_clone.get_text())

            # 3. Body
            quote_elem = (
                _find_by_testid(card, "review-quote-text")
                or _find_by_testid(card, "review-card-quote-block")
                or card.find(class_=re.compile(r"c-siteReview_quote|quote", re.I))
            )
            body = ""
            if quote_elem:
                q_clone = BeautifulSoup(str(quote_elem), "html.parser")
                for rm in _find_all_by_testid(q_clone, "review-quote-read-more"):
                    rm.decompose()
                for rm in q_clone.find_all(class_=re.compile(r"read-more", re.I)):
                    rm.decompose()
                body = _clean_text(q_clone.get_text()) or ""


            # 4. Platform
            platform_elem = _find_by_testid(card, "review-platform") or card.find(class_=re.compile(r"platform", re.I))
            platform_name = _clean_text(platform_elem.get_text()) if platform_elem else None
            platform_slug = platform_name.lower().replace(" ", "-") if platform_name else None

            # 5. Full review link (critic)
            source_url = None
            if review_type == "critic":
                full_link_elem = _find_by_testid(card, "review-full-review-link") or card.find("a", href=re.compile(r"^https?://"))
                if full_link_elem:
                    source_url = _get_attr(full_link_elem, "href")

            # 6. Sentiment category
            sentiment = classify_sentiment(score, review_type)

            # 7. Content hash and external id
            raw_hash_input = f"{game_slug}:{review_type}:{platform_slug or ''}:{author or ''}:{published_at or ''}:{body}"
            content_hash = hashlib.sha256(raw_hash_input.encode("utf-8")).hexdigest()
            external_id = f"{review_type}-{content_hash[:16]}"

            reviews.append(
                ReviewItem(
                    external_id=external_id,
                    review_type=review_type,
                    author=author,
                    score=score,
                    body=body,
                    published_at=published_at,
                    platform_slug=platform_slug,
                    source_url=source_url,
                    sentiment_category=sentiment,
                    content_hash=content_hash,
                )
            )

        # 8. Pagination detection
        next_elem = (
            _find_by_testid(soup, "pagination-next")
            or soup.find(class_=re.compile(r"pagination.*next", re.I))
            or soup.find("a", href=re.compile(rf"[?&]page={page + 1}"))
        )
        has_next_page = bool(next_elem)

        total_pages = None
        pag_links = soup.find_all("a", href=re.compile(r"[?&]page=(\d+)"))
        if pag_links:
            page_nums: list[int] = []
            for pl in pag_links:
                m = re.search(r"[?&]page=(\d+)", _get_attr(pl, "href") or "")
                if m:
                    try:
                        page_nums.append(int(m.group(1)))
                    except ValueError:
                        pass
            if page_nums:
                total_pages = max(page_nums)

        return ReviewPage(
            reviews=reviews,
            current_page=page,
            has_next_page=has_next_page,
            total_pages=total_pages,
        )

    @staticmethod
    def parse_critic_reviews(html: str, game_slug: str, page: int = 1) -> ReviewPage:
        return MetacriticParser._parse_reviews_page(html, game_slug=game_slug, review_type="critic", page=page)

    @staticmethod
    def parse_user_reviews(html: str, game_slug: str, page: int = 1) -> ReviewPage:
        return MetacriticParser._parse_reviews_page(html, game_slug=game_slug, review_type="user", page=page)


