"""
Purpose: Human-in-the-loop approval plugin for Google Calendar write operations
LLM-Note:
  Dependencies: imports from [typing, events.before_each_tool, tui.pick, rich.console, rich.panel, rich.text] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_calendar_plugin.py]
  Data flow: before_each_tool → check_calendar_approval() checks if tool is create_event/create_meet/update_event/delete_event → displays event preview with Rich panel → pick() prompts for user approval → raises ValueError to cancel if rejected
  State/Effects: blocks on user input | displays Rich-formatted event preview | raises exception to cancel tool execution | no file I/O | no network
  Integration: exposes calendar_plugin list with [check_calendar_approval] handler | used via Agent(plugins=[calendar_plugin]) | works with GoogleCalendar tool
  Performance: instant display | blocks on user input | no LLM calls
  Errors: raises ValueError on rejection | keyboard interrupts handled gracefully

Calendar plugin - Approval for Google Calendar operations.

Usage:
    from connectonion import Agent, GoogleCalendar
    from connectonion.useful_plugins import calendar_plugin

    calendar = GoogleCalendar()
    agent = Agent("assistant", tools=[calendar], plugins=[calendar_plugin])
"""

from typing import TYPE_CHECKING
from ..events import before_each_tool
from ..tui import pick
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from ..agent import Agent

_console = Console()

# Calendar methods that create/modify/delete events
WRITE_METHODS = ('create_event', 'create_meet', 'update_event', 'delete_event')


@before_each_tool
def check_calendar_approval(agent: 'Agent') -> None:
    """Ask user approval before modifying calendar.

    Raises:
        ValueError: If user rejects the action
    """
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name']
    if tool_name not in WRITE_METHODS:
        return

    args = pending['arguments']

    # Skip if all calendar actions auto-approved
    if agent.current_session.get('calendar_approve_all', False):
        return

    preview = Text()

    if tool_name == 'create_event':
        title = args.get('title', '')
        start = args.get('start_time', '')
        end = args.get('end_time', '')
        attendees = args.get('attendees', '')
        location = args.get('location', '')
        description = args.get('description', '')

        preview.append("Title: ", style="bold cyan")
        preview.append(f"{title}\n")
        preview.append("Start: ", style="bold cyan")
        preview.append(f"{start}\n")
        preview.append("End: ", style="bold cyan")
        preview.append(f"{end}\n")
        if attendees:
            preview.append("Attendees: ", style="bold yellow")
            preview.append(f"{attendees} (will receive invite!)\n")
        if location:
            preview.append("Location: ", style="bold cyan")
            preview.append(f"{location}\n")
        if description:
            preview.append("\n")
            preview.append(description[:300])

        action = "Create Event"

    elif tool_name == 'create_meet':
        title = args.get('title', '')
        start = args.get('start_time', '')
        end = args.get('end_time', '')
        attendees = args.get('attendees', '')
        description = args.get('description', '')

        preview.append("Title: ", style="bold cyan")
        preview.append(f"{title}\n")
        preview.append("Start: ", style="bold cyan")
        preview.append(f"{start}\n")
        preview.append("End: ", style="bold cyan")
        preview.append(f"{end}\n")
        preview.append("Attendees: ", style="bold yellow")
        preview.append(f"{attendees} (will receive Meet invite!)\n")
        if description:
            preview.append("\n")
            preview.append(description[:300])

        action = "Create Meeting"

    elif tool_name == 'update_event':
        event_id = args.get('event_id', '')
        title = args.get('title', '')
        start = args.get('start_time', '')
        end = args.get('end_time', '')
        attendees = args.get('attendees', '')

        preview.append("Event ID: ", style="bold cyan")
        preview.append(f"{event_id}\n")
        if title:
            preview.append("New Title: ", style="bold cyan")
            preview.append(f"{title}\n")
        if start:
            preview.append("New Start: ", style="bold cyan")
            preview.append(f"{start}\n")
        if end:
            preview.append("New End: ", style="bold cyan")
            preview.append(f"{end}\n")
        if attendees:
            preview.append("New Attendees: ", style="bold yellow")
            preview.append(f"{attendees} (will be notified!)\n")

        action = "Update Event"

    elif tool_name == 'delete_event':
        event_id = args.get('event_id', '')

        preview.append("Event ID: ", style="bold red")
        preview.append(f"{event_id}\n")
        preview.append("\n", style="bold red")
        preview.append("This will permanently delete the event!", style="red")

        action = "Delete Event"

    _console.print()
    _console.print(Panel(preview, title=f"[yellow]{action}[/yellow]", border_style="yellow"))

    options = [f"Yes, {action.lower()}"]
    options.append("Auto approve all calendar actions this session")
    options.append("No, tell agent what I want")

    choice = pick(f"Proceed with {action.lower()}?", options, console=_console)

    if choice.startswith("Yes"):
        return
    elif choice == "Auto approve all calendar actions this session":
        agent.current_session['calendar_approve_all'] = True
        return
    else:
        feedback = input("What do you want the agent to do instead? ")
        raise ValueError(f"User feedback: {feedback}")


# Bundle as plugin
calendar_plugin = [
    check_calendar_approval,
]
