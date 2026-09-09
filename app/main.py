"""Application composition root: wiring and orchestration (§10)."""

from __future__ import annotations

import asyncio

from app.automation.assignments import AssignmentScraper
from app.automation.browser import BrowserManager
from app.automation.classroom import ClassroomScraper
from app.automation.login import LoginService
from app.config.settings import Settings, get_settings
from app.database.connection import init_db
from app.database.repository import Repository
from app.scheduler.scheduler import AgentScheduler
from app.services.notification_service import NotificationService
from app.services.reminder_service import ReminderService
from app.services.sync_service import SyncService
from app.utils.logging import setup_logging


class App:
    """Builds and wires every layer of the agent."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        setup_logging(self.settings)

        session_factory = init_db(self.settings)
        self.repository = Repository(session_factory)
        self.notifier = NotificationService(self.settings)
        self.reminder_service = ReminderService(
            self.settings, self.repository, self.notifier, session_factory
        )

        self.browser_manager = BrowserManager(self.settings)
        self.login_service = LoginService(self.settings, self.browser_manager)
        self.classroom_scraper = ClassroomScraper(self.settings)
        self.assignment_scraper = AssignmentScraper(self.settings)

        self.sync_service = SyncService(
            settings=self.settings,
            repository=self.repository,
            browser_manager=self.browser_manager,
            login_service=self.login_service,
            classroom_scraper=self.classroom_scraper,
            assignment_scraper=self.assignment_scraper,
            reminder_service=self.reminder_service,
        )

    # --- Commands ---

    def sync_now(self) -> None:
        asyncio.run(self.sync_service.run_sync())

    def run_scheduled(self) -> None:
        scheduler = AgentScheduler(
            self.sync_service,
            self.settings.check_interval_minutes,
            self.settings.daily_summary_time,
        )
        scheduler.start()
