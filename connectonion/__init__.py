"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.5.2"

# Auto-load .env files for the entire framework
from dotenv import load_dotenv
from pathlib import Path as _Path

# Load from current working directory (where user runs their script)
# NOT from the module's location (framework directory)
load_dotenv(_Path.cwd() / ".env")

from .agent import Agent
from .tool_factory import create_tool_from_function
from .llm import LLM
from .logger import Logger
from .llm_do import llm_do
from .prompts import load_system_prompt
from .xray import xray
from .decorators import replay, xray_replay
from .useful_tools import send_email, get_emails, mark_read, mark_unread, Memory, Gmail, GoogleCalendar, Outlook, MicrosoftCalendar, WebFetch, Shell, DiffWriter, pick, yes_no, autocomplete, TodoList, SlashCommand
from .auto_debug_exception import auto_debug_exception
from .connect import connect, RemoteAgent
from .host import host, create_app
from .events import (
    after_user_input,
    before_llm,
    after_llm,
    before_each_tool,
    before_tools,
    after_each_tool,
    after_tools,
    on_error,
    on_complete
)

__all__ = [
    "Agent",
    "LLM",
    "Logger",
    "create_tool_from_function",
    "llm_do",
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