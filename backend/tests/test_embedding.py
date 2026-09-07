import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.models.summary import GameReviewSummary
from app.services.ai.embedding_builder import (
    build_game_embedding_text,
    compute_embedding_fingerprint,
)
from app.services.ai.embedding_provider import (
    FakeEmbeddingProvider,
    get_embedding_provider,
)
from app.services.ai.embedding_service import GameEmbeddingService, validate_vector


def test_build_game_embedding_text_deterministic():
    """Requirement 8, 9, 10: build_game_embedding_text produces deterministic canonical text."""
    p1 = Platform(id=1, name="PlayStation 5", slug="ps5")
    p2 = Platform(id=2, name="PC", slug="pc")
    p3 = Platform(id=3, name="Xbox Series X", slug="xbox-series-x")

    game = Game(
        id=1,
        title="Elden Ring",
        metacritic_slug="elden-ring",
        metacritic_url="https://www.metacritic.com/game/elden-ring/",
        developer="FromSoftware",
        description="A dark fantasy action RPG set in the Lands Between.",
        critic_summary="An extraordinary open world masterpiece with deep combat.",
        user_summary="One of the best games ever made despite occasional frame drops.",
    )
    # Give platforms in unsorted order
    game.game_platforms = [
        GamePlatform(id=1, game_id=1, platform_id=3, platform=p3),
        GamePlatform(id=2, game_id=1, platform_id=1, platform=p1),
        GamePlatform(id=3, game_id=1, platform_id=2, platform=p2),
    ]

    text1 = build_game_embedding_text(game)
    text2 = build_game_embedding_text(game)

    assert text1 == text2
    assert "Title:\nElden Ring" in text1
    assert "Developer:\nFromSoftware" in text1
    # Platforms must be sorted alphabetically: PC, PlayStation 5, Xbox Series X
    assert "Platforms:\nPC, PlayStation 5, Xbox Series X" in text1
    assert "Description:\nA dark fantasy action RPG set in the Lands Between." in text1
    assert "Critics:\nAn extraordinary open world masterpiece with deep combat." in text1
    assert "Players:\nOne of the best games ever made despite occasional frame drops." in text1

    # Invariant: ratings, IDs, timestamps, URLs, token counts must NOT be in text
    assert "Metascore" not in text1
    assert "Userscore" not in text1
    assert "http" not in text1
    assert "Lands Between." in text1


def test_build_game_embedding_text_no_none():
    """Requirement 8 & 9: Missing fields must not insert literal 'None' into canonical text."""
    game = Game(
        id=2,
        title="Minimal Indie",
        metacritic_slug="minimal-indie",
        metacritic_url="https://www.metacritic.com/game/minimal-indie/",
        developer=None,
        description=None,
        critic_summary=None,
        user_summary=None,
    )
    game.game_platforms = []

    text = build_game_embedding_text(game)
    assert "None" not in text
    assert text == "Title:\nMinimal Indie"


def test_build_game_embedding_text_prefers_review_summaries_table():
    """Ensures critic and user summaries from GameReviewSummary table are included."""
    game = Game(
        id=3,
        title="Game With Summaries",
        metacritic_slug="game-with-summaries",
        metacritic_url="https://www.metacritic.com/game/game-with-summaries/",
        developer="Studio",
        description="Desc",
    )
    game.game_platforms = []
    game.review_summaries = [
        GameReviewSummary(
            id=1,
            game_id=3,
            review_type="critic",
            summary="Critics loved the atmosphere and pacing.",
            likes=["Pacing"],
            dislikes=["Difficulty"],
            review_count_used=10,
            total_reviews_seen=10,
            input_fingerprint="fp1",
            provider="openrouter",
            model="openai/gpt-4o-mini",
            prompt_version="v1",
        ),
        GameReviewSummary(
            id=2,
            game_id=3,
            review_type="user",
            summary="Players praised the soundtrack.",
            likes=["Music"],
            dislikes=["Bugs"],
            review_count_used=20,
            total_reviews_seen=20,
            input_fingerprint="fp2",
            provider="openrouter",
            model="openai/gpt-4o-mini",
            prompt_version="v1",
        ),
    ]

    text = build_game_embedding_text(game)
    assert "Critics:\nCritics loved the atmosphere and pacing." in text
    assert "Players:\nPlayers praised the soundtrack." in text


def test_compute_embedding_fingerprint_sensitivity():
    """Requirement 11: Fingerprint is sensitive to text, provider, model, dimensions, and version."""
    t1 = "Title:\nGame A\n\nDescription:\nFirst version"
    t2 = "Title:\nGame A\n\nDescription:\nSecond version"

    fp_base = compute_embedding_fingerprint(t1, "openrouter", "openai/text-embedding-3-small", 1536, "v1")
    fp_same = compute_embedding_fingerprint(t1, "openrouter", "openai/text-embedding-3-small", 1536, "v1")
    assert fp_base == fp_same

    # Text changed
    fp_t2 = compute_embedding_fingerprint(t2, "openrouter", "openai/text-embedding-3-small", 1536, "v1")
    assert fp_base != fp_t2

    # Provider changed
    fp_prov = compute_embedding_fingerprint(t1, "fake", "openai/text-embedding-3-small", 1536, "v1")
    assert fp_base != fp_prov

    # Model changed
    fp_model = compute_embedding_fingerprint(t1, "openrouter", "openai/text-embedding-3-large", 1536, "v1")
    assert fp_base != fp_model

    # Dimensions changed
    fp_dim = compute_embedding_fingerprint(t1, "openrouter", "openai/text-embedding-3-small", 512, "v1")
    assert fp_base != fp_dim

    # Input version changed
    fp_ver = compute_embedding_fingerprint(t1, "openrouter", "openai/text-embedding-3-small", 1536, "v2")
    assert fp_base != fp_ver


def test_validate_vector():
    """Requirement 14: Validates vector length and ensures all floats are finite."""
    # Valid vector
    validate_vector([0.1, -0.2, 0.5], 3)

    # Wrong dimension
    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        validate_vector([0.1, 0.2], 3)

    # Empty vector
    with pytest.raises(ValueError, match="Vector cannot be empty"):
        validate_vector([], 0)

    # NaN
    with pytest.raises(ValueError, match="not finite"):
        validate_vector([0.1, float("nan"), 0.3], 3)

    # Infinity
    with pytest.raises(ValueError, match="not finite"):
        validate_vector([0.1, float("inf"), 0.3], 3)


def test_embedding_provider_missing_key_raises_error(monkeypatch):
    """Requirement 3: Missing OPENROUTER_API_KEY under openrouter provider must raise explicit ValueError."""
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", None)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is missing or empty"):
        get_embedding_provider()

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "   ")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is missing or empty"):
        get_embedding_provider()


@pytest.mark.asyncio
async def test_embedding_cost_control_skips_unchanged(db_session: AsyncSession):
    """Requirement 12: If fingerprint is unchanged, embedding provider is NOT called."""
    game = Game(
        title="Cost Control Game",
        metacritic_slug="cost-control-game",
        metacritic_url="https://www.metacritic.com/game/cost-control-game/",
        developer="Dev Studio",
        description="Great game with deep lore.",
    )
    db_session.add(game)
    await db_session.flush()

    fake_provider = FakeEmbeddingProvider(dimensions=1536)
    service = GameEmbeddingService(db=db_session, provider=fake_provider)

    # 1. First run: generates embedding
    res1 = await service.refresh_game_embedding(game.id)
    assert res1.status == "generated"
    assert fake_provider.call_count == 1

    # 2. Second run with same game state: must be skipped_unchanged with 0 provider calls
    res2 = await service.refresh_game_embedding(game.id)
    assert res2.status == "skipped_unchanged"
    assert fake_provider.call_count == 1  # No additional provider call!
    assert res1.input_fingerprint == res2.input_fingerprint


@pytest.mark.asyncio
async def test_embedding_provider_switch_regenerates(db_session: AsyncSession):
    """Requirement 13: Switching provider/model updates fingerprint and forces regeneration."""
    game = Game(
        title="Switch Provider Game",
        metacritic_slug="switch-provider-game",
        metacritic_url="https://www.metacritic.com/game/switch-provider-game/",
        developer="Dev Studio",
        description="Initial description.",
    )
    db_session.add(game)
    await db_session.flush()

    provider1 = FakeEmbeddingProvider(dimensions=1536, model="model-v1")
    service1 = GameEmbeddingService(db=db_session, provider=provider1)

    res1 = await service1.refresh_game_embedding(game.id)
    assert res1.status == "generated"
    assert provider1.call_count == 1

    # Switch to provider 2 with different model
    provider2 = FakeEmbeddingProvider(dimensions=1536, model="model-v2")
    service2 = GameEmbeddingService(db=db_session, provider=provider2)

    res2 = await service2.refresh_game_embedding(game.id)
    assert res2.status == "generated"
    assert provider2.call_count == 1
    assert res1.input_fingerprint != res2.input_fingerprint


@pytest.mark.asyncio
async def test_embedding_failure_isolation(db_session: AsyncSession):
    """Requirement 24 & 36: Embedding provider failure does not rollback existing game."""
    game = Game(
        title="Failure Isolation Game",
        metacritic_slug="failure-isolation-game",
        metacritic_url="https://www.metacritic.com/game/failure-isolation-game/",
        developer="Dev Studio",
    )
    db_session.add(game)
    await db_session.flush()

    class FailingEmbeddingProvider:
        provider = "failing"
        model = "failing-model"
        dimensions = 1536

        async def embed(self, text: str):
            raise ConnectionError("Simulated embedding upstream timeout")

    service = GameEmbeddingService(db=db_session, provider=FailingEmbeddingProvider())
    res = await service.refresh_game_embedding(game.id)

    assert res.status == "failed"
    assert "Simulated embedding upstream timeout" in (res.error or "")

    # Invariant: Game remains committed in database
    await db_session.refresh(game)
    assert game.id is not None
