"""Application configuration loaded from the local .env file.

Credentials and endpoints are never hard-coded (design doc §18).
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Portal ---
    portal_url: str = "https://elearning.paruluniversity.ac.in/students/dashboard"
    portal_username: str = ""
    portal_password: str = ""

    # --- Browser ---
    browser_headless: bool = False
    browser_profile_dir: Path = PROJECT_ROOT / "data" / "browser-profile"
    navigation_timeout_ms: int = 30_000
    manual_login_timeout_seconds: int = 300

    # --- Scheduling ---
    check_interval_minutes: int = 60

    # --- Reminders ---
    reminder_windows: str = "7d,3d,24h,3h"
    daily_summary_time: str = "08:00"
    notify_overdue: bool = False

    # --- Notifications ---
    notification_enabled: bool = True

    # --- Storage / logging ---
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'portal.db').as_posix()}"
    log_level: str = "INFO"
    log_file: Path = PROJECT_ROOT / "logs" / "agent.log"
    screenshots_dir: Path = PROJECT_ROOT / "screenshots"
    timezone: str = "Asia/Kolkata"

    def get_timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def reminder_window_deltas(self) -> list[timedelta]:
        """Parse '7d,3d,24h,3h' into a list of timedeltas, largest first."""
        deltas: set[timedelta] = set()
        for token in self.reminder_windows.split(","):
            token = token.strip().lower()
            if not token:
                continue
            unit, value = token[-1], token[:-1]
            if unit == "d":
                deltas.add(timedelta(days=int(value)))
            elif unit == "h":
                deltas.add(timedelta(hours=int(value)))
            elif unit == "m":
                deltas.add(timedelta(minutes=int(value)))
        return sorted(deltas, reverse=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
