"""Reminder service: decides when to notify and prevents duplicates (§14)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.database.models import Assignment, Subject
from app.database.repository import Repository
from app.services.deadline_engine import time_remaining
from app.services.notification_service import NotificationService
from app.utils.dates import format_deadline

logger = logging.getLogger(__name__)


class ReminderService:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        notifier: NotificationService,
        session_factory: sessionmaker[Session] | None = None,
    ):
        self._settings = settings
        self._repo = repository
        self._notifier = notifier
        self._session_factory = session_factory  # used to read subject names

    def _subject_name(self, assignment: Assignment) -> str:
        if self._session_factory is None:
            return ""
        with self._session_factory() as session:
            subject = session.get(Subject, assignment.subject_id)
            return subject.name if subject else ""

    def _window_type(self, delta: timedelta) -> str:
        total_minutes = int(delta.total_seconds() // 60)
        return f"REMINDER_{total_minutes}M"

    def notify_new(self, assignment: Assignment) -> None:
        """New assignment discovered -> notify immediately (once ever)."""
        if self._repo.has_notification(assignment.id, "NEW_ASSIGNMENT"):
            return
        subject_name = self._subject_name(assignment)
        sent = self._notifier.new_assignment(
            subject_name, assignment.title, assignment.deadline, assignment.source_url
        )
        if sent:
            self._repo.record_notification(assignment.id, "NEW_ASSIGNMENT")

    def notify_deadline_change(self, assignment: Assignment, old_deadline, new_deadline) -> None:
        # Dedupe per new value: if the faculty changes the deadline again, the
        # student should be notified again (§14: never repeat the same message).
        notification_type = "DEADLINE_CHANGED"
        if new_deadline is not None:
            notification_type += ":" + new_deadline.strftime("%Y%m%d%H%M")
        if self._repo.has_notification(assignment.id, notification_type):
            return
        subject_name = self._subject_name(assignment)
        sent = self._notifier.deadline_changed(
            subject_name, assignment.title, old_deadline, new_deadline
        )
        if sent:
            self._repo.record_notification(assignment.id, notification_type)

    def process_due_soon(self) -> int:
        """Check every active assignment and send any windowed reminders due.

        Sends at most one reminder per assignment per run: the smallest
        configured window that has been reached and not yet sent (§14).
        """
        windows = self._settings.reminder_window_deltas()
        if not windows:
            return 0

        max_window = windows[0]
        from datetime import datetime
        tz = self._settings.get_timezone()
        # Deadlines are stored as naive wall-time in the configured timezone.
        current = datetime.now(tz).replace(tzinfo=None)

        candidates = self._repo.get_active_with_deadline_before(current + max_window)
        sent_count = 0

        for assignment in candidates:
            remaining = time_remaining(assignment.deadline, current)
            if remaining is None:
                continue

            subject_name = self._subject_name(assignment)

            if remaining < timedelta(0):
                if self._settings.notify_overdue and not self._repo.has_notification(
                    assignment.id, "OVERDUE"
                ):
                    if self._notifier.overdue(subject_name, assignment.title, assignment.deadline):
                        self._repo.record_notification(assignment.id, "OVERDUE")
                        sent_count += 1
                continue

            # Smallest configured window that has been reached (§14). If its
            # reminder was already sent, stop — never fall through to a larger
            # (older-news) window on a later run.
            reached = [w for w in windows if remaining <= w]
            if not reached:
                continue
            window = reached[-1]  # smallest, as `windows` is largest-first
            notification_type = self._window_type(window)
            if self._repo.has_notification(assignment.id, notification_type):
                continue
            if self._notifier.reminder(
                subject_name, assignment.title, assignment.deadline, remaining
            ):
                self._repo.record_notification(assignment.id, notification_type)
                sent_count += 1

        return sent_count

    def build_assignment_summary(self) -> str:
        """Full post-scan dashboard text (§ new 10-minute scan flow).

        Every active assignment is classified into exactly one bucket:
        OVERDUE (deadline passed), UPCOMING (future deadline) or NO DEADLINE.
        Overdue assignments are retained, never filtered out. Already
        SUBMITTED work is excluded from the buckets but reported in the
        header so the summary stays complete.
        """
        from datetime import datetime

        tz = self._settings.get_timezone()
        # Deadlines are stored as naive wall-time in the configured timezone.
        now = datetime.now(tz).replace(tzinfo=None)

        all_assignments = self._repo.get_assignments()
        outstanding = [a for a in all_assignments if a.status != "SUBMITTED"]
        submitted = [a for a in all_assignments if a.status == "SUBMITTED"]

        overdue: list[Assignment] = []
        upcoming: list[Assignment] = []
        no_deadline: list[Assignment] = []
        for assignment in outstanding:
            if assignment.deadline is None:
                no_deadline.append(assignment)
            elif assignment.deadline < now:
                overdue.append(assignment)
            else:
                upcoming.append(assignment)
        overdue.sort(key=lambda a: a.deadline)
        upcoming.sort(key=lambda a: a.deadline)

        lines = [
            f"COLLEGE ASSIGNMENT SUMMARY — {len(outstanding)} outstanding "
            f"({len(overdue)} overdue, {len(upcoming)} upcoming, "
            f"{len(no_deadline)} no deadline), {len(submitted)} submitted",
        ]

        for label, group, icon in (
            ("❗ OVERDUE", overdue, "❗"),
            ("🟠 UPCOMING", upcoming, "🟠"),
            ("➖ NO DEADLINE", no_deadline, "➖"),
        ):
            lines.append("")
            lines.append(f"{label} ({len(group)})")
            for assignment in group:
                subject_name = self._subject_name(assignment)
                if assignment.deadline is None:
                    lines.append(f"{icon} {subject_name} — {assignment.title}")
                else:
                    lines.append(
                        f"{icon} {subject_name} — {assignment.title} — "
                        f"due {format_deadline(assignment.deadline)}"
                    )

        return "\n".join(lines)

    def build_daily_summary(self) -> str:
        from datetime import datetime

        tz = self._settings.get_timezone()
        # Deadlines are stored as naive wall-time in the configured timezone.
        now = datetime.now(tz).replace(tzinfo=None)
        windows = self._settings.reminder_window_deltas()

        def within(delta: timedelta) -> list[Assignment]:
            return self._repo.get_active_with_deadline_before(now + delta)

        due_today = [a for a in within(timedelta(days=1)) if a.deadline.date() == now.date()]
        counts = {w: len(within(w)) for w in windows}

        lines = ["COLLEGE DAILY SUMMARY", ""]
        for label, count in (
            ("🔴 Due today", len(due_today)),
            *[("🟠 Due within %s" % _human(w), c) for w, c in sorted(counts.items())],
        ):
            lines.append(f"{label}: {count}")

        if due_today:
            lines.append("")
            lines.append("Today's tasks")
            for index, assignment in enumerate(due_today, start=1):
                lines.append(f"{index}. {self._subject_name(assignment)} — {assignment.title}")

        return "\n".join(lines)

    def send_daily_summary(self) -> None:
        self._notifier.daily_summary(self.build_daily_summary())


def _human(delta: timedelta) -> str:
    hours = int(delta.total_seconds() // 3600)
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''}"
    return f"{hours} hour{'s' if hours != 1 else ''}"
