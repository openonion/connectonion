"""Calendar CLI maps directly to GoogleCalendar; mutations require --yes."""

from typing import Optional
import os
import re
from pathlib import Path
import typer
from rich.console import Console

from ...useful_tools.google_calendar import GoogleCalendar
from .google_errors import google_errors

gcalendar_app = typer.Typer(help="Google Calendar events and Meet links. Bare co gcalendar lists events.", no_args_is_help=False)


@google_errors("co gcalendar list")
def _run(method: str, *args, **kwargs):
    from dotenv import load_dotenv
    from ...project import project_root
    load_dotenv(project_root() / ".env")
    load_dotenv(Path(os.getenv("AGENT_CONFIG_PATH", str(Path.home() / ".co"))) / "keys.env")
    result = getattr(GoogleCalendar(), method)(*args, **kwargs)
    Console().print(result, markup=False, highlight=False)
    first = re.search(r"\bID: ([a-zA-Z0-9_-]+)", result) if method == "list_events" else None
    print(f"Next: co gcalendar read {first[1]}" if first else "Next: co gcalendar list")


def _confirm(yes: bool, operation: str, details: dict):
    if not yes:
        Console().print({"mode": "preview", "operation": operation, **details}, markup=False)
        print(f"No changes made. Next: co gcalendar {operation} --help")
    return yes


@gcalendar_app.callback(invoke_without_command=True)
def calendar(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        _run("list_events")


@gcalendar_app.command("list")
def list_events(days: int = typer.Option(7, "--days", min=1),
                last: int = typer.Option(20, "--last", "-n", min=1, max=250)):
    """List primary-calendar events with stable event IDs (not row numbers)."""
    _run("list_events", days_ahead=days, max_results=last)


@gcalendar_app.command("today")
def today():
    """Read today's events."""
    _run("get_today_events")


@gcalendar_app.command("read")
def read(event_id: str = typer.Argument(..., help="Exact event ID from co gcalendar list")):
    """Read one event by ID."""
    _run("get_event", event_id)


@gcalendar_app.command("meetings")
def meetings(days: int = typer.Option(7, "--days", min=1)):
    """Read upcoming events that have attendees."""
    _run("get_upcoming_meetings", days_ahead=days)


@gcalendar_app.command("free")
def free(date: str = typer.Argument(..., help="YYYY-MM-DD; business hours in UTC"),
         minutes: int = typer.Option(60, "--minutes", min=1, max=480)):
    """Find primary-calendar free slots between 09:00 and 17:00 UTC."""
    _run("find_free_slots", date, duration_minutes=minutes)


@gcalendar_app.command("create")
def create(title: str, start: str, end: str,
           description: Optional[str] = None, attendees: Optional[str] = None,
           location: Optional[str] = None, yes: bool = typer.Option(False, "--yes", help="Create this event; default is a local preview")):
    """Create an event. Use ISO timestamps with offsets; naive times mean UTC."""
    values = dict(title=title, start_time=start, end_time=end, description=description, attendees=attendees, location=location)
    if _confirm(yes, "create", values):
        _run("create_event", **values)


@gcalendar_app.command("meet")
def meet(title: str, start: str, end: str, attendees: str = typer.Option(..., "--attendees", help="Comma-separated emails"),
         description: Optional[str] = None, yes: bool = typer.Option(False, "--yes", help="Create event and Meet conference; default previews")):
    """Create a Calendar event with a Google Meet conference request."""
    values = dict(title=title, start_time=start, end_time=end, attendees=attendees, description=description)
    if _confirm(yes, "meet", values):
        _run("create_meet", **values)


@gcalendar_app.command("update")
def update(event_id: str, title: Optional[str] = None, start: Optional[str] = None,
           end: Optional[str] = None, description: Optional[str] = None,
           attendees: Optional[str] = None, location: Optional[str] = None,
           yes: bool = typer.Option(False, "--yes", help="Apply fields to this exact event; default previews")):
    """Update supplied nonempty fields; other fields are preserved."""
    values = dict(title=title, start_time=start, end_time=end, description=description, attendees=attendees, location=location)
    if not any(values.values()):
        print("No changes supplied. Next: co gcalendar update --help")
        raise typer.Exit(2)
    if _confirm(yes, "update", dict(event_id=event_id, **values)):
        _run("update_event", event_id, **values)


@gcalendar_app.command("delete")
def delete(event_id: str, yes: bool = typer.Option(False, "--yes", help="Delete the exact event; default previews")):
    """Delete an event by stable ID, never by a listing number."""
    if _confirm(yes, "delete", dict(event_id=event_id)):
        _run("delete_event", event_id)
