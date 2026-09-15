"""Desktop GUI for CampusWatch — a zero-dependency Tkinter front-end."""

from __future__ import annotations

from app.gui import theme
from app.gui.sync_worker import SyncEvent, SyncWorker


def run_gui(settings=None) -> int:
    """Launch the desktop dashboard; blocks until the window closes."""
    from app.gui.app_window import GuiApp  # deferred: keep Tk out of import time

    window = GuiApp(settings=settings)
    window.mainloop()
    return 0


__all__ = ["SyncEvent", "SyncWorker", "run_gui", "theme"]
