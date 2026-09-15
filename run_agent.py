"""CampusWatch entry point.

Usage:
    python run_agent.py sync-now
    python run_agent.py sync          (scheduler: immediate pass, then periodic)
    python run_agent.py assignments
    python run_agent.py upcoming
    python run_agent.py overdue
    python run_agent.py status
    python run_agent.py test-notification
    python run_agent.py gui           (desktop dashboard - professional GUI)
"""

import sys

from app.cli.commands import app


def _ensure_utf8_console() -> None:
    """Windows defaults to the cp1252 codec for piped stdout, which cannot
    encode the emoji used by the CLI. Force UTF-8 so output works both on the
    terminal and when piped (e.g. `run_agent.py assignments | ...`)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _ensure_utf8_console()
    app()
