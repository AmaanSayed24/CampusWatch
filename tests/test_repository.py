from pathlib import Path

import pytest

from app.database.connection import init_db
from app.database.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    settings_stub = type("S", (), {"database_url": f"sqlite:///{tmp_path / 'test.db'}"})
    factory = init_db(settings_stub())
    return Repository(factory)


def test_upsert_subject_idempotent(repo: Repository):
    first = repo.upsert_subject("sub-1", "Data Structures")
    second = repo.upsert_subject("sub-1", "Data Structures")
    assert first.id == second.id
    assert len(repo.get_subjects()) == 1


def test_upsert_assignment_new_then_existing(repo: Repository):
    subject = repo.upsert_subject("sub-1", "Java")
    data = {
        "external_key": "a-1",
        "portal_id": "10",
        "title": "Exception Handling",
        "description": None,
        "assigned_at": None,
        "deadline": None,
        "status": "PENDING",
        "source_url": None,
        "content_hash": "h1",
    }
    assignment, is_new = repo.upsert_assignment(data, subject.id)
    assert is_new

    data["title"] = "Exception Handling v2"
    updated, is_new = repo.upsert_assignment(data, subject.id)
    assert not is_new
    assert updated.id == assignment.id
    assert updated.title == "Exception Handling v2"
    assert len(repo.get_assignments()) == 1


def test_notification_dedup(repo: Repository):
    subject = repo.upsert_subject("sub-1", "Java")
    data = {"external_key": "a-1", "title": "T", "status": "PENDING"}
    assignment, _ = repo.upsert_assignment(data, subject.id)

    assert not repo.has_notification(assignment.id, "NEW_ASSIGNMENT")
    repo.record_notification(assignment.id, "NEW_ASSIGNMENT")
    assert repo.has_notification(assignment.id, "NEW_ASSIGNMENT")
    repo.record_notification(assignment.id, "NEW_ASSIGNMENT")  # still one row type-wise
    assert repo.has_notification(assignment.id, "NEW_ASSIGNMENT")


def test_due_soon_assignments(repo: Repository):
    from datetime import datetime, timedelta

    subject = repo.upsert_subject("sub-1", "DS")
    now = datetime.now()
    soon = {
        "external_key": "soon", "title": "Soon",
        "status": "PENDING", "deadline": now + timedelta(days=2),
    }
    far = {
        "external_key": "far", "title": "Far",
        "status": "PENDING", "deadline": now + timedelta(days=30),
    }
    repo.upsert_assignment(soon, subject.id)
    repo.upsert_assignment(far, subject.id)

    due_soon = repo.get_due_soon_assignments(timedelta(days=7))
    assert [a.external_key for a in due_soon] == ["soon"]


def test_manual_deadline_survives_sync(repo: Repository):
    """A manually set deadline is never overwritten by the portal's N/A."""
    from datetime import datetime

    subject = repo.upsert_subject("sub-1", "Software Engineering")
    data = {
        "external_key": "pdf-1", "title": "Assignment 1",
        "status": "PENDING", "deadline": None,  # portal stores no date
    }
    assignment, _ = repo.upsert_assignment(data, subject.id)

    repo.set_manual_deadline(assignment.id, datetime(2026, 9, 20, 23, 59))
    # Portal sync comes back with still no deadline...
    updated, _ = repo.upsert_assignment(dict(data), subject.id)
    assert updated.deadline == datetime(2026, 9, 20, 23, 59)
    assert updated.manual_deadline is True

    # Clearing the override restores the portal value.
    repo.set_manual_deadline(assignment.id, None)
    cleared, _ = repo.upsert_assignment(dict(data), subject.id)
    assert cleared.deadline is None
    assert cleared.manual_deadline is False


def test_get_assignment(repo: Repository):
    subject = repo.upsert_subject("sub-1", "Java")
    assignment, _ = repo.upsert_assignment(
        {"external_key": "x", "title": "T", "status": "PENDING"}, subject.id
    )
    assert repo.get_assignment(assignment.id) is not None
    assert repo.get_assignment(9999) is None


def test_sync_run_lifecycle(repo: Repository):
    run_id = repo.start_sync_run()
    repo.finish_sync_run(run_id, "SUCCESS", subjects_checked=6, assignments_found=10)
    run = repo.get_last_sync_run()
    assert run.status == "SUCCESS"
    assert run.subjects_checked == 6
    assert run.assignments_found == 10
    assert run.finished_at is not None


def test_get_previous_sync_run(repo: Repository):
    assert repo.get_previous_sync_run(1) is None  # nothing before run 1

    first = repo.start_sync_run()
    repo.finish_sync_run(first, "SUCCESS", 1, 2)
    second = repo.start_sync_run()
    repo.finish_sync_run(second, "FAILED", 0, 0, "payloads not captured")

    previous = repo.get_previous_sync_run(second)
    assert previous is not None
    assert previous.id == first
    assert previous.status == "SUCCESS"
