"""Background sync worker for the GUI.

Runs ``SyncService.run_sync()`` in a daemon thread and posts discrete events to
a queue the Tk main loop polls.  The UI thread never touches async code, and
sync runs never block the window.  When another CampusWatch process already
holds the cross-process lock file, the pass is reported as a ``skipped`` event
(no DB activity happens, so the SyncRun id does not advance).
"""

from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass

from app.main import App


@dataclass
class SyncEvent:
    kind: str  # started | finished | failed | skipped
    message: str = ""
    run_id: int | None = None
    stats: object | None = None


class SyncWorker:
    def __init__(self, app: App) -> None:
        self._app = app
        self._events: "queue.Queue[SyncEvent]" = queue.Queue()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Kick off a sync pass; returns False if one is already running."""
        if self.busy:
            return False
        self._thread = threading.Thread(
            target=self._run, name="campuswatch-gui-sync", daemon=True
        )
        self._thread.start()
        return True

    def drain(self, limit: int = 50) -> list[SyncEvent]:
        events: list[SyncEvent] = []
        try:
            while len(events) < limit:
                events.append(self._events.get_nowait())
        except queue.Empty:
            pass
        return events

    # --- runs on the worker thread ---------------------------------------

    def _run(self) -> None:
        repo = self._app.repository
        previous = repo.get_last_sync_run()
        previous_id = previous.id if previous is not None else 0
        self._events.put(SyncEvent(kind="started", message="Portal scan started"))
        stats = None
        try:
            stats = asyncio.run(self._app.sync_service.run_sync())
            current = repo.get_last_sync_run()
            current_id = current.id if current is not None else 0
            if current_id == previous_id:
                self._events.put(
                    SyncEvent(
                        kind="skipped",
                        message=(
                            "Another CampusWatch instance is already scanning; "
                            "this pass was skipped."
                        ),
                        run_id=current_id,
                        stats=stats,
                    )
                )
                return
            status = current.status if current is not None else "SUCCESS"
            self._events.put(
                SyncEvent(
                    kind="finished",
                    message=(
                        f"Scan #{current_id} {status.lower()}: "
                        f"{current.subjects_checked} subject(s), "
                        f"{current.assignments_found} assignment(s) found"
                    ),
                    run_id=current_id,
                    stats=stats,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self._events.put(
                SyncEvent(kind="failed", message=f"Scan failed: {exc}", stats=stats)
            )
