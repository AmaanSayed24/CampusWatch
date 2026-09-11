"""Typer CLI commands (design doc §23)."""

from __future__ import annotations

import logging

import typer

from app.database.models import Assignment
from app.main import App
from app.parsers.deadline_parser import parse_deadline
from app.services.deadline_engine import Urgency, compute_urgency, format_remaining, time_remaining
from app.utils.dates import format_deadline

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
        pin = " 📌" if assignment.manual_deadline else ""
        subject = subject_names.get(assignment.subject_id, "?")
        typer.echo(
            f"{URGENCY_ICONS[urgency]} #{assignment.id} [{subject}] "
            f"{assignment.title} — due {assignment.deadline or 'N/A'} ({remaining_text}){pin}"
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


@app.command(name="set-deadline")
def set_deadline(
    assignment_id: int = typer.Argument(..., help="Assignment ID (shown by `assignments`)"),
    when: str = typer.Argument(..., help='e.g. "20/09/2026" or "20/09/2026 11:59 PM"'),
):
    """Manually set a deadline for an assignment (survives portal syncs).

    For deadlines the faculty announces outside the portal (in class, on
    WhatsApp, ...). The override drives reminders like any other deadline
    until removed with `clear-deadline`.
    """
    agent = App()
    assignment = agent.repository.get_assignment(assignment_id)
    if assignment is None:
        typer.echo(f"No assignment with id {assignment_id}. Run: run_agent.py assignments")
        raise typer.Exit(1)
    tz = agent.settings.get_timezone()
    parsed = parse_deadline(when, tz)
    if parsed is None:
        typer.echo(f"Could not parse the date: {when!r}")
        raise typer.Exit(1)
    naive = parsed.astimezone(tz).replace(tzinfo=None)
    agent.repository.set_manual_deadline(assignment_id, naive)
    typer.echo(
        f"✅ #{assignment_id} {assignment.title}: "
        f"manual deadline set to {format_deadline(naive)} 📌"
    )


@app.command(name="clear-deadline")
def clear_deadline(
    assignment_id: int = typer.Argument(..., help="Assignment ID (shown by `assignments`)"),
):
    """Remove a manual deadline; the portal's value (often N/A) is restored."""
    agent = App()
    assignment = agent.repository.get_assignment(assignment_id)
    if assignment is None:
        typer.echo(f"No assignment with id {assignment_id}. Run: run_agent.py assignments")
        raise typer.Exit(1)
    agent.repository.set_manual_deadline(assignment_id, None)
    typer.echo(f"✅ #{assignment_id} {assignment.title}: manual deadline cleared")


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
