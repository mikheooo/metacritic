import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence

from app.services.crawler.dtos import ReviewForSummary, ReviewItem


def classify_sentiment(score: float | None, review_type: str) -> str:
    """
    Classify a review score into 'positive', 'mixed', or 'negative'.
    Missing scores default to 'mixed'.

    Critic scale (0-100):
      >= 75: positive
      50-74: mixed
      < 50: negative

    User scale (0-10):
      >= 8.0: positive
      5.0-7.9: mixed
      < 5.0: negative
    """
    if score is None:
        return "mixed"

    if review_type.lower() == "critic":
        if score >= 75:
            return "positive"
        elif score >= 50:
            return "mixed"
        else:
            return "negative"
    else:  # user
        if score >= 8.0:
            return "positive"
        elif score >= 5.0:
            return "mixed"
        else:
            return "negative"



def _to_summary_review(item: ReviewItem | ReviewForSummary) -> ReviewForSummary:
    if isinstance(item, ReviewForSummary):
        return item
    return ReviewForSummary(
        external_id=item.external_id,
        review_type=item.review_type,
        author=item.author,
        score=item.score,
        body=item.body,
        platform_slug=item.platform_slug,
        sentiment_category=item.sentiment_category,
        content_hash=item.content_hash,
    )


def select_reviews_for_summary(
    reviews: Sequence[ReviewItem | ReviewForSummary],
    max_count: int = 20,
) -> list[ReviewForSummary]:
    """
    Deterministically select a balanced subset of reviews for LLM summarization.
    Guarantees:
    1. Determinism: Same input always produces exact same output.
    2. Sentiment balance: Allocates quota across positive, mixed, negative.
    3. Platform diversity: Interleaves platforms within sentiment buckets.
    4. Bounded size: Never exceeds max_count.
    5. No empty/duplicate reviews.
    """
    if not reviews:
        return []

    # Convert all to ReviewForSummary, deduplicate by external_id
    seen_ids: set[str] = set()
    cleaned_reviews: list[ReviewForSummary] = []
    for r in reviews:
        cand_rev = _to_summary_review(r)
        if not cand_rev.body or not cand_rev.body.strip():
            continue
        if cand_rev.external_id in seen_ids:
            continue
        seen_ids.add(cand_rev.external_id)
        cleaned_reviews.append(cand_rev)


    if len(cleaned_reviews) <= max_count:
        # If total reviews are within limit, return all sorted deterministically
        return sorted(cleaned_reviews, key=lambda r: (r.sentiment_category, r.content_hash, r.external_id))

    # Partition into sentiment buckets
    buckets: dict[str, list[ReviewForSummary]] = {
        "positive": [],
        "mixed": [],
        "negative": [],
    }
    for r in cleaned_reviews:
        cat = r.sentiment_category if r.sentiment_category in buckets else classify_sentiment(r.score, r.review_type)
        buckets[cat].append(r)

    # Within each bucket, group by platform to encourage platform diversity,
    # then interleave deterministically.
    sorted_buckets: dict[str, list[ReviewForSummary]] = {}
    for cat, items in buckets.items():
        by_platform: dict[str, list[ReviewForSummary]] = defaultdict(list)
        for it in items:
            p_key = it.platform_slug or "unknown"
            by_platform[p_key].append(it)

        # Sort within each platform by content_hash for determinism
        for p_key in by_platform:
            by_platform[p_key].sort(key=lambda x: (x.content_hash, x.external_id))

        # Interleave across platforms deterministically (platforms sorted alphabetically)
        platform_keys = sorted(by_platform.keys())
        interleaved: list[ReviewForSummary] = []
        idx = 0
        has_more = True
        while has_more:
            has_more = False
            for p in platform_keys:
                if idx < len(by_platform[p]):
                    interleaved.append(by_platform[p][idx])
                    has_more = True
            idx += 1
        sorted_buckets[cat] = interleaved

    # Calculate target quota per non-empty bucket
    active_cats = [c for c in ["positive", "mixed", "negative"] if sorted_buckets[c]]
    if not active_cats:
        return []

    # Round-robin allocation among active sentiment buckets until max_count is filled
    selected: list[ReviewForSummary] = []
    selected_set: set[str] = set()

    bucket_ptrs = dict.fromkeys(active_cats, 0)
    while len(selected) < max_count:
        progress = False
        for cat_name in active_cats:
            if len(selected) >= max_count:
                break
            ptr = bucket_ptrs[cat_name]
            bucket_list = sorted_buckets[cat_name]
            if ptr < len(bucket_list):
                cand = bucket_list[ptr]
                bucket_ptrs[cat_name] += 1
                if cand.external_id not in selected_set:
                    selected.append(cand)
                    selected_set.add(cand.external_id)
                    progress = True
        if not progress:
            break


    # Return selected sorted deterministically by sentiment and external_id
    return sorted(selected, key=lambda r: (r.sentiment_category, r.content_hash, r.external_id))


def compute_input_fingerprint(
    reviews: Sequence[ReviewForSummary],
    prompt_version: str,
    model: str,
    provider: str = "openai",
    review_type: str = "critic",
    language: str = "ru",
) -> str:
    """
    Compute a deterministic SHA-256 hash of the reviews, prompt version, model,
    provider, review_type, and summary language.
    Used to skip expensive LLM calls if the selected review corpus and configuration are unchanged.
    """
    # Sort reviews deterministically by external_id and content_hash
    sorted_reviews = sorted(reviews, key=lambda r: (r.external_id, r.content_hash))

    payload = {
        "review_type": review_type.lower(),
        "provider": provider.lower(),
        "model": model,
        "prompt_version": prompt_version,
        "language": language.lower(),
        "reviews": [
            {
                "external_id": r.external_id,
                "review_type": r.review_type,
                "score": r.score,
                "platform": r.platform_slug,
                "content_hash": r.content_hash,
                "body": r.body.strip(),
            }
            for r in sorted_reviews
        ],
    }

    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

