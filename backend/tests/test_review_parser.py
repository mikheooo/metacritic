from pathlib import Path

from app.services.crawler.parser import MetacriticParser

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "metacritic"


def test_parse_critic_reviews_single_page():
    html = (FIXTURES_DIR / "critic_reviews_single_page.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_critic_reviews(html, game_slug="elden-ring", page=1)

    assert result.current_page == 1
    assert result.has_next_page is False
    assert len(result.reviews) == 4

    r1 = result.reviews[0]
    assert r1.review_type == "critic"
    assert r1.author == "Areajugones"
    assert r1.score == 100.0
    assert r1.sentiment_category == "positive"
    assert "masterpiece of open world design" in r1.body
    assert r1.platform_slug == "playstation-5"
    assert r1.source_url == "https://example.com/reviews/elden-ring-1"
    assert r1.published_at == "Feb 23, 2022"
    assert r1.content_hash != ""
    assert r1.external_id.startswith("critic-")

    # Check mixed review
    r3 = result.reviews[2]
    assert r3.author == "Eurogamer Italy"
    assert r3.score == 65.0
    assert r3.sentiment_category == "mixed"

    # Check negative review
    r4 = result.reviews[3]
    assert r4.author == "Slanted Magazine"
    assert r4.score == 40.0
    assert r4.sentiment_category == "negative"


def test_parse_critic_reviews_paginated():
    html = (FIXTURES_DIR / "critic_reviews_paginated.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_critic_reviews(html, game_slug="elden-ring", page=1)

    assert result.current_page == 1
    assert result.has_next_page is True
    assert result.total_pages == 3
    assert len(result.reviews) == 2


def test_parse_critic_reviews_multi_platform():
    html = (FIXTURES_DIR / "critic_reviews_multi_platform.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_critic_reviews(html, game_slug="elden-ring", page=1)

    assert len(result.reviews) == 3
    platforms = {r.platform_slug for r in result.reviews}
    assert platforms == {"playstation-5", "pc", "xbox-series-x"}


def test_parse_user_reviews_single_page():
    html = (FIXTURES_DIR / "user_reviews_single_page.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_user_reviews(html, game_slug="elden-ring", page=1)

    assert result.current_page == 1
    assert result.has_next_page is False
    assert len(result.reviews) == 4

    u1 = result.reviews[0]
    assert u1.review_type == "user"
    assert u1.author == "tarnished_one"
    assert u1.score == 10.0
    assert u1.sentiment_category == "positive"
    assert "Absolute masterpiece" in u1.body

    u2 = result.reviews[1]
    assert u2.author == "ivantret04"
    assert u2.score == 8.0
    assert u2.sentiment_category == "positive"

    u3 = result.reviews[2]
    assert u3.author == "casual_gamer99"
    assert u3.score == 6.0
    assert u3.sentiment_category == "mixed"

    u4 = result.reviews[3]
    assert u4.author == "ragequitter"
    assert u4.score == 2.0
    assert u4.sentiment_category == "negative"


def test_parse_user_reviews_paginated():
    html = (FIXTURES_DIR / "user_reviews_paginated.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_user_reviews(html, game_slug="elden-ring", page=1)

    assert result.current_page == 1
    assert result.has_next_page is True
    assert len(result.reviews) == 2


def test_parse_user_reviews_multi_platform():
    html = (FIXTURES_DIR / "user_reviews_multi_platform.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_user_reviews(html, game_slug="elden-ring", page=1)

    assert len(result.reviews) == 3
    platforms = {r.platform_slug for r in result.reviews}
    assert platforms == {"pc", "xbox-series-x", "playstation-5"}


def test_parse_reviews_empty():
    html = (FIXTURES_DIR / "reviews_empty.html").read_text(encoding="utf-8")
    critic_result = MetacriticParser.parse_critic_reviews(html, game_slug="indie-game", page=1)
    assert len(critic_result.reviews) == 0
    assert critic_result.has_next_page is False

    user_result = MetacriticParser.parse_user_reviews(html, game_slug="indie-game", page=1)
    assert len(user_result.reviews) == 0
    assert user_result.has_next_page is False


def test_parse_review_spoiler():
    html = (FIXTURES_DIR / "review_spoiler.html").read_text(encoding="utf-8")
    result = MetacriticParser.parse_user_reviews(html, game_slug="elden-ring", page=1)

    assert len(result.reviews) == 1
    r = result.reviews[0]
    assert "Radagon being Marika" in r.body
    # "Read More" button text should be stripped
    assert "Read More" not in r.body


def test_parse_review_missing_score():
    html = (FIXTURES_DIR / "review_missing_score.html").read_text(encoding="utf-8")
    result_critic = MetacriticParser.parse_critic_reviews(html, game_slug="elden-ring", page=1)
    assert len(result_critic.reviews) == 2

    # First is critic with 'tbd'
    r1 = result_critic.reviews[0]
    assert r1.score is None
    assert r1.sentiment_category == "mixed"
    assert "Review in progress" in r1.body

    # Second is user with '--'
    r2 = result_critic.reviews[1]
    assert r2.score is None
    assert r2.sentiment_category == "mixed"
