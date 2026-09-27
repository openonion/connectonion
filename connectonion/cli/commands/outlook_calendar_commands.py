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
    help="Your Outlook calendar: events, Teams meetings, free slots. Bare 'co outlook calendar' lists events (Read-only).",
    epilog="Example:  co outlook calendar today",
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


@outlook_calendar_app.command("list", epilog="Example:  co outlook calendar list --days 14")
def list_events(days: int = typer.Option(7, "--days", min=1, help="How many days ahead to include, starting now"),
                last: int = typer.Option(20, "--last", "-n", min=1, max=250, help="Maximum events to show")):
    """List upcoming events with stable event IDs (not row numbers). Read-only."""
    _run("list_events", days_ahead=days, max_results=last)


@outlook_calendar_app.command("today", epilog="Example:  co outlook calendar today")
def today():
    """Read today's events. Read-only."""
    _run("get_today_events")


@outlook_calendar_app.command("read", epilog="Example:  co outlook calendar read AAMkAGQ5ZjE3LTJiYzEAAA=")
def read(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list")):
    """Read one event by ID. Read-only."""
    _run("get_event", event_id)


@outlook_calendar_app.command("meetings", epilog="Example:  co outlook calendar meetings --days 14")
def meetings(days: int = typer.Option(7, "--days", min=1, help="How many days ahead to include, starting now")):
    """Read upcoming events that have attendees. Read-only."""
    _run("get_upcoming_meetings", days_ahead=days)


@outlook_calendar_app.command("free", epilog="Example:  co outlook calendar free 2026-10-01 --minutes 30")
def free(date: str = typer.Argument(..., help="YYYY-MM-DD; business hours in UTC"),
         minutes: int = typer.Option(60, "--minutes", min=1, max=480, help="Length of free time to find, in minutes")):
    """Find free slots between 09:00 and 17:00 UTC on one day. Read-only."""
    _run("find_free_slots", date, duration_minutes=minutes)


@outlook_calendar_app.command("create", epilog="Example:  co outlook calendar create \"Design review\" 2026-10-01T10:00:00Z 2026-10-01T11:00:00Z --attendees sam@example.com --yes")
def create(title: str = typer.Argument(..., help="Event title"),
           start: str = typer.Argument(..., help=TIME_HELP),
           end: str = typer.Argument(..., help=TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description", help="Event description, plain text"),
           attendees: Optional[str] = typer.Option(None, "--attendees", help="Comma-separated emails"),
           location: Optional[str] = typer.Option(None, "--location", help="Location text shown on the event"),
           yes: bool = typer.Option(False, "--yes", help="Create this event; default is a local preview")):
    """Create an event. Previews until --yes, which Creates it in your calendar and invites any --attendees."""
    options = dict(description=description, attendees=attendees, location=location)
    if _confirm(yes, "create", [title, start, end], options):
        _run("create_event", title, start, end, **options)


@outlook_calendar_app.command("teams", epilog="Example:  co outlook calendar teams \"Weekly sync\" 2026-10-01T10:00:00Z 2026-10-01T11:00:00Z --attendees sam@example.com --yes")
def teams(title: str = typer.Argument(..., help="Meeting title"),
          start: str = typer.Argument(..., help=TIME_HELP),
          end: str = typer.Argument(..., help=TIME_HELP),
          attendees: str = typer.Option(..., "--attendees", help="Comma-separated emails"),
          description: Optional[str] = typer.Option(None, "--description", help="Event description, plain text"),
          yes: bool = typer.Option(False, "--yes", help="Create the event and its Teams link; default previews")):
    """Create an event with a Microsoft Teams meeting link. Previews until --yes, which Creates it and invites the --attendees.

    Teams meetings need a work or school Microsoft account; on a personal account the command stops before anything is created or sent.
    """
    options = dict(attendees=attendees, description=description)
    if _confirm(yes, "teams", [title, start, end], options):
        _run("create_teams_meeting", title, start, end, attendees, description=description)


@outlook_calendar_app.command("update", epilog="Example:  co outlook calendar update <event-id> --location \"Room 4\" --yes")
def update(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list"),
           title: Optional[str] = typer.Option(None, "--title", help="New event title"),
           start: Optional[str] = typer.Option(None, "--start", help=TIME_HELP),
           end: Optional[str] = typer.Option(None, "--end", help=TIME_HELP),
           description: Optional[str] = typer.Option(None, "--description", help="Event description, plain text"),
           attendees: Optional[str] = typer.Option(None, "--attendees", help="Comma-separated emails"),
           location: Optional[str] = typer.Option(None, "--location", help="Location text shown on the event"),
           yes: bool = typer.Option(False, "--yes", help="Apply the supplied fields to this exact event; default previews")):
    """Update the supplied fields; omitted fields are preserved. Previews until --yes, which Changes the event."""
    options = dict(title=title, start=start, end=end, description=description, attendees=attendees, location=location)
    if not any(options.values()):
        print_tip("No changes supplied. Next: co outlook calendar update --help")
        raise typer.Exit(2)
    if _confirm(yes, "update", [event_id], options):
        _run("update_event", event_id, title=title, start_time=start, end_time=end,
             description=description, attendees=attendees, location=location)


@outlook_calendar_app.command("delete", epilog="Example:  co outlook calendar delete AAMkAGQ5ZjE3LTJiYzEAAA=  |  "
                                               "co outlook calendar delete AAMkAGQ5ZjE3LTJiYzEAAA= --yes")
def delete(event_id: str = typer.Argument(..., help="Exact event ID from co outlook calendar list"),
           yes: bool = typer.Option(False, "--yes", help="Delete the exact event; default previews")):
    """Delete one event by its ID from co outlook calendar list. Without --yes it only previews and changes nothing; --yes Deletes it."""
    if _confirm(yes, "delete", [event_id], {}):
        _run("delete_event", event_id)
