from typing import Protocol

from app.services.crawler.dtos import BrowsePage, GameCandidate, GameDetails


class MetacriticSource(Protocol):
    """
    Source abstraction for fetching Metacritic content.
    Decouples raw network/browser transport from ingestion business logic.
    """

    async def get_new_releases(self) -> list[GameCandidate]:
        """Fetch candidates from Games -> New Releases section."""
        ...

    async def get_browse_page(self, page: int) -> BrowsePage:
        """Fetch a specific page from Browse -> Newest games."""
        ...

    async def get_game_details(self, url: str) -> GameDetails:
        """Fetch detailed information for a specific game."""
        ...
