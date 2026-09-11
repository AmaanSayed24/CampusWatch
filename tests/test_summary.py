"""Tests for the post-scan assignment summary (10-minute dashboard flow)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.database.connection import init_db
from app.database.repository import Repository
from app.services.reminder_service import ReminderService

TZ = ZoneInfo("Asia/Kolkata")


def make_service(tmp_path) -> tuple[Repository, ReminderService]:
    settings_stub = type(
        "S",
        (),
        {
            "database_url": f"sqlite:///{tmp_path / 't.db'}",
            "timezone": "Asia/Kolkata",
            "reminder_windows": "7d,3d,24h,3h",
            "notify_overdue": False,
        },
    )()
    settings_stub.get_timezone = lambda: TZ
    factory = init_db(settings_stub)
    repo = Repository(factory)
    service = ReminderService(settings_stub, repo, type("N", (), {}), factory)
    return repo, service


def add(repo: Repository, subject_id: int, key: str, title: str, deadline, status):
    repo.upsert_assignment(
        {"external_key": key, "title": title, "status": status, "deadline": deadline},
        subject_id,
    )


def test_summary_classification(tmp_path):
    repo, service = make_service(tmp_path)
    subject = repo.upsert_subject("sub-1", "Data Structures")
    now = datetime.now()
    add(repo, subject.id, "overdue-1", "Assignment 1", now - timedelta(days=2), "PENDING")
    add(repo, subject.id, "upcoming-1", "Assignment 2", now + timedelta(days=3), "PENDING")
    add(repo, subject.id, "none-1", "Assignment 3", None, "PENDING")
    add(repo, subject.id, "done-1", "Assignment 4", now - timedelta(days=1), "SUBMITTED")

    text = service.build_assignment_summary()

    assert "3 outstanding" in text
    assert "1 overdue, 1 upcoming, 1 no deadline" in text
    assert "1 submitted" in text
    assert "❗ OVERDUE (1)" in text and "Assignment 1" in text
    assert "🟠 UPCOMING (1)" in text and "Assignment 2" in text
    assert "➖ NO DEADLINE (1)" in text and "Assignment 3" in text
    # Bucket order: overdue first, upcoming, then no-deadline.
    assert text.index("OVERDUE") < text.index("UPCOMING") < text.index("NO DEADLINE")
    # Submitted work is excluded from the buckets but counted in the header.
    assert "Assignment 4" not in text


def test_truncate_for_toast():
    from app.services.notification_service import MAX_TOAST_CHARS, truncate_for_toast

    short = "tiny message"
    assert truncate_for_toast(short) == short

    long_text = "x" * 2000
    truncated = truncate_for_toast(long_text)
    # Windows NOTIFYICONDATAW hard limit is 256 chars — plyer crashes above it.
    assert len(truncated) <= MAX_TOAST_CHARS
    assert truncated.endswith("...")


def test_summary_orders_upcoming_by_deadline(tmp_path):
    repo, service = make_service(tmp_path)
    subject = repo.upsert_subject("sub-1", "Java")
    now = datetime.now()
    add(repo, subject.id, "far", "Far", now + timedelta(days=10), "PENDING")
    add(repo, subject.id, "soon", "Soon", now + timedelta(days=1), "PENDING")

    text = service.build_assignment_summary()
    assert text.index("Soon") < text.index("Far")


def test_summary_all_overdue_retained(tmp_path):
    """Overdue assignments are kept in the summary, never filtered out."""
    repo, service = make_service(tmp_path)
    subject = repo.upsert_subject("sub-1", "DS")
    now = datetime.now()
    add(repo, subject.id, "old-1", "A1", now - timedelta(days=30), "PENDING")
    add(repo, subject.id, "old-2", "A2", now - timedelta(days=10), "PENDING")

    text = service.build_assignment_summary()
    assert "2 overdue, 0 upcoming, 0 no deadline" in text
    assert "A1" in text and "A2" in text
