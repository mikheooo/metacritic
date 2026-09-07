import re
from typing import NamedTuple

from app.services.youtube.search_provider import YouTubeVideoCandidate

# Stop words ignored during title token matching
TITLE_STOP_WORDS = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "edition",
    "remastered",
    "remake",
    "definitive",
    "deluxe",
    "bundle",
    "collection",
}

# Negative rejection patterns in video title
REJECT_PATTERNS = [
    (
        re.compile(r"\b(trailer|teaser|reveal trailer|launch trailer|cinematic)\b", re.I),
        "trailer/teaser content",
    ),
    (
        re.compile(
            r"\b(ost|soundtrack|original score|main theme|theme song|bgm|music video)\b", re.I
        ),
        "music/soundtrack content",
    ),
    (
        re.compile(
            r"\b(review|before you buy|is it worth it|critique|analysis|video essay)\b", re.I
        ),
        "review/critique content",
    ),
    (re.compile(r"\b(reaction|reacts|reacting)\b", re.I), "reaction content"),
    (
        re.compile(r"\b(dev diary|developer diary|behind the scenes|making of|interview)\b", re.I),
        "developer diary/interview",
    ),
    (
        re.compile(r"\b(nintendo direct|state of play|xbox showcase|summer game fest|e3)\b", re.I),
        "press conference/showcase",
    ),
    (
        re.compile(r"\b(unboxing|figure|statue|collector'?s edition unboxing)\b", re.I),
        "unboxing content",
    ),
]

# Positive gameplay/Let's Play patterns
POSITIVE_PATTERNS = [
    re.compile(r"\b(let'?s play)\b", re.I),
    re.compile(r"\b(gameplay)\b", re.I),
    re.compile(r"\b(playthrough)\b", re.I),
    re.compile(r"\b(walkthrough)\b", re.I),
    re.compile(r"\b(longplay)\b", re.I),
    re.compile(r"\b(full game)\b", re.I),
    re.compile(r"\b(part\s*\d+|ep\s*\d+|episode\s*\d+)\b", re.I),
    re.compile(r"\b(stream|vod|live stream)\b", re.I),
    re.compile(r"\b(blind run|blind playthrough)\b", re.I),
]


class RelevanceResult(NamedTuple):
    is_relevant: bool
    reason: str


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercased alphanumeric words."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [token for token in cleaned.split() if token]


def evaluate_candidate_relevance(
    candidate: YouTubeVideoCandidate,
    game_title: str,
) -> RelevanceResult:
    """
    Deterministic relevance evaluation:
    1. Rejects obvious non-gameplay (trailers, OST, reactions, reviews, dev diaries, shorts).
    2. Validates game title presence (exact substring or core non-stop tokens match).
    3. Confirms presence of gameplay / Let's Play signals.
    """
    vid_title = candidate.title.strip()
    vid_desc = candidate.description.strip()
    combined_text = f"{vid_title} {vid_desc}"

    # 1. Reject very short videos (e.g. YouTube shorts < 90 seconds or marked with #shorts)
    if candidate.duration_seconds is not None and candidate.duration_seconds < 90:
        return RelevanceResult(
            is_relevant=False,
            reason=f"Rejected: video duration too short ({candidate.duration_seconds}s < 90s, likely a short or clip)",
        )
    if "#shorts" in vid_title.lower() or "#shorts" in vid_desc.lower():
        return RelevanceResult(
            is_relevant=False,
            reason="Rejected: candidate is a YouTube Short (#shorts)",
        )

    # 2. Rejection patterns in video title (primary title check)
    for pattern, reject_reason in REJECT_PATTERNS:
        # Check title first (strongest indicator)
        if pattern.search(vid_title):
            # Check if it's explicitly titled as "gameplay trailer" - still reject because it's a trailer, not a let's play
            return RelevanceResult(
                is_relevant=False,
                reason=f"Rejected: video title indicates {reject_reason}",
            )

    # 3. Game title token matching
    game_tokens = [t for t in tokenize(game_title) if t not in TITLE_STOP_WORDS]
    if not game_tokens:
        game_tokens = tokenize(game_title)

    norm_game_title = " ".join(tokenize(game_title))
    norm_vid_title = " ".join(tokenize(vid_title))

    # Exact or contiguous match of game title
    has_title_match = norm_game_title in norm_vid_title or game_title.lower() in vid_title.lower()

    if not has_title_match:
        # Check token intersection ratio
        vid_title_tokens = set(tokenize(vid_title))
        matched_tokens = [t for t in game_tokens if t in vid_title_tokens]
        # At least 70% of core game title tokens must be in video title
        match_ratio = len(matched_tokens) / max(len(game_tokens), 1)
        if match_ratio >= 0.7:
            has_title_match = True
        else:
            # Fallback: check if full title is in snippet/description
            if (
                norm_game_title in " ".join(tokenize(vid_desc))
                or game_title.lower() in vid_desc.lower()
            ):
                has_title_match = True
            else:
                return RelevanceResult(
                    is_relevant=False,
                    reason=f"Rejected: game title '{game_title}' tokens missing from video title and description",
                )

    # 4. Gameplay / Let's Play signal verification
    has_positive_signal = any(pattern.search(combined_text) for pattern in POSITIVE_PATTERNS)
    if not has_positive_signal:
        # Check if duration indicates long-form gameplay (>= 15 minutes / 900 seconds)
        if candidate.duration_seconds and candidate.duration_seconds >= 900:
            has_positive_signal = True

    if not has_positive_signal:
        return RelevanceResult(
            is_relevant=False,
            reason="Rejected: lacking gameplay, Let's Play, walkthrough, or playthrough signals",
        )

    return RelevanceResult(
        is_relevant=True,
        reason=f"Accepted: verified Let's Play gameplay candidate for '{game_title}'",
    )


def sort_candidates_by_views(
    candidates: list[YouTubeVideoCandidate],
) -> list[YouTubeVideoCandidate]:
    """Sort candidate videos deterministically by view_count descending, then video_id."""
    return sorted(
        candidates,
        key=lambda c: (c.view_count or 0, c.like_count or 0, c.video_id),
        reverse=True,
    )
