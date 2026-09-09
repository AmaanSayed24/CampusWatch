from app.services.change_detector import ChangeResult, compare


def make_incoming(**overrides):
    base = {
        "external_key": "key-1",
        "title": "Searching and Sorting",
        "description": "Implement merge sort",
        "deadline": None,
        "status": "PENDING",
        "content_hash": "hash-1",
        "portal_id": "42",
        "source_url": "http://portal/assignment/42",
    }
    base.update(overrides)
    return base


def make_existing(**overrides):
    base = {
        "id": 1,
        "external_key": "key-1",
        "title": "Searching and Sorting",
        "description": "Implement merge sort",
        "deadline": None,
        "status": "PENDING",
        "content_hash": "hash-1",
        "portal_id": "42",
        "source_url": "http://portal/assignment/42",
    }
    base.update(overrides)

    class FakeAssignment:
        pass

    fake = FakeAssignment()
    for key, value in base.items():
        setattr(fake, key, value)
    return fake


def test_new_assignment():
    result = compare(make_incoming(), None)
    assert result.is_new
    assert result.has_changes


def test_unchanged_assignment():
    result = compare(make_incoming(), make_existing())
    assert not result.is_new
    assert not result.deadline_changed
    assert not result.title_changed
    assert not result.has_changes


def test_deadline_changed():
    existing = make_existing(deadline="2026-09-17T00:00:00")
    result = compare(make_incoming(deadline="2026-09-19T00:00:00"), existing)
    assert result.deadline_changed
    assert result.old_deadline == "2026-09-17T00:00:00"
    assert result.new_deadline == "2026-09-19T00:00:00"
    assert result.has_changes


def test_title_changed():
    result = compare(make_incoming(title="New Title"), make_existing())
    assert result.title_changed and result.has_changes


def test_content_hash_change_only():
    """Hash-only change: update, but no new/deadline/title flags."""
    result = compare(make_incoming(content_hash="hash-2"), make_existing())
    assert not result.is_new
    assert not result.deadline_changed
    assert not result.title_changed
    assert result.content_changed


def test_change_result_defaults():
    result = ChangeResult()
    assert not result.has_changes
