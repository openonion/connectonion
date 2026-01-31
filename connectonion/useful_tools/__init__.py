"""
Purpose: Export all useful tools and utilities for ConnectOnion agents
LLM-Note:
  Dependencies: imports from [send_email, get_emails, memory, gmail, google_calendar, outlook, microsoft_calendar, web_fetch, shell, diff_writer, tui.pick, terminal, todo_list, slash_command, read_file, edit, multi_edit, glob_files, grep_files, write_file] | imported by [__init__.py main package] | re-exports tools for agent consumption
  Data flow: agent imports from useful_tools → accesses tool functions/classes directly
  State/Effects: no state | pure re-exports | lazy loading for heavy dependencies
  Integration: exposes send_email, get_emails, mark_read, mark_unread (email functions) | Memory, Gmail, GoogleCalendar, Outlook, MicrosoftCalendar, WebFetch, Shell, DiffWriter, TodoList (tool classes) | pick, yes_no, autocomplete (TUI helpers) | SlashCommand (extension point) | read_file, edit, multi_edit, glob, grep, write, Write (Claude Code-style tools)
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
from .bash import bash
from .diff_writer import DiffWriter, MODE_NORMAL, MODE_AUTO, MODE_PLAN
from ..tui import pick
from .terminal import yes_no, autocomplete
from .todo_list import TodoList
from .slash_command import SlashCommand
from .ask_user import ask_user

# Claude Code-style file tools
from .read_file import read_file
from .edit import edit
from .multi_edit import multi_edit
from .glob_files import glob
from .grep_files import grep
from .write_file import write, FileWriter

__all__ = [
    # Email tools
    "send_email",
    "get_emails",
    "mark_read",
    "mark_unread",
    # Class-based tools
    "Memory",
    "Gmail",
    "GoogleCalendar",
    "Outlook",
    "MicrosoftCalendar",
    "WebFetch",
    "Shell",
    "bash",
    "DiffWriter",
    "MODE_NORMAL",
    "MODE_AUTO",
    "MODE_PLAN",
    # TUI helpers
    "pick",
    "yes_no",
    "autocomplete",
    # Task management
    "TodoList",
    "SlashCommand",
    "ask_user",
    # Claude Code-style file tools
    "read_file",
    "edit",
    "multi_edit",
    "glob",
    "grep",
    "write",
    "FileWriter",
]