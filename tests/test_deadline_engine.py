from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.deadline_engine import Urgency, compute_urgency, format_remaining, time_remaining

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 8, 10, 0, 0, tzinfo=TZ)


def dt(**kwargs):
    return NOW + timedelta(**kwargs)


def test_no_deadline():
    assert compute_urgency(None, NOW) is Urgency.NO_DEADLINE


def test_overdue():
    assert compute_urgency(dt(hours=-1), NOW) is Urgency.OVERDUE


def test_due_today():
    assert compute_urgency(datetime(2026, 9, 8, 23, 59, tzinfo=TZ), NOW) is Urgency.DUE_TODAY


def test_due_within_24h():
    assert compute_urgency(dt(hours=20), NOW) is Urgency.DUE_WITHIN_24H


def test_due_within_3_days():
    assert compute_urgency(dt(days=2), NOW) is Urgency.DUE_WITHIN_3_DAYS


def test_due_within_7_days():
    assert compute_urgency(dt(days=6), NOW) is Urgency.DUE_WITHIN_7_DAYS


def test_future():
    assert compute_urgency(dt(days=30), NOW) is Urgency.FUTURE


def test_time_remaining():
    assert time_remaining(dt(hours=5), NOW) == timedelta(hours=5)
    assert time_remaining(None, NOW) is None


def test_format_remaining():
    assert format_remaining(timedelta(days=2, hours=3)) == "2 days"
    assert format_remaining(timedelta(hours=3)) == "3 hours"
    assert format_remaining(timedelta(minutes=45)) == "45 minutes"
