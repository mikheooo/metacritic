from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import DailyGameProcessing


@pytest.mark.asyncio
async def test_daily_processing_invariant_same_date_rejected_next_date_allowed(
    db_session: AsyncSession,
) -> None:
    """
    CRITICAL PROJECT INVARIANT:
    A game must never be processed more than once within the same calendar day,
    but processing on a subsequent calendar day MUST be allowed.
    """
    test_game_id = "metacritic-game-chrono-trigger"
    day_one = date(2026, 9, 7)
    day_two = day_one + timedelta(days=1)

    # 1. First attempt on Day 1 -> Allowed
    record_day1 = DailyGameProcessing(
        processing_date=day_one,
        game_external_id=test_game_id,
    )
    db_session.add(record_day1)
    await db_session.commit()
    await db_session.refresh(record_day1)
    assert record_day1.id is not None
    assert record_day1.processing_date == day_one

    # 2. Second attempt on Day 1 (same game, same date) -> Duplicate REJECTED
    duplicate_day1 = DailyGameProcessing(
        processing_date=day_one,
        game_external_id=test_game_id,
    )
    db_session.add(duplicate_day1)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # 3. Subsequent attempt on Day 2 (same game, next date) -> ALLOWED
    record_day2 = DailyGameProcessing(
        processing_date=day_two,
        game_external_id=test_game_id,
    )
    db_session.add(record_day2)
    await db_session.commit()
    await db_session.refresh(record_day2)
    assert record_day2.id is not None
    assert record_day2.processing_date == day_two
