"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.6.0"

# Auto-load .env files for the entire framework
from dotenv import load_dotenv
from pathlib import Path as _Path

# Load from current working directory (where user runs their script)
# NOT from the module's location (framework directory)
load_dotenv(_Path.cwd() / ".env")

from .core import Agent, LLM, create_tool_from_function
from .core import (
    after_user_input,
    before_llm,
    after_llm,
    before_each_tool,
    before_tools,
    after_each_tool,
    after_tools,
    on_error,
    on_complete,
)
from .logger import Logger
from .llm_do import llm_do
from .transcribe import transcribe
from .prompts import load_system_prompt
from .debug import xray, auto_debug_exception, replay, xray_replay
from .useful_tools import send_email, get_emails, mark_read, mark_unread, Memory, Gmail, GoogleCalendar, Outlook, MicrosoftCalendar, WebFetch, Shell, DiffWriter, pick, yes_no, autocomplete, TodoList, SlashCommand
from .network import connect, RemoteAgent, host, create_app
from .network import relay, announce
from . import address

__all__ = [
    "Agent",
    "LLM",
    "Logger",
    "create_tool_from_function",
    "llm_do",
    "transcribe",
    "load_system_prompt",
    "xray",
    "replay",
    "xray_replay",
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
    "SlashCommand",
    "auto_debug_exception",
    "connect",
    "RemoteAgent",
    "host",
    "create_app",
    "relay",
    "announce",
    "address",
    "after_user_input",
    "before_llm",
    "after_llm",
    "before_each_tool",
    "before_tools",
    "after_each_tool",
    "after_tools",
    "on_error",
    "on_complete"
]