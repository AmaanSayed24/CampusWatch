"""Typer CLI commands (design doc §23)."""

from __future__ import annotations

import logging

import typer

from app.database.models import Assignment
from app.main import App
from app.services.deadline_engine import Urgency, compute_urgency, format_remaining, time_remaining

app = typer.Typer(help="CampusWatch — College Portal Assignment Tracking Agent")
logger = logging.getLogger(__name__)

URGENCY_ICONS = {
    Urgency.OVERDUE: "❗",
    Urgency.DUE_TODAY: "🔴",
    Urgency.DUE_WITHIN_24H: "🟠",
    Urgency.DUE_WITHIN_3_DAYS: "🟠",
    Urgency.DUE_WITHIN_7_DAYS: "🟡",
    Urgency.FUTURE: "⚪",
    Urgency.NO_DEADLINE: "➖",
}


def _print_assignments(assignments: list[Assignment], subject_names: dict[int, str]) -> None:
    if not assignments:
        typer.echo("No assignments tracked yet. Run: python run_agent.py sync-now")
        return
    for assignment in assignments:
        urgency = compute_urgency(assignment.deadline)
        remaining = time_remaining(assignment.deadline)
        remaining_text = format_remaining(remaining) if remaining else "no deadline"
        typer.echo(
            f"{URGENCY_ICONS[urgency]} [{subject_names.get(assignment.subject_id, '?')}] "
            f"{assignment.title} — due {assignment.deadline or 'N/A'} ({remaining_text})"
        )


@app.command()
def sync():
    """Start the scheduler (immediate sync, then every CHECK_INTERVAL_MINUTES)."""
    App().run_scheduled()


@app.command(name="sync-now")
def sync_now():
    """Run a single manual sync pass against the portal."""
    App().sync_now()


@app.command()
def assignments():
    """List all tracked assignments."""
    agent = App()
    subjects = {s.id: s.name for s in agent.repository.get_subjects(active_only=False)}
    _print_assignments(agent.repository.get_assignments(), subjects)


@app.command()
def upcoming():
    """List assignments due within the largest reminder window."""
    agent = App()
    windows = agent.settings.reminder_window_deltas()
    window = windows[0] if windows else __import__("datetime").timedelta(days=7)
    subjects = {s.id: s.name for s in agent.repository.get_subjects(active_only=False)}
    _print_assignments(agent.repository.get_due_soon_assignments(window), subjects)


@app.command()
def overdue():
    """List assignments past their deadline."""
    agent = App()
    from datetime import datetime

    active = agent.repository.get_active_with_deadline_before(datetime.now())
    subjects = {s.id: s.name for s in agent.repository.get_subjects(active_only=False)}
    _print_assignments(active, subjects)


@app.command()
def status():
    """Show the result of the last sync run."""
    agent = App()
    run = agent.repository.get_last_sync_run()
    if run is None:
        typer.echo("No sync runs recorded yet.")
        return
    typer.echo(f"Last sync run #{run.id}")
    typer.echo(f"  Status:      {run.status}")
    typer.echo(f"  Started:     {run.started_at}")
    typer.echo(f"  Finished:    {run.finished_at}")
    typer.echo(f"  Subjects:    {run.subjects_checked}")
    typer.echo(f"  Assignments: {run.assignments_found}")
    if run.error_message:
        typer.echo(f"  Error:       {run.error_message}")


@app.command(name="test-notification")
def test_notification():
    """Verify desktop notifications work on this machine."""
    agent = App()
    sent = agent.notifier.send(
        "✅ Test Notification", "CampusWatch is working. Reminders will appear here."
    )
    typer.echo("Notification sent." if sent else "Notification failed — see logs/agent.log.")


if __name__ == "__main__":
    app()
