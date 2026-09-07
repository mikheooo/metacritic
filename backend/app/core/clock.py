from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.config import settings


class Clock(Protocol):
    def now(self) -> datetime:
        """Return current timezone-aware datetime."""
        ...

    def today(self) -> date:
        """Return current calendar date in application timezone."""
        ...


class SystemClock:
    def __init__(self, tz_name: str | None = None) -> None:
        self.tz_name = tz_name or settings.APP_TIMEZONE

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """Deterministic clock for testing time shifts and date rollovers."""

    def __init__(self, current_dt_or_date: datetime | date) -> None:
        if isinstance(current_dt_or_date, datetime):
            self._dt = current_dt_or_date
        else:
            self._dt = datetime(
                current_dt_or_date.year,
                current_dt_or_date.month,
                current_dt_or_date.day,
                tzinfo=ZoneInfo(settings.APP_TIMEZONE),
            )

    def now(self) -> datetime:
        return self._dt

    def today(self) -> date:
        return self._dt.date()

    def advance(self, days: int = 1) -> None:
        from datetime import timedelta

        self._dt = self._dt + timedelta(days=days)


_CURRENT_CLOCK: Clock = SystemClock()


def get_clock() -> Clock:
    return _CURRENT_CLOCK


def set_clock(clock: Clock) -> None:
    global _CURRENT_CLOCK
    _CURRENT_CLOCK = clock


def reset_clock() -> None:
    global _CURRENT_CLOCK
    _CURRENT_CLOCK = SystemClock()


def get_current_date() -> date:
    return get_clock().today()


def get_current_datetime() -> datetime:
    return get_clock().now()
