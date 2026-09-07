from typing import Protocol

from app.services.crawler.dtos import BrowsePage, GameCandidate, GameDetails, ReviewPage


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

    async def get_critic_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        """Fetch critic reviews page for a game."""
        ...

    async def get_user_reviews(
        self, slug: str, page: int = 1, platform: str | None = None
    ) -> ReviewPage:
        """Fetch user reviews page for a game."""
        ...

