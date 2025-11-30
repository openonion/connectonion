"""Useful tools for ConnectOnion agents."""

from .send_email import send_email
from .get_emails import get_emails, mark_read, mark_unread
from .memory import Memory
from .gmail import Gmail
from .google_calendar import GoogleCalendar
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
    "WebFetch",
    "Shell",
    "DiffWriter",
    "pick",
    "yes_no",
    "autocomplete",
    "TodoList",
    "SlashCommand"
]