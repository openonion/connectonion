"""Useful tools for ConnectOnion agents."""

from .send_email import send_email
from .get_emails import get_emails, mark_read, mark_unread
from .memory import Memory
from .gmail import Gmail
from .web_fetch import WebFetch
from .shell import Shell
from .diff_writer import DiffWriter

__all__ = ["send_email", "get_emails", "mark_read", "mark_unread", "Memory", "Gmail", "WebFetch", "Shell", "DiffWriter"]