"""Date/time helpers. All datetimes are timezone-aware (design doc §27)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_in(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def ensure_aware(value: datetime, tz: ZoneInfo) -> datetime:
    """Return a tz-aware datetime; naive values are assumed to be in `tz`."""
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def format_deadline(value: datetime | None) -> str:
    if value is None:
        return "No deadline"
    return value.strftime("%d %B %Y, %I:%M %p").lstrip("0")
