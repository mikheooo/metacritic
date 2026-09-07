import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import GameEmbedding
from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.models.similar import SimilarGame
from app.services.ai.similarity_service import SimilarGamesService


@pytest.mark.asyncio
async def test_synthetic_vector_ranking(db_session: AsyncSession):
    """
    Requirement 35: Deterministic ranking with synthetic vectors:
      Game A [1.0, 0.0, 0.0]
      Game B [0.99, 0.01, 0.0] (almost identical to A)
      Game C [0.7, 0.7, 0.0]   (partially aligned)
      Game D [0.0, 1.0, 0.0]   (orthogonal to A)
    Proves: A -> B ranked first, followed by C, then D.
    """
    game_a = Game(title="Game A", metacritic_slug="game-a", metacritic_url="https://mc.com/game-a")
    game_b = Game(title="Game B", metacritic_slug="game-b", metacritic_url="https://mc.com/game-b")
    game_c = Game(title="Game C", metacritic_slug="game-c", metacritic_url="https://mc.com/game-c")
    game_d = Game(title="Game D", metacritic_slug="game-d", metacritic_url="https://mc.com/game-d")

    db_session.add_all([game_a, game_b, game_c, game_d])
    await db_session.flush()

    emb_a = GameEmbedding(
        game_id=game_a.id,
        embedding=[1.0, 0.0, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fpa",
        input_version="v1",
    )
    emb_b = GameEmbedding(
        game_id=game_b.id,
        embedding=[0.99, 0.01, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fpb",
        input_version="v1",
    )
    emb_c = GameEmbedding(
        game_id=game_c.id,
        embedding=[0.7, 0.7, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fpc",
        input_version="v1",
    )
    emb_d = GameEmbedding(
        game_id=game_d.id,
        embedding=[0.0, 1.0, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fpd",
        input_version="v1",
    )
    db_session.add_all([emb_a, emb_b, emb_c, emb_d])
    await db_session.commit()

    service = SimilarGamesService(db=db_session, limit=5)
    matches = await service.find_similar_games(game_id=game_a.id)

    assert len(matches) == 3
    # Expected ranking: B (closest), then C, then D
    assert matches[0][0] == game_b.id
    assert matches[1][0] == game_c.id
    assert matches[2][0] == game_d.id

    # Verify descending score ordering
    assert matches[0][1] > matches[1][1] > matches[2][1]
    assert matches[0][1] > 0.95
    assert matches[2][1] < 0.1


@pytest.mark.asyncio
async def test_similarity_never_recommends_self(db_session: AsyncSession):
    """Requirement 17: Source game must NEVER be in its own similar games list."""
    game_1 = Game(
        title="Self Check 1", metacritic_slug="self-1", metacritic_url="https://mc.com/self-1"
    )
    game_2 = Game(
        title="Self Check 2", metacritic_slug="self-2", metacritic_url="https://mc.com/self-2"
    )
    db_session.add_all([game_1, game_2])
    await db_session.flush()

    emb_1 = GameEmbedding(
        game_id=game_1.id,
        embedding=[1.0, 0.0, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fp1",
        input_version="v1",
    )
    emb_2 = GameEmbedding(
        game_id=game_2.id,
        embedding=[1.0, 0.0, 0.0],
        provider="fake",
        model="fake-model",
        dimensions=3,
        input_fingerprint="fp2",
        input_version="v1",
    )
    db_session.add_all([emb_1, emb_2])
    await db_session.commit()

    service = SimilarGamesService(db=db_session, limit=5)
    recs = await service.refresh_for_game(game_1.id)

    assert all(r.similar_game_id != game_1.id for r in recs)
    assert len(recs) == 1
    assert recs[0].similar_game_id == game_2.id


@pytest.mark.asyncio
async def test_similarity_top_k_limit(db_session: AsyncSession):
    """Requirement 16: Limits output to configured top-K (default 5)."""
    games = [
        Game(title=f"Game {i}", metacritic_slug=f"g-{i}", metacritic_url=f"https://mc.com/g-{i}")
        for i in range(8)
    ]
    db_session.add_all(games)
    await db_session.flush()

    for i, g in enumerate(games):
        # Slightly different vectors
        db_session.add(
            GameEmbedding(
                game_id=g.id,
                embedding=[1.0, i * 0.1, 0.0],
                provider="fake",
                model="fake-model",
                dimensions=3,
                input_fingerprint=f"fp{i}",
                input_version="v1",
            )
        )
    await db_session.commit()

    service = SimilarGamesService(db=db_session, limit=5)
    matches = await service.find_similar_games(game_id=games[0].id)
    assert len(matches) == 5


@pytest.mark.asyncio
async def test_similarity_unembedded_games_excluded(db_session: AsyncSession):
    """Requirement 18: Unembedded games are excluded from results; unembedded source returns []."""
    g_embedded = Game(title="Embedded", metacritic_slug="emb", metacritic_url="https://mc.com/emb")
    g_unembedded = Game(
        title="Unembedded", metacritic_slug="unemb", metacritic_url="https://mc.com/unemb"
    )
    db_session.add_all([g_embedded, g_unembedded])
    await db_session.flush()

    db_session.add(
        GameEmbedding(
            game_id=g_embedded.id,
            embedding=[1.0, 0.0, 0.0],
            provider="fake",
            model="fake-model",
            dimensions=3,
            input_fingerprint="fp_emb",
            input_version="v1",
        )
    )
    await db_session.commit()

    service = SimilarGamesService(db=db_session, limit=5)

    # Source game with no embedding returns empty list without error
    recs_unemb = await service.find_similar_games(g_unembedded.id)
    assert recs_unemb == []

    # Target candidate with no embedding is not included
    recs_emb = await service.find_similar_games(g_embedded.id)
    assert recs_emb == []  # Only unembedded game exists as candidate, so result is empty


@pytest.mark.asyncio
async def test_similarity_atomic_refresh_and_idempotency(db_session: AsyncSession):
    """Requirement 21 & 36: Multiple refreshes atomically replace stale rows with 0 duplicates."""
    g1 = Game(title="G1", metacritic_slug="g1", metacritic_url="https://mc.com/g1")
    g2 = Game(title="G2", metacritic_slug="g2", metacritic_url="https://mc.com/g2")
    db_session.add_all([g1, g2])
    await db_session.flush()

    db_session.add(
        GameEmbedding(
            game_id=g1.id,
            embedding=[1.0, 0.0],
            provider="fake",
            model="m",
            dimensions=2,
            input_fingerprint="f1",
            input_version="v1",
        )
    )
    db_session.add(
        GameEmbedding(
            game_id=g2.id,
            embedding=[0.9, 0.1],
            provider="fake",
            model="m",
            dimensions=2,
            input_fingerprint="f2",
            input_version="v1",
        )
    )
    await db_session.commit()

    service = SimilarGamesService(db=db_session, limit=5)

    # First run
    recs1 = await service.refresh_for_game(g1.id)
    assert len(recs1) == 1

    # Second identical run
    recs2 = await service.refresh_for_game(g1.id)
    assert len(recs2) == 1

    # Verify DB has exactly 1 row for g1, no duplicates
    count_stmt = select(func.count(SimilarGame.id)).where(SimilarGame.game_id == g1.id)
    total_recs = await db_session.scalar(count_stmt)
    assert total_recs == 1


@pytest.mark.asyncio
async def test_game_detail_api_exposes_similar_games(client: AsyncClient, db_session: AsyncSession):
    """Requirement 30 & 31: GET /api/games/{id} exposes similar_games with expected fields."""
    platform = Platform(id=1, name="PlayStation 5", slug="ps5")
    db_session.add(platform)

    g1 = Game(title="Source Game", metacritic_slug="src", metacritic_url="https://mc.com/src")
    g2 = Game(
        title="Target Game",
        metacritic_slug="tgt",
        metacritic_url="https://mc.com/tgt",
        cover_url="https://mc.com/cover.jpg",
    )
    db_session.add_all([g1, g2])
    await db_session.flush()

    gp = GamePlatform(id=1, game_id=g2.id, platform_id=platform.id, platform=platform)
    db_session.add(gp)

    db_session.add(
        GameEmbedding(
            game_id=g1.id,
            embedding=[1.0, 0.0],
            provider="fake",
            model="m",
            dimensions=2,
            input_fingerprint="f1",
            input_version="v1",
        )
    )
    db_session.add(
        GameEmbedding(
            game_id=g2.id,
            embedding=[0.95, 0.05],
            provider="fake",
            model="m",
            dimensions=2,
            input_fingerprint="f2",
            input_version="v1",
        )
    )
    await db_session.commit()

    # Refresh recommendations
    service = SimilarGamesService(db=db_session, limit=5)
    await service.refresh_for_game(g1.id)

    # Call REST API
    resp = await client.get(f"/api/games/{g1.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert "similar_games" in data
    assert len(data["similar_games"]) == 1
    sim_item = data["similar_games"][0]
    assert sim_item["id"] == g2.id
    assert sim_item["title"] == "Target Game"
    assert sim_item["cover_url"] == "https://mc.com/cover.jpg"
    assert sim_item["similarity_score"] > 0.9
    assert "PlayStation 5" in sim_item["platforms"]
