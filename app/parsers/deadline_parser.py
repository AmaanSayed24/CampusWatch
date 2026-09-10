"""Deadline parsing: normalize portal date formats into tz-aware datetimes (§10, §27).

Handled formats (all naive results are assumed to be in the configured timezone):
    15/09/2026            15-09-2026            15.09.2026
    15/09/2026 11:59 PM   15/09/2026 23:59
    Sep 15, 2026          Sep 15, 2026 11:59 PM
    15 September 2026     15 September 2026, 11:59 PM
    15th September 2026   Sep 15th, 2026 11:59 PM
    2026-09-15            2026-09-15T23:59:00
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_FORMATS = [
    "%d/%m/%Y %I:%M %p",
    "%d-%m-%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%b %d, %Y %I:%M %p",
    "%b %d, %Y",
    "%B %d, %Y %I:%M %p",
    "%B %d, %Y",
    "%d %B %Y %I:%M %p",
    "%d %B %Y, %I:%M %p",
    "%d %B %Y",
    "%d %b %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
]

# Ordinal suffixes are stripped before parsing ("15th" -> "15"), so both the
# format list and the extraction regexes below never need suffix variants.
_ORDINAL_SUFFIX = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)


def parse_deadline(raw: str | None, tz: ZoneInfo) -> datetime | None:
    """Parse a deadline string into a timezone-aware datetime, or None."""
    if not raw:
        return None

    text = re.sub(r"\s+", " ", str(raw).strip().rstrip("."))
    text = _ORDINAL_SUFFIX.sub(r"\1", text)
    if not text:
        return None

    for fmt in _FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def extract_deadline_from_text(text: str | None, tz: ZoneInfo) -> datetime | None:
    """Find a date-like substring inside free text and parse it."""
    if not text:
        return None
    pattern = (
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm])?)?"
        r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    )
    match = re.search(pattern, text)
    if not match:
        return None
    return parse_deadline(match.group(0), tz)
