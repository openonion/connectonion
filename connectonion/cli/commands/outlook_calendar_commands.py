"""`co outlook calendar`: the terminal surface of MicrosoftCalendar (#816).

Outlook is one product with three panes — Mail, Calendar, People — so the
calendar sits under `co outlook` beside `contact`, not as a fourth top-level
name an agent would have to guess. Each leaf maps to exactly one
MicrosoftCalendar method, mirroring `co gcalendar` leaf for leaf (`teams`
where Google has `meet`). Reads run at once; every write previews by default
and the preview prints the complete command that performs it, so the agent's
next call is a copy, not a reconstruction.
"""

from typing import Optional
import re
import shlex

import typer
from rich.console import Console

from .microsoft_errors import microsoft_errors
from .command_tips import print_tip
from ..typer_groups import _OneSuggestion

outlook_calendar_app = typer.Typer(
    cls=_OneSuggestion,  # a typo is answered once, like every other group
    help="Your Outlook calendar: events, Teams meetings, free slots. Bare 'co outlook calendar' lists events.",
    no_args_is_help=False,
)

TIME_HELP = "ISO time; an offset is converted to UTC, a naive time means UTC (2026-09-10T10:00:00Z)"


def _client():
    """The Calendars scope check shares its words and next command with mail and contacts."""
    from .outlook_commands import _microsoft_record
    _microsoft_record("Calendars")
    from ...useful_tools.microsoft_calendar import MicrosoftCalendar
    return MicrosoftCalendar()


@microsoft_errors("co outlook calendar list")
def _run(method: str, *args, **kwargs):
    result = getattr(_client(), method)(*args, **kwargs)
    Console().print(result, markup=False, highlight=False)
    first = re.search(r"\bID: (\S+)", result) if method == "list_events" else None
    print_tip(f"Next: co outlook calendar read {first[1]}" if first else "Next: co outlook calendar list")


def _performing_command(operation: str, positional: list, options: dict) -> str:
    parts = ["co", "outlook", "calendar", operation, *(shlex.quote(str(value)) for value in positional)]
    for name, value in options.items():
        if value:
            parts += [f"--{name}", shlex.quote(str(value))]
    return " ".join(parts + ["--yes"])


def _confirm(yes: bool, operation: str, positional: list, options: dict) -> bool:
    if not yes:
        Console().print({"mode": "preview", "operation": operation,
                         **{f"arg{i}": v for i, v in enumerate(positional, 1)},
                         **{k: v for k, v in options.items() if v}}, markup=False)
        Console().print("No changes made.", markup=False)
        print_tip(f"Next: {_performing_command(operation, positional, options)}")
    return yes


@outlook_calendar_app.callback(invoke_without_command=True)
def calendar(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        _run("list_events")


@outlook_calendar_app.command("list")
def list_events(days: int = typer.Option(7, "--days", min=1),
                last: int = typer.Option(20, "--last", "-n", min=1, max=250)):
    """List upcoming events with stable event IDs (not row numbers)."""
    _run("list_events", days_ahead=days, max_results=last)


@outlook_calendar_app.command("today")
def today():
    """Read today's events."""
    _run("get_today_events")


@outlook_calendar_app.command("read")
def read(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list")):
    """Read one event by ID."""
    _run("get_event", event_id)


@outlook_calendar_app.command("meetings")
def meetings(days: int = typer.Option(7, "--days", min=1)):
    """Read upcoming events that have attendees."""
    _run("get_upcoming_meetings", days_ahead=days)


@outlook_calendar_app.command("free")
def free(date: str = typer.Argument(..., help="YYYY-MM-DD; business hours in UTC"),
         minutes: int = typer.Option(60, "--minutes", min=1, max=480)):
    """Find free slots between 09:00 and 17:00 UTC on one day."""
    _run("find_free_slots", date, duration_minutes=minutes)


@outlook_calendar_app.command("create")
def create(title: str = typer.Argument(..., help="Event title"),
           start: str = typer.Argument(..., help=TIME_HELP),
           end: str = typer.Argument(..., help=TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description"),
           attendees: Optional[str] = typer.Option(None, "--attendees", help="Comma-separated emails"),
           location: Optional[str] = typer.Option(None, "--location"),
           yes: bool = typer.Option(False, "--yes", help="Create this event; default is a local preview")):
    """Create an event. Previews until --yes."""
    options = dict(description=description, attendees=attendees, location=location)
    if _confirm(yes, "create", [title, start, end], options):
        _run("create_event", title, start, end, **options)


@outlook_calendar_app.command("teams")
def teams(title: str = typer.Argument(..., help="Meeting title"),
          start: str = typer.Argument(..., help=TIME_HELP),
          end: str = typer.Argument(..., help=TIME_HELP),
          attendees: str = typer.Option(..., "--attendees", help="Comma-separated emails"),
          description: Optional[str] = typer.Option(None, "--description"),
          yes: bool = typer.Option(False, "--yes", help="Create the event and its Teams link; default previews")):
    """Create an event with a Microsoft Teams meeting link. Previews until --yes."""
    options = dict(attendees=attendees, description=description)
    if _confirm(yes, "teams", [title, start, end], options):
        _run("create_teams_meeting", title, start, end, attendees, description=description)


@outlook_calendar_app.command("update")
def update(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list"),
           title: Optional[str] = typer.Option(None, "--title"),
           start: Optional[str] = typer.Option(None, "--start", help=TIME_HELP),
           end: Optional[str] = typer.Option(None, "--end", help=TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description"),
           attendees: Optional[str] = typer.Option(None, "--attendees", help="Comma-separated emails"),
           location: Optional[str] = typer.Option(None, "--location"),
           yes: bool = typer.Option(False, "--yes", help="Apply the supplied fields to this exact event; default previews")):
    """Update the supplied fields; omitted fields are preserved. Previews until --yes."""
    options = dict(title=title, start=start, end=end, description=description, attendees=attendees, location=location)
    if not any(options.values()):
        print_tip("No changes supplied. Next: co outlook calendar update --help")
        raise typer.Exit(2)
    if _confirm(yes, "update", [event_id], options):
        _run("update_event", event_id, title=title, start_time=start, end_time=end,
             description=description, attendees=attendees, location=location)


@outlook_calendar_app.command("delete")
def delete(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list"),
           yes: bool = typer.Option(False, "--yes", help="Delete the exact event; default previews")):
    """Delete an event by its stable ID, never by a listing number. Previews until --yes."""
    if _confirm(yes, "delete", [event_id], {}):
        _run("delete_event", event_id)
