from zoneinfo import ZoneInfo

import pytest

from app.parsers.deadline_parser import extract_deadline_from_text, parse_deadline

TZ = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("15/09/2026", "2026-09-15T00:00:00+05:30"),
        ("15-09-2026", "2026-09-15T00:00:00+05:30"),
        ("15.09.2026", "2026-09-15T00:00:00+05:30"),
        ("Sep 15, 2026", "2026-09-15T00:00:00+05:30"),
        ("September 15, 2026", "2026-09-15T00:00:00+05:30"),
        ("15 September 2026", "2026-09-15T00:00:00+05:30"),
        ("15th September 2026", "2026-09-15T00:00:00+05:30"),
        ("15Th September 2026", "2026-09-15T00:00:00+05:30"),
        ("15/09/2026 11:59 PM", "2026-09-15T23:59:00+05:30"),
        ("15/09/2026 23:59", "2026-09-15T23:59:00+05:30"),
        ("15 September 2026, 11:59 PM", "2026-09-15T23:59:00+05:30"),
        ("Sep 15th, 2026", "2026-09-15T00:00:00+05:30"),
        ("2026-09-15", "2026-09-15T00:00:00+05:30"),
        ("2026-09-15T23:59:00", "2026-09-15T23:59:00+05:30"),
        ("", None),
        (None, None),
        ("not a date", None),
    ],
)
def test_parse_deadline_formats(raw, expected):
    result = parse_deadline(raw, TZ)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.isoformat() == expected
        assert result.tzinfo is not None


def test_extract_deadline_from_text():
    text = "The assignment is due on 20/09/2026 at 11:59 PM. Late submissions not allowed."
    result = extract_deadline_from_text(text, TZ)
    assert result is not None
    assert result.day == 20 and result.month == 9 and result.year == 2026


def test_extract_deadline_from_text_ordinal():
    text = "MCA Assignment 1: submit by 15th September 2026."
    result = extract_deadline_from_text(text, TZ)
    assert result is not None
    assert result.day == 15 and result.month == 9 and result.year == 2026


def test_extract_deadline_from_text_without_date():
    assert extract_deadline_from_text("no date here", TZ) is None
    assert extract_deadline_from_text(None, TZ) is None


def test_naive_assumed_in_configured_tz():
    result = parse_deadline("15/09/2026", TZ)
    assert result.utcoffset().total_seconds() == 5.5 * 3600
