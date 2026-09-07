import random

from app.services.ai.sampling import (
    classify_sentiment,
    compute_input_fingerprint,
    select_reviews_for_summary,
)
from app.services.crawler.dtos import ReviewForSummary


def test_classify_sentiment_critic():
    assert classify_sentiment(100, "critic") == "positive"
    assert classify_sentiment(75, "critic") == "positive"
    assert classify_sentiment(74.9, "critic") == "mixed"
    assert classify_sentiment(50, "critic") == "mixed"
    assert classify_sentiment(49.9, "critic") == "negative"
    assert classify_sentiment(0, "critic") == "negative"
    assert classify_sentiment(None, "critic") == "mixed"


def test_classify_sentiment_user():
    assert classify_sentiment(10.0, "user") == "positive"
    assert classify_sentiment(8.0, "user") == "positive"
    assert classify_sentiment(7.9, "user") == "mixed"
    assert classify_sentiment(5.0, "user") == "mixed"
    assert classify_sentiment(4.9, "user") == "negative"
    assert classify_sentiment(0.0, "user") == "negative"
    assert classify_sentiment(None, "user") == "mixed"


def _make_review(
    id_num: int,
    review_type: str = "critic",
    score: float = 80.0,
    platform: str = "pc",
    body: str | None = None,
) -> ReviewForSummary:
    sentiment = classify_sentiment(score, review_type)
    content = body or f"Review body {id_num} for test"
    return ReviewForSummary(
        external_id=f"{review_type}-{id_num}",
        review_type=review_type,
        author=f"Author {id_num}",
        score=score,
        body=content,
        platform_slug=platform,
        sentiment_category=sentiment,
        content_hash=f"hash_{id_num:04d}",
    )


def test_select_reviews_empty():
    assert select_reviews_for_summary([]) == []


def test_select_reviews_under_limit():
    reviews = [_make_review(i, score=85.0) for i in range(5)]
    selected = select_reviews_for_summary(reviews, max_count=20)
    assert len(selected) == 5


def test_select_reviews_deterministic_and_balanced():
    # Create 30 reviews: 10 positive, 10 mixed, 10 negative across 2 platforms
    reviews = []
    for i in range(10):
        reviews.append(_make_review(i, score=90.0, platform="pc" if i % 2 == 0 else "ps5"))
    for i in range(10, 20):
        reviews.append(_make_review(i, score=60.0, platform="pc" if i % 2 == 0 else "ps5"))
    for i in range(20, 30):
        reviews.append(_make_review(i, score=30.0, platform="pc" if i % 2 == 0 else "ps5"))

    # Request max_count = 15
    selected_1 = select_reviews_for_summary(reviews, max_count=15)
    assert len(selected_1) == 15

    # Should contain representation from positive, mixed, and negative
    cats = {r.sentiment_category for r in selected_1}
    assert cats == {"positive", "mixed", "negative"}

    # Counts per sentiment should be balanced (5 each)
    pos = [r for r in selected_1 if r.sentiment_category == "positive"]
    mix = [r for r in selected_1 if r.sentiment_category == "mixed"]
    neg = [r for r in selected_1 if r.sentiment_category == "negative"]
    assert len(pos) == 5
    assert len(mix) == 5
    assert len(neg) == 5

    # Shuffled runs must yield exact same result
    shuffled = list(reviews)
    for _ in range(5):
        random.shuffle(shuffled)
        selected_shuffled = select_reviews_for_summary(shuffled, max_count=15)
        assert [r.external_id for r in selected_shuffled] == [r.external_id for r in selected_1]


def test_select_reviews_platform_diversity():
    # 10 positive reviews: 8 from PS5, 2 from PC
    reviews = []
    for i in range(8):
        reviews.append(_make_review(i, score=90.0, platform="ps5"))
    for i in range(8, 10):
        reviews.append(_make_review(i, score=90.0, platform="pc"))

    selected = select_reviews_for_summary(reviews, max_count=4)
    assert len(selected) == 4
    platforms = [r.platform_slug for r in selected]
    # Interleaving ensures PC is included despite PS5 being the majority
    assert "pc" in platforms
    assert "ps5" in platforms


def test_compute_input_fingerprint_deterministic():
    r1 = _make_review(1, score=90.0)
    r2 = _make_review(2, score=50.0)

    fp1 = compute_input_fingerprint([r1, r2], prompt_version="v1", model="gpt-4o-mini")
    fp2 = compute_input_fingerprint([r2, r1], prompt_version="v1", model="gpt-4o-mini")
    # Order of inputs should not change fingerprint
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256


def test_compute_input_fingerprint_sensitive():
    r1 = _make_review(1, score=90.0)
    r2 = _make_review(2, score=50.0)

    fp_base = compute_input_fingerprint([r1, r2], prompt_version="v1", model="gpt-4o-mini")

    # Change prompt version
    fp_v2 = compute_input_fingerprint([r1, r2], prompt_version="v2", model="gpt-4o-mini")
    assert fp_base != fp_v2

    # Change model
    fp_model = compute_input_fingerprint([r1, r2], prompt_version="v1", model="gpt-4o")
    assert fp_base != fp_model

    # Change provider (fake vs openai vs openrouter must produce distinct fingerprints)
    fp_fake = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", provider="fake"
    )
    fp_openai = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", provider="openai"
    )
    fp_openrouter = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", provider="openrouter"
    )
    assert fp_fake != fp_openai
    assert fp_openai != fp_openrouter
    assert fp_fake != fp_openrouter


    # Change review type
    fp_critic = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", review_type="critic"
    )
    fp_user = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", review_type="user"
    )
    assert fp_critic != fp_user

    # Change language
    fp_ru = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", language="ru"
    )
    fp_en = compute_input_fingerprint(
        [r1, r2], prompt_version="v1", model="gpt-4o-mini", language="en"
    )
    assert fp_ru != fp_en

    # Change review score
    r2_changed = _make_review(2, score=55.0)
    fp_score = compute_input_fingerprint([r1, r2_changed], prompt_version="v1", model="gpt-4o-mini")
    assert fp_base != fp_score

