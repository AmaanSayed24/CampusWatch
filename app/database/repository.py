"""Repository layer: all database operations (design doc §10)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Assignment, Notification, PdfDeadlineCache, Subject, SyncRun
from app.utils import hashing

logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    # --- Subjects ---

    def upsert_subject(self, portal_id: str, name: str, url: str | None = None) -> Subject:
        with self._session_factory() as session:
            subject = session.scalar(select(Subject).where(Subject.portal_id == portal_id))
            if subject is None:
                subject = Subject(portal_id=portal_id, name=name, url=url, active=True)
                session.add(subject)
                logger.info("New subject recorded: %s", name)
            else:
                subject.name = name
                subject.url = url or subject.url
                subject.active = True
            session.commit()
            session.refresh(subject)
            return subject

    def get_subjects(self, active_only: bool = True) -> list[Subject]:
        with self._session_factory() as session:
            stmt = select(Subject)
            if active_only:
                stmt = stmt.where(Subject.active.is_(True))
            return list(session.scalars(stmt.order_by(Subject.name)).all())

    def get_subject_by_portal_id(self, portal_id: str) -> Subject | None:
        with self._session_factory() as session:
            return session.scalar(select(Subject).where(Subject.portal_id == portal_id))

    def deactivate_subjects_not_in(self, portal_ids: set[str]) -> int:
        """Mark subjects no longer discovered on the portal as inactive."""
        with self._session_factory() as session:
            subjects = list(session.scalars(select(Subject)).all())
            changed = 0
            for subject in subjects:
                if subject.portal_id not in portal_ids and subject.active:
                    subject.active = False
                    changed += 1
                    logger.info("Subject no longer on portal, deactivated: %s", subject.name)
            session.commit()
            return changed

    # --- Assignments ---

    def get_assignment_by_external_key(self, external_key: str) -> Assignment | None:
        with self._session_factory() as session:
            return session.scalar(
                select(Assignment).where(Assignment.external_key == external_key)
            )

    def upsert_assignment(self, data: dict, subject_id: int) -> tuple[Assignment, bool]:
        """Insert or update an assignment. Returns (assignment, is_new)."""
        with self._session_factory() as session:
            assignment = session.scalar(
                select(Assignment).where(Assignment.external_key == data["external_key"])
            )
            is_new = assignment is None
            if is_new:
                assignment = Assignment(
                    external_key=data["external_key"], subject_id=subject_id
                )
                session.add(assignment)
            assignment.subject_id = subject_id
            assignment.portal_id = data.get("portal_id")
            assignment.title = data["title"]
            assignment.description = data.get("description")
            assignment.assigned_at = data.get("assigned_at")
            assignment.deadline = data.get("deadline")
            assignment.status = data.get("status", "PENDING")
            assignment.source_url = data.get("source_url")
            assignment.content_hash = data.get("content_hash")
            assignment.last_seen_at = datetime.now()
            session.commit()
            session.refresh(assignment)
            return assignment, is_new

    def get_assignments(self) -> list[Assignment]:
        with self._session_factory() as session:
            return list(session.scalars(select(Assignment).order_by(Assignment.deadline)).all())

    def get_due_soon_assignments(self, within: timedelta) -> list[Assignment]:
        horizon = datetime.now() + within
        return self.get_active_with_deadline_before(horizon)

    def get_active_with_deadline_before(self, upper_bound: datetime) -> list[Assignment]:
        """PENDING assignments whose deadline is set and before upper_bound."""
        with self._session_factory() as session:
            stmt = (
                select(Assignment)
                .where(Assignment.deadline.is_not(None))
                .where(Assignment.status.in_(["PENDING", "UNKNOWN", "OVERDUE"]))
                .where(Assignment.deadline <= upper_bound)
            )
            return list(session.scalars(stmt).all())

    def mark_assignment_status(self, assignment_id: int, status: str) -> None:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment:
                assignment.status = status
                session.commit()

    # --- Notifications ---

    def has_notification(self, assignment_id: int, notification_type: str) -> bool:
        with self._session_factory() as session:
            found = session.scalar(
                select(Notification).where(
                    Notification.assignment_id == assignment_id,
                    Notification.notification_type == notification_type,
                )
            )
            return found is not None

    def record_notification(
        self, assignment_id: int, notification_type: str, channel: str = "desktop"
    ) -> None:
        with self._session_factory() as session:
            session.add(
                Notification(
                    assignment_id=assignment_id,
                    notification_type=notification_type,
                    channel=channel,
                )
            )
            session.commit()

    # --- Sync runs ---

    def start_sync_run(self) -> int:
        with self._session_factory() as session:
            # Local time explicitly, because SQLite's func.now() default
            # writes UTC while finish_sync_run records local time.
            run = SyncRun(status="RUNNING", started_at=datetime.now())
            session.add(run)
            session.commit()
            return run.id

    def finish_sync_run(
        self,
        run_id: int,
        status: str,
        subjects_checked: int = 0,
        assignments_found: int = 0,
        error_message: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            run = session.get(SyncRun, run_id)
            if run:
                run.finished_at = datetime.now()
                run.status = status
                run.subjects_checked = subjects_checked
                run.assignments_found = assignments_found
                run.error_message = error_message
                session.commit()

    def get_last_sync_run(self) -> SyncRun | None:
        with self._session_factory() as session:
            return session.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))

    def get_previous_sync_run(self, current_run_id: int) -> SyncRun | None:
        """The sync run before `current_run_id`, for failure-transition checks."""
        with self._session_factory() as session:
            return session.scalar(
                select(SyncRun)
                .where(SyncRun.id < current_run_id)
                .order_by(SyncRun.id.desc())
                .limit(1)
            )

    # --- PDF deadline extraction cache ---

    def get_pdf_deadline(self, url: str) -> PdfDeadlineCache | None:
        with self._session_factory() as session:
            return session.get(PdfDeadlineCache, hashing.sha256_text(url))

    def save_pdf_deadline(
        self,
        url: str,
        deadline: datetime | None,
        confidence: float = 0.0,
        snippet: str | None = None,
    ) -> None:
        """Upsert an extraction result (deadline None = nothing reliable found)."""
        with self._session_factory() as session:
            url_hash = hashing.sha256_text(url)
            row = session.get(PdfDeadlineCache, url_hash)
            if row is None:
                row = PdfDeadlineCache(url_hash=url_hash, url=url)
                session.add(row)
            row.deadline = deadline
            row.confidence = confidence
            row.snippet = snippet
            session.commit()

