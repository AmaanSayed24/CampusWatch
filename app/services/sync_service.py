"""Main monitoring workflow (design doc §22)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.automation.assignments import AssignmentScraper
from app.automation.browser import BrowserManager
from app.automation.classroom import ClassroomScraper
from app.automation.login import LoginService
from app.config.settings import Settings
from app.database.repository import Repository
from app.parsers.assignment_parser import normalize_assignment
from app.services.change_detector import compare
from app.services.notification_service import NotificationService
from app.services.pdf_deadline_service import PdfDeadlineService
from app.services.reminder_service import ReminderService

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    subjects_checked: int = 0
    assignments_found: int = 0
    new_assignments: int = 0
    deadline_changes: int = 0
    errors: int = 0


class SyncService:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        browser_manager: BrowserManager,
        login_service: LoginService,
        classroom_scraper: ClassroomScraper,
        assignment_scraper: AssignmentScraper,
        reminder_service: ReminderService,
        notifier: NotificationService,
    ):
        self._settings = settings
        self._repo = repository
        self._browser = browser_manager
        self._login = login_service
        self._classroom = classroom_scraper
        self._assignments = assignment_scraper
        self._reminders = reminder_service
        self._notifier = notifier
        self._pdf_deadlines = PdfDeadlineService(settings, repository)

    # --- Public delegates (used by the scheduler / CLI) ---

    def send_daily_summary(self) -> None:
        """Public delegate for the scheduler's daily-summary job."""
        self._reminders.send_daily_summary()

    async def run_sync(self) -> SyncStats:
        stats = SyncStats()
        run_id = self._repo.start_sync_run()
        logger.info("Starting portal sync (run #%d)", run_id)

        try:
            page = await self._browser.start()
            page = await self._login.ensure_authenticated(page)
            subjects = await self._classroom.discover_subjects(page)
            if not subjects:
                # A transient capture failure must never deactivate subjects
                # discovered on earlier successful runs.
                stats.errors += 1
                self._repo.finish_sync_run(
                    run_id, "FAILED", 0, 0, "No subjects discovered (API payloads not captured)"
                )
                self._notify_sync_issue_once(run_id)
                logger.error(
                    "Subject discovery failed; skipping sync to protect existing data"
                )
                return stats
            self._repo.deactivate_subjects_not_in(
                {s["portal_id"] for s in subjects}
            )

            for subject in subjects:
                try:
                    stored = self._repo.upsert_subject(
                        subject["portal_id"], subject["name"], subject["url"]
                    )
                    stats.subjects_checked += 1

                    raw_assignments = await self._assignments.get_assignments(page, subject)
                    if raw_assignments is None:
                        # Payloads not captured -> state unknown. Never treat
                        # this as "no assignments"; record a real error instead.
                        stats.errors += 1
                        logger.error(
                            "Classwork payloads not captured for %s; subject "
                            "state unknown this run",
                            subject.get("name"),
                        )
                        continue
                    raw_assignments = await self._pdf_deadlines.enrich(page, raw_assignments)
                    for raw in raw_assignments:
                        normalized = normalize_assignment(
                            raw, subject["portal_id"], self._settings.get_timezone()
                        )
                        if normalized is None:
                            continue
                        stats.assignments_found += 1

                        existing = self._repo.get_assignment_by_external_key(
                            normalized["external_key"]
                        )
                        change = compare(normalized, existing)
                        assignment, _ = self._repo.upsert_assignment(
                            normalized, stored.id
                        )

                        if change.is_new:
                            stats.new_assignments += 1
                            logger.info(
                                "New assignment detected: %s — %s",
                                stored.name, normalized["title"],
                            )
                            self._reminders.notify_new(assignment)
                        elif change.deadline_changed:
                            stats.deadline_changes += 1
                            logger.info(
                                "Deadline changed for %s: %s -> %s",
                                normalized["title"], change.old_deadline, change.new_deadline,
                            )
                            self._reminders.notify_deadline_change(
                                assignment, change.old_deadline, change.new_deadline
                            )

                except Exception:
                    stats.errors += 1
                    logger.exception("Failed to process subject %s", subject.get("name"))

            sent = self._reminders.process_due_soon()
            status = "SUCCESS" if stats.errors == 0 else "PARTIAL"
            self._repo.finish_sync_run(
                run_id, status, stats.subjects_checked, stats.assignments_found
            )
            logger.info(
                "Sync completed: %d subjects, %d assignments, %d new, "
                "%d deadline changes, %d reminders",
                stats.subjects_checked, stats.assignments_found,
                stats.new_assignments, stats.deadline_changes, sent,
            )
            return stats

        except Exception as exc:
            stats.errors += 1
            self._repo.finish_sync_run(
                run_id, "FAILED", stats.subjects_checked, stats.assignments_found, str(exc)
            )
            self._notify_sync_issue_once(run_id)
            logger.exception("Sync failed")
            raise
        finally:
            await self._browser.close()

    def _notify_sync_issue_once(self, run_id: int) -> None:
        """Send the §15 sync_issue alert when scanning stops working, but only
        on the transition into failure — never repeatedly every interval (§14:
        never repeat the same message)."""
        previous = self._repo.get_previous_sync_run(run_id)
        if previous is not None and previous.status == "FAILED":
            return  # the student was already alerted on the first failure
        try:
            self._notifier.sync_issue(datetime.now().strftime("%d %B %Y, %I:%M %p"))
        except Exception:
            logger.exception("Failed to send the sync-issue notification")
