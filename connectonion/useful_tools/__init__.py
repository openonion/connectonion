"""
Purpose: Export all useful tools and utilities for ConnectOnion agents
LLM-Note:
  Dependencies: imports from [send_email, get_emails, memory, gmail, google_calendar, outlook, microsoft_calendar, web_fetch, shell, diff_writer, tui.pick, terminal, todo_list, slash_command, read_file, edit, multi_edit, glob_files, grep_files, write_file] | imported by [__init__.py main package] | re-exports tools for agent consumption
  Data flow: agent imports from useful_tools → accesses tool functions/classes directly
  State/Effects: no state | pure re-exports | lazy loading for heavy dependencies
  Integration: exposes send_email, get_emails, mark_read, mark_unread (email functions) | Memory, Gmail, GDrive, GoogleCalendar, Outlook, MicrosoftCalendar, WebFetch, Shell, DiffWriter, TodoList (tool classes) | pick, yes_no, autocomplete (TUI helpers) | SlashCommand (extension point) | read_file, edit, multi_edit, glob, grep, write, Write (Claude Code-style tools)
  Errors: ImportError if dependency not installed (e.g., google-auth for GoogleCalendar, httpx for Outlook/MicrosoftCalendar)
"""

from ..tui import pick
from .ask_user import ask_user
from .bash import bash
from .claude_code import ClaudeCode, claude_code
from .codex import codex
from .diff_writer import MODE_AUTO, MODE_NORMAL, MODE_PLAN, DiffWriter

# Claude Code-style file tools
from .file_tools import (
    FileTools,
    edit,
    glob,
    grep,
    multi_edit,
    read_file,
    write,
)
from .gdrive import GDrive
from .get_emails import get_emails, mark_read, mark_unread
from .gmail import Gmail
from .google_calendar import GoogleCalendar
from .memory import Memory
from .microsoft_calendar import MicrosoftCalendar
from .outlook import Outlook
from .send_email import send_email
from .shell import Shell
from .slash_command import SlashCommand
from .synology import Synology
from .telegram import send_telegram
from .terminal import autocomplete, yes_no
from .todo_list import TodoList
from .web_fetch import WebFetch

__all__ = [
    # Email tools
    "send_email",
    "get_emails",
    "mark_read",
    "mark_unread",
    # Class-based tools
    "Memory",
    "Gmail",
    "GDrive",
    "Synology",
    "GoogleCalendar",
    "Outlook",
    "MicrosoftCalendar",
    "WebFetch",
    "Shell",
    "bash",
    "codex",
    "ClaudeCode",
    "claude_code",
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
    "send_telegram",
    # Claude Code-style file tools
    "FileTools",
    "read_file",
    "edit",
    "multi_edit",
    "glob",
    "grep",
    "write",
]
