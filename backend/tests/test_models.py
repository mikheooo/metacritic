from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import DailyGameProcessing
from app.models.game import Game
from app.models.platform import GamePlatform, Platform
from app.models.similar import SimilarGame


@pytest.mark.asyncio
async def test_create_game_success(db_session: AsyncSession) -> None:
    """Verify standard creation of a Game model."""
    game = Game(
        title="Elden Ring",
        metacritic_slug="elden-ring",
        metacritic_url="https://www.metacritic.com/game/elden-ring/",
        developer="FromSoftware",
        description="Action RPG masterpiece.",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    assert game.id is not None
    assert game.title == "Elden Ring"
    assert game.created_at is not None
    assert game.updated_at is not None


@pytest.mark.asyncio
async def test_unique_metacritic_url_constraint(db_session: AsyncSession) -> None:
    """Verify unique constraint on external Metacritic identifier (metacritic_url)."""
    game1 = Game(
        title="Hades",
        metacritic_slug="hades",
        metacritic_url="https://www.metacritic.com/game/hades/",
    )
    db_session.add(game1)
    await db_session.commit()

    game2 = Game(
        title="Hades Duplicate URL",
        metacritic_slug="hades-dup",
        metacritic_url="https://www.metacritic.com/game/hades/",  # same URL
    )
    db_session.add(game2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_multiple_platforms_for_single_game(db_session: AsyncSession) -> None:
    """Verify one game can have multiple distinct platforms."""
    game = Game(
        title="Cyberpunk 2077",
        metacritic_slug="cyberpunk-2077",
        metacritic_url="https://www.metacritic.com/game/cyberpunk-2077/",
    )
    p_pc = Platform(name="PC", slug="pc")
    p_ps5 = Platform(name="PlayStation 5", slug="ps5")

    db_session.add_all([game, p_pc, p_ps5])
    await db_session.commit()

    gp_pc = GamePlatform(game_id=game.id, platform_id=p_pc.id, metascore=86, userscore=7.2)
    gp_ps5 = GamePlatform(game_id=game.id, platform_id=p_ps5.id, metascore=87, userscore=7.8)
    db_session.add_all([gp_pc, gp_ps5])
    await db_session.commit()

    await db_session.refresh(game, ["game_platforms"])
    assert len(game.game_platforms) == 2


@pytest.mark.asyncio
async def test_unique_game_platform_constraint(db_session: AsyncSession) -> None:
    """Verify unique constraint on (game_id, platform_id)."""
    game = Game(
        title="Doom",
        metacritic_slug="doom",
        metacritic_url="https://www.metacritic.com/game/doom/",
    )
    plat = Platform(name="PC", slug="pc")
    db_session.add_all([game, plat])
    await db_session.commit()

    gp1 = GamePlatform(game_id=game.id, platform_id=plat.id, metascore=85)
    db_session.add(gp1)
    await db_session.commit()

    gp2 = GamePlatform(game_id=game.id, platform_id=plat.id, metascore=90)
    db_session.add(gp2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_similar_game_prohibit_self_reference(db_session: AsyncSession) -> None:
    """Verify check constraint prohibiting a game referencing itself as similar."""
    game = Game(
        title="Celeste",
        metacritic_slug="celeste",
        metacritic_url="https://www.metacritic.com/game/celeste/",
    )
    db_session.add(game)
    await db_session.commit()

    # Self-reference: game_id == similar_game_id
    self_similar = SimilarGame(
        game_id=game.id,
        similar_game_id=game.id,
        similarity_score=0.99,
    )
    db_session.add(self_similar)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unique_processing_date_game_external_id(db_session: AsyncSession) -> None:
    """Verify unique constraint on (processing_date, game_external_id)."""
    today = date(2026, 9, 7)
    rec1 = DailyGameProcessing(
        processing_date=today,
        game_external_id="game-101",
    )
    db_session.add(rec1)
    await db_session.commit()

    rec2 = DailyGameProcessing(
        processing_date=today,
        game_external_id="game-101",  # Duplicate on same date
    )
    db_session.add(rec2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
