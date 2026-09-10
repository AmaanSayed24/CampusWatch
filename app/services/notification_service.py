"""Notification service: desktop notifications via plyer (§15 message formats)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.config.settings import Settings
from app.services.deadline_engine import format_remaining
from app.utils.dates import format_deadline

logger = logging.getLogger(__name__)

APP_NAME = "CampusWatch"


class NotificationService:
    def __init__(self, settings: Settings):
        self._settings = settings

    def send(self, title: str, message: str) -> bool:
        if not self._settings.notification_enabled:
            logger.info("Notifications disabled; would show: %s", title)
            return False
        try:
            from plyer import notification

            notification.notify(
                title=f"{APP_NAME}: {title}",
                message=message,
                app_name=APP_NAME,
                timeout=10,
            )
            logger.info("Desktop notification sent: %s", title)
            return True
        except Exception:
            # plyer can fail on some Windows setups; never lose the message.
            logger.exception("Desktop notification failed; logging instead")
            logger.warning("NOTIFICATION | %s | %s", title, message)
            return False

    # --- Message builders (§15) ---

    def new_assignment(
        self, subject_name: str, assignment_title: str, deadline, url: str | None
    ) -> bool:
        lines = [
            f"Subject: {subject_name}",
            f"Assignment: {assignment_title}",
            f"Due: {format_deadline(deadline)}",
        ]
        if url:
            lines.append(f"Open portal: {url}")
        return self.send("📚 New Assignment", "\n".join(lines))

    def deadline_changed(
        self, subject_name: str, assignment_title: str, old_deadline, new_deadline
    ) -> bool:
        return self.send(
            "🔄 Deadline Updated",
            "\n".join(
                [
                    f"{subject_name} — {assignment_title}",
                    f"Old: {format_deadline(old_deadline)}",
                    f"New: {format_deadline(new_deadline)}",
                ]
            ),
        )

    def reminder(
        self, subject_name: str, assignment_title: str, deadline, remaining: timedelta
    ) -> bool:
        now = datetime.now(deadline.tzinfo) if deadline and deadline.tzinfo else datetime.now()
        if deadline is not None and deadline.date() == now.date():
            return self.send(
                "🚨 Due Today",
                "\n".join(
                    [
                        f"{subject_name} — {assignment_title}",
                        "Deadline: Today, "
                        f"{deadline.strftime('%I:%M %p').lstrip('0') if deadline else 'unknown'}",
                    ]
                ),
            )
        return self.send(
            "⏰ Assignment Reminder",
            "\n".join(
                [
                    f"{subject_name} — {assignment_title}",
                    f"Due in {format_remaining(remaining)}.",
                    f"Deadline: {format_deadline(deadline)}",
                ]
            ),
        )

    def overdue(self, subject_name: str, assignment_title: str, deadline) -> bool:
        return self.send(
            "❗ Overdue Assignment",
            f"{subject_name} — {assignment_title}\nDeadline was: {format_deadline(deadline)}",
        )

    def sync_issue(self, when: str) -> None:
        return self.send(
            "⚠️ College portal sync issue",
            (
                f"The portal could not be scanned successfully at {when}.\n"
                "The browser session may have expired.\n"
                "Please run: python run_agent.py sync-now"
            ),
        )

    def daily_summary(self, text: str) -> None:
        return self.send("📋 College Daily Summary", text)
