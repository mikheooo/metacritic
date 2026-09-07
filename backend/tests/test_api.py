import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.platform import GamePlatform, Platform


@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient) -> None:
    """Verify GET /health returns 200 OK and status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_check_endpoint(client: AsyncClient) -> None:
    """Verify GET /ready returns 200 OK with connected database."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_list_games_empty(client: AsyncClient) -> None:
    """Verify GET /api/games returns empty list when DB has no games."""
    response = await client.get("/api/games")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 20
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_games_with_filter_and_sorting(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify GET /api/games with q, platform, sort, order, pagination."""
    # Seed platforms
    plat_pc = Platform(name="PC", slug="pc")
    plat_ps5 = Platform(name="PlayStation 5", slug="ps5")
    db_session.add_all([plat_pc, plat_ps5])
    await db_session.commit()

    # Seed games
    game1 = Game(
        title="Portal 2",
        metacritic_slug="portal-2",
        metacritic_url="https://www.metacritic.com/game/portal-2/",
    )
    game2 = Game(
        title="Half-Life 2",
        metacritic_slug="half-life-2",
        metacritic_url="https://www.metacritic.com/game/half-life-2/",
    )
    db_session.add_all([game1, game2])
    await db_session.commit()

    # Seed platform associations with scores
    gp1 = GamePlatform(game_id=game1.id, platform_id=plat_pc.id, metascore=95, userscore=9.1)
    gp2 = GamePlatform(game_id=game2.id, platform_id=plat_pc.id, metascore=96, userscore=9.2)
    gp3 = GamePlatform(game_id=game1.id, platform_id=plat_ps5.id, metascore=94, userscore=8.9)
    db_session.add_all([gp1, gp2, gp3])
    await db_session.commit()

    # 1. Search by title 'Portal'
    resp = await client.get("/api/games", params={"q": "portal"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Portal 2"

    # 2. Filter by platform 'ps5'
    resp = await client.get("/api/games", params={"platform": "ps5"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Portal 2"

    # 3. Sort by metascore desc
    resp = await client.get("/api/games", params={"sort": "metascore", "order": "desc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["items"][0]["title"] == "Half-Life 2"
    assert data["items"][1]["title"] == "Portal 2"

    # 4. Sort by metascore asc
    resp = await client.get("/api/games", params={"sort": "metascore", "order": "asc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"][0]["title"] == "Portal 2"

    # 5. Pagination limit=1
    resp = await client.get("/api/games", params={"limit": 1, "offset": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_game_by_id(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify GET /api/games/{id} returns details or 404."""
    game = Game(
        title="Sekiro",
        metacritic_slug="sekiro",
        metacritic_url="https://www.metacritic.com/game/sekiro/",
        description="Shadows Die Twice",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    # Found
    resp = await client.get(f"/api/games/{game.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == game.id
    assert data["title"] == "Sekiro"

    # Not found
    resp_404 = await client.get("/api/games/999999")
    assert resp_404.status_code == 404
