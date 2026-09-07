import hashlib
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.game import Game


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace by trimming lines and collapsing multiple consecutive blank lines."""
    lines = [line.strip() for line in text.splitlines()]
    joined = "\n".join(lines)
    # Collapse 3+ newlines into 2
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def build_game_embedding_text(game: "Game") -> str:
    """
    Constructs a pure canonical deterministic representation of a game for semantic embedding.
    Includes:
      - Title
      - Developer (if present)
      - Platforms (sorted deterministically)
      - Description (if present)
      - Critic summary (from GameReviewSummary or game.critic_summary, if present)
      - User summary (from GameReviewSummary or game.user_summary, if present)

    Strictly excludes:
      - Metascore / Userscore
      - Database IDs
      - Timestamps
      - URLs
      - Crawl metadata / Token usage

    Never outputs literal 'None' for missing values.
    """
    sections: list[str] = []

    # Title
    if game.title and game.title.strip():
        sections.append(f"Title:\n{game.title.strip()}")

    # Developer
    if game.developer and game.developer.strip() and game.developer.strip().lower() != "none":
        sections.append(f"Developer:\n{game.developer.strip()}")

    # Platforms (deterministic alphabetical sort)
    platform_names: list[str] = []
    if getattr(game, "game_platforms", None):
        for gp in game.game_platforms:
            if gp.platform and gp.platform.name and gp.platform.name.strip():
                platform_names.append(gp.platform.name.strip())
    if platform_names:
        sorted_platforms = sorted(set(platform_names))
        sections.append(f"Platforms:\n{', '.join(sorted_platforms)}")

    # Description
    if game.description and game.description.strip() and game.description.strip().lower() != "none":
        sections.append(f"Description:\n{game.description.strip()}")

    # Critic Summary
    critic_summary_text: str | None = None
    if getattr(game, "review_summaries", None):
        for s in game.review_summaries:
            if s.review_type == "critic" and s.summary and s.summary.strip():
                critic_summary_text = s.summary.strip()
                break
    if not critic_summary_text and game.critic_summary and game.critic_summary.strip():
        critic_summary_text = game.critic_summary.strip()

    if critic_summary_text and critic_summary_text.lower() != "none":
        sections.append(f"Critics:\n{critic_summary_text}")

    # Player / User Summary
    user_summary_text: str | None = None
    if getattr(game, "review_summaries", None):
        for s in game.review_summaries:
            if s.review_type == "user" and s.summary and s.summary.strip():
                user_summary_text = s.summary.strip()
                break
    if not user_summary_text and game.user_summary and game.user_summary.strip():
        user_summary_text = game.user_summary.strip()

    if user_summary_text and user_summary_text.lower() != "none":
        sections.append(f"Players:\n{user_summary_text}")

    raw_text = "\n\n".join(sections)
    return _normalize_whitespace(raw_text)


def compute_embedding_fingerprint(
    canonical_text: str,
    provider: str,
    model: str,
    dimensions: int,
    input_version: str,
) -> str:
    """
    Computes a canonical SHA-256 fingerprint for a game's semantic embedding input.
    Binds the canonical text, provider, model, dimensions, and input version.
    """
    payload = {
        "dimensions": dimensions,
        "input_version": input_version.strip(),
        "model": model.strip().lower(),
        "provider": provider.strip().lower(),
        "text": canonical_text,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
