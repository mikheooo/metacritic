from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.platform import GamePlatform, Platform
from app.schemas.platform import PlatformBase
from app.services.crawler.parser import is_navigation_or_category_label

router = APIRouter(prefix="/platforms", tags=["Platforms"])


@router.get("", response_model=list[PlatformBase])
async def list_platforms(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve distinct real gaming platforms actually present in the database,
    excluding navigation or category artifacts, sorted human-friendly.
    """
    stmt = (
        select(Platform.name, Platform.slug)
        .join(GamePlatform, GamePlatform.platform_id == Platform.id)
        .distinct()
        .order_by(Platform.name.asc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    platforms = []
    seen_slugs = set()
    for row in rows:
        name, slug = row
        if (
            is_navigation_or_category_label(name)
            or is_navigation_or_category_label(slug)
            or slug in seen_slugs
        ):
            continue
        seen_slugs.add(slug)
        platforms.append(PlatformBase(name=name, slug=slug))

    return platforms
