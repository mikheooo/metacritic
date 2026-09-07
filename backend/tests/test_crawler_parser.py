from pathlib import Path

from app.services.crawler.dtos import (
    extract_canonical_slug,
    normalize_canonical_url,
)
from app.services.crawler.parser import MetacriticParser

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "metacritic"


def load_fixture(filename: str) -> str:
    path = FIXTURES_DIR / filename
    return path.read_text(encoding="utf-8")


def test_canonical_url_normalization() -> None:
    """Verify normalization of various URL formats into canonical URL and slug."""
    url1 = "https://www.metacritic.com/game/elden-ring/"
    url2 = "https://www.metacritic.com/game/elden-ring?platform=ps5#reviews"
    url3 = "/game/elden-ring"
    url4 = "elden-ring"

    assert normalize_canonical_url(url1) == "https://www.metacritic.com/game/elden-ring/"
    assert normalize_canonical_url(url2) == "https://www.metacritic.com/game/elden-ring/"
    assert normalize_canonical_url(url3) == "https://www.metacritic.com/game/elden-ring/"
    assert normalize_canonical_url(url4) == "https://www.metacritic.com/game/elden-ring/"

    assert extract_canonical_slug(url1) == "elden-ring"
    assert extract_canonical_slug(url2) == "elden-ring"
    assert extract_canonical_slug(url3) == "elden-ring"
    assert extract_canonical_slug(url4) == "elden-ring"


def test_parse_new_releases_fixture() -> None:
    """Verify candidate extraction from new_releases.html fixture."""
    html = load_fixture("new_releases.html")
    candidates = MetacriticParser.parse_new_releases(html)

    assert len(candidates) == 5
    slugs = [c.external_id for c in candidates]
    assert "nba-2k27" in slugs
    assert "onimusha-way-of-the-sword" in slugs
    assert "orbitals" in slugs
    assert "the-blood-of-dawnwalker" in slugs
    assert "bioeden" in slugs

    # Check first candidate fields
    c0 = candidates[0]
    assert c0.title == "NBA 2K27"
    assert c0.url == "https://www.metacritic.com/game/nba-2k27/"
    assert c0.external_id == "nba-2k27"


def test_parse_browse_page_1_fixture() -> None:
    """Verify candidate and pagination extraction from browse_page_1.html fixture."""
    html = load_fixture("browse_page_1.html")
    page_data = MetacriticParser.parse_browse_page(html, page=1)

    assert len(page_data.candidates) == 5
    assert page_data.page == 1
    assert page_data.has_next is True
    assert page_data.total_pages == 7415

    slugs = [c.external_id for c in page_data.candidates]
    assert slugs == [
        "tiny-eden",
        "dataminers",
        "port-of-jumanah",
        "curse-of-pirates",
        "glow-in-the-shadows",
    ]
    assert page_data.candidates[0].title == "Tiny Eden"
    assert page_data.candidates[0].release_date == "Sep 7, 2026"


def test_parse_browse_page_2_fixture() -> None:
    """Verify candidate extraction from browse_page_2.html fixture."""
    html = load_fixture("browse_page_2.html")
    page_data = MetacriticParser.parse_browse_page(html, page=2)

    assert len(page_data.candidates) == 5
    assert page_data.page == 2
    assert page_data.has_next is True
    slugs = [c.external_id for c in page_data.candidates]
    assert "nothing-strange-here" in slugs
    assert "exit-ways" in slugs
    assert "soul-chained" in slugs
    assert "the-ayna" in slugs
    assert "the-well-is-not-empty" in slugs


def test_parse_game_multi_platform_fixture() -> None:
    """Verify multi-platform parsing, scores, developer, media, and description."""
    html = load_fixture("game_multi_platform.html")
    details = MetacriticParser.parse_game_details(html, "https://www.metacritic.com/game/elden-ring/")

    assert details.title == "Elden Ring"
    assert details.external_id == "elden-ring"
    assert details.metacritic_slug == "elden-ring"
    assert details.metacritic_url == "https://www.metacritic.com/game/elden-ring/"
    assert details.developer == "FromSoftware"
    assert "Hidetaka Miyazaki" in (details.description or "")
    assert details.cover_url == "https://www.metacritic.com/a/img/eldenring.jpg"
    assert "youtube.com/embed/E3Huy2cdih0" in (details.trailer_url or "")

    # Platforms check
    p_slugs = {p.platform_slug for p in details.platforms}
    assert "playstation-5" in p_slugs
    assert "pc" in p_slugs
    assert "xbox-series-x" in p_slugs
    assert "playstation-4" in p_slugs

    # PlayStation 5 scores
    ps5_p = next(p for p in details.platforms if p.platform_slug == "playstation-5")
    assert ps5_p.metascore == 96
    assert ps5_p.userscore == 7.8


def test_parse_game_single_platform_fixture() -> None:
    """Verify single-platform parsing and attributes."""
    html = load_fixture("game_single_platform.html")
    details = MetacriticParser.parse_game_details(
        html, "https://www.metacritic.com/game/total-war-warhammer-iii/"
    )

    assert details.title == "Total War: Warhammer III"
    assert details.developer == "Creative Assembly"
    assert details.cover_url == "https://www.metacritic.com/a/img/warhammer3.jpg"
    assert "WARHAMMER" in (details.description or "")
    assert len(details.platforms) == 1
    assert details.platforms[0].platform_slug == "pc"
    assert details.platforms[0].metascore == 85
    assert details.platforms[0].userscore == 8.2


def test_parse_game_missing_scores_fixture() -> None:
    """Verify resilient parsing when metascore, userscore, developer, or trailer are missing."""
    html = load_fixture("game_missing_scores.html")
    details = MetacriticParser.parse_game_details(
        html, "https://www.metacritic.com/game/indie-mystery-game/"
    )

    assert details.title == "Indie Mystery Game"
    assert details.external_id == "indie-mystery-game"
    assert details.developer is None
    assert details.trailer_url is None
    assert len(details.platforms) == 1
    assert details.platforms[0].platform_slug == "pc"
    assert details.platforms[0].metascore is None
    assert details.platforms[0].userscore is None
