"""
Purpose: Export all useful tools and utilities for ConnectOnion agents
LLM-Note:
  Dependencies: imports from [send_email, get_emails, memory, gmail, google_calendar, outlook, microsoft_calendar, web_fetch, shell, diff_writer, tui.pick, terminal, todo_list, slash_command] | imported by [__init__.py main package] | re-exports tools for agent consumption
  Data flow: agent imports from useful_tools → accesses tool functions/classes directly
  State/Effects: no state | pure re-exports | lazy loading for heavy dependencies
  Integration: exposes send_email, get_emails, mark_read, mark_unread (email functions) | Memory, Gmail, GoogleCalendar, Outlook, MicrosoftCalendar, WebFetch, Shell, DiffWriter, TodoList (tool classes) | pick, yes_no, autocomplete (TUI helpers) | SlashCommand (extension point)
  Errors: ImportError if dependency not installed (e.g., google-auth for GoogleCalendar, httpx for Outlook/MicrosoftCalendar)
"""

from .send_email import send_email
from .get_emails import get_emails, mark_read, mark_unread
from .memory import Memory
from .gmail import Gmail
from .google_calendar import GoogleCalendar
from .outlook import Outlook
from .microsoft_calendar import MicrosoftCalendar
from .web_fetch import WebFetch
from .shell import Shell
from .diff_writer import DiffWriter
from ..tui import pick
from .terminal import yes_no, autocomplete
from .todo_list import TodoList
from .slash_command import SlashCommand

__all__ = [
    "send_email",
    "get_emails",
    "mark_read",
    "mark_unread",
    "Memory",
    "Gmail",
    "GoogleCalendar",
    "Outlook",
    "MicrosoftCalendar",
    "WebFetch",
    "Shell",
    "DiffWriter",
    "pick",
    "yes_no",
    "autocomplete",
    "TodoList",
    "SlashCommand"
]