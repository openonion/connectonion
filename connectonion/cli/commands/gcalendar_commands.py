"""Calendar CLI maps directly to GoogleCalendar; mutations require --yes."""

from typing import Optional
import os
import re
from pathlib import Path
import typer
from rich.console import Console

from .google_errors import google_errors
from .command_tips import print_tip

gcalendar_app = typer.Typer(
    help="Google Calendar events and Meet links. Bare co gcalendar lists events (Read-only); "
         "create, meet, update and delete only preview until --yes.",
    epilog="Example:  co gcalendar list --days 14  |  co gcalendar read <event-id>",
    no_args_is_help=False)

TIME_HELP = "ISO time, e.g. 2026-10-01T10:00:00+10:00 or \"2026-10-01 10:00\"; no offset means UTC"
EVENT_ID_HELP = "Exact event ID from co gcalendar list"
ATTENDEES_HELP = "Comma-separated emails; Google emails each one an invitation"


def _client():
    from ...useful_tools.google_calendar import GoogleCalendar
    try:
        return GoogleCalendar()
    except ValueError as error:
        from ...provider_credentials import ProviderCredentialError
        if isinstance(error, ProviderCredentialError):
            raise
        print_tip("Saved Google grant lacks Calendar access. Next: co auth google")
        raise typer.Exit(1) from None


@google_errors("co gcalendar list")
def _run(method: str, *args, **kwargs):
    from ...environment import load_environment
    load_environment()
    result = getattr(_client(), method)(*args, **kwargs)
    Console().print(result, markup=False, highlight=False)
    first = re.search(r"\bID: ([a-zA-Z0-9_-]+)", result) if method == "list_events" else None
    print_tip(f"Next: co gcalendar read {first[1]}" if first else "Next: co gcalendar list")


def _confirm(yes: bool, operation: str, details: dict):
    if not yes:
        Console().print({"mode": "preview", "operation": operation, **details}, markup=False)
        print_tip(f"No changes made. Next: co gcalendar {operation} --help")
    return yes


@gcalendar_app.callback(invoke_without_command=True)
def calendar(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        _run("list_events")


@gcalendar_app.command("list", epilog="Example:  co gcalendar list --days 14 -n 50")
def list_events(days: int = typer.Option(7, "--days", min=1, help="How many days ahead to include, starting now"),
                last: int = typer.Option(20, "--last", "-n", min=1, max=250, help="Maximum events to show")):
    """List primary-calendar events with stable event IDs (not row numbers). Read-only."""
    _run("list_events", days_ahead=days, max_results=last)


@gcalendar_app.command("today", epilog="Example:  co gcalendar today")
def today():
    """Read today's events. Read-only."""
    _run("get_today_events")


@gcalendar_app.command("read", epilog="Example:  co gcalendar read 7nc7u7q2b09p6g8q3k1r3b1m40")
def read(event_id: str = typer.Argument(..., help="Exact event ID from co gcalendar list")):
    """Read one event by ID. Read-only."""
    _run("get_event", event_id)


@gcalendar_app.command("meetings", epilog="Example:  co gcalendar meetings --days 3")
def meetings(days: int = typer.Option(7, "--days", min=1, help="How many days ahead to include, starting now")):
    """Read upcoming events that have attendees. Read-only."""
    _run("get_upcoming_meetings", days_ahead=days)


@gcalendar_app.command("free", epilog="Example:  co gcalendar free 2026-10-01 --minutes 30")
def free(date: str = typer.Argument(..., help="YYYY-MM-DD; business hours in UTC"),
         minutes: int = typer.Option(60, "--minutes", min=1, max=480, help="Length of free time to find, in minutes")):
    """Find primary-calendar free slots between 09:00 and 17:00 UTC. Read-only."""
    _run("find_free_slots", date, duration_minutes=minutes)


@gcalendar_app.command("create", epilog=(
    "Example:  co gcalendar create \"Team sync\" 2026-10-01T10:00:00+10:00 "
    "2026-10-01T10:30:00+10:00 --attendees you@example.com --yes"))
def create(title: str = typer.Argument(..., help="Event title"),
           start: str = typer.Argument(..., help=TIME_HELP),
           end: str = typer.Argument(..., help=TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description", help="Event description, plain text"),
           attendees: Optional[str] = typer.Option(None, "--attendees", help=ATTENDEES_HELP),
           location: Optional[str] = typer.Option(None, "--location", help="Location text shown on the event"),
           yes: bool = typer.Option(False, "--yes", help="Create this event; default is a local preview")):
    """Create an event. Creates it only with --yes; otherwise previews.

    Use ISO timestamps with offsets; naive times mean UTC. With --attendees,
    Google emails each attendee an invitation.
    """
    values = dict(title=title, start_time=start, end_time=end, description=description, attendees=attendees, location=location)
    if _confirm(yes, "create", values):
        _run("create_event", **values)


@gcalendar_app.command("meet", epilog=(
    "Example:  co gcalendar meet \"Intro call\" 2026-10-01T15:00:00+10:00 "
    "2026-10-01T15:30:00+10:00 --attendees you@example.com --yes"))
def meet(title: str = typer.Argument(..., help="Meeting title"),
         start: str = typer.Argument(..., help=TIME_HELP),
         end: str = typer.Argument(..., help=TIME_HELP),
         attendees: str = typer.Option(..., "--attendees", help="Comma-separated emails"),
         description: Optional[str] = typer.Option(None, "--description", help="Event description, plain text"),
         yes: bool = typer.Option(False, "--yes", help="Create event and Meet conference; default previews")):
    """Create a Calendar event with a Google Meet conference request. Creates it only with --yes; otherwise previews.

    Google emails each attendee an invitation.
    """
    values = dict(title=title, start_time=start, end_time=end, attendees=attendees, description=description)
    if _confirm(yes, "meet", values):
        _run("create_meet", **values)


@gcalendar_app.command("update", epilog=(
    "Example:  co gcalendar update 7nc7u7q2b09p6g8q3k1r3b1m40 --title \"Team sync (moved)\" "
    "--start 2026-10-01T11:00:00+10:00 --end 2026-10-01T11:30:00+10:00 --yes"))
def update(event_id: str = typer.Argument(..., help=EVENT_ID_HELP),
           title: Optional[str] = typer.Option(None, "--title", help="New event title"),
           start: Optional[str] = typer.Option(None, "--start", help="New start; " + TIME_HELP),
           end: Optional[str] = typer.Option(None, "--end", help="New end; " + TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description", help="New description, plain text"),
           attendees: Optional[str] = typer.Option(None, "--attendees",
                                                   help="Comma-separated emails; replaces the attendee list, keeping replies of those still on it"),
           location: Optional[str] = typer.Option(None, "--location", help="New location text"),
           yes: bool = typer.Option(False, "--yes", help="Apply fields to this exact event; default previews")):
    """Change an existing event's title, time, description, attendees or location; fields you leave out stay as they are. Changes the event only with --yes; otherwise previews.

    Google emails the event's attendees about the change.
    """
    values = dict(title=title, start_time=start, end_time=end, description=description, attendees=attendees, location=location)
    if not any(values.values()):
        print_tip("No changes supplied. Next: co gcalendar update --help")
        raise typer.Exit(2)
    if _confirm(yes, "update", dict(event_id=event_id, **values)):
        _run("update_event", event_id, **values)


@gcalendar_app.command("delete", epilog="Example:  co gcalendar delete 7nc7u7q2b09p6g8q3k1r3b1m40  |  "
                                         "co gcalendar delete 7nc7u7q2b09p6g8q3k1r3b1m40 --yes")
def delete(event_id: str = typer.Argument(..., help=EVENT_ID_HELP), yes: bool = typer.Option(False, "--yes", help="Delete the exact event; default previews")):
    """Delete an event by stable ID, never by a listing number. Deletes it only with --yes; otherwise previews.

    Google emails the event's attendees a cancellation.
    """
    if _confirm(yes, "delete", dict(event_id=event_id)):
        _run("delete_event", event_id)
