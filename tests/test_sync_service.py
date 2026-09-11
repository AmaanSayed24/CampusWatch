"""Tests for the cross-process sync guard (two instances must not collide)."""

from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.sync_service import SyncService

TZ = ZoneInfo("Asia/Kolkata")


def make_service(tmp_path: Path) -> SyncService:
    settings_stub = type(
        "S",
        (),
        {"browser_profile_dir": tmp_path / "profile", "timezone": "Asia/Kolkata"},
    )()
    settings_stub.get_timezone = lambda: TZ
    dummy = lambda name: type(name, (), {})()  # noqa: E731
    return SyncService(
        settings=settings_stub,
        repository=dummy("R"),
        browser_manager=dummy("B"),
        login_service=dummy("L"),
        classroom_scraper=dummy("C"),
        assignment_scraper=dummy("A"),
        reminder_service=dummy("RM"),
        notifier=dummy("N"),
    )


def test_lock_is_exclusive_then_releasable(tmp_path: Path):
    service = make_service(tmp_path)
    assert service._acquire_lock() is True
    # A second concurrent instance must be refused.
    second = make_service(tmp_path)
    assert second._acquire_lock() is False
    # After release the lock is free again.
    service._release_lock()
    assert second._acquire_lock() is True
    second._release_lock()
