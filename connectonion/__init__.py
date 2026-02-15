"""
Purpose: Main package entry point exposing public API for ConnectOnion framework
LLM-Note:
  Dependencies: imports from [core/, logger.py, llm_do.py, transcribe.py, prompts.py, debug/, useful_tools/, network/, address.py] | imported by [user code, tests/, examples/] | no direct tests (integration tests import from here)
  Data flow: loads .env from cwd via load_dotenv() → exports all public API symbols → user imports `from connectonion import Agent, llm_do, ...`
  State/Effects: auto-loads .env file from current working directory (NOT module directory) at import time
  Integration: exposes complete public API: Agent, LLM, Logger, create_tool_from_function, llm_do, transcribe, xray, event decorators, built-in tools, networking functions | __all__ defines explicit public exports
  Performance: .env loading happens once at first import (dotenv caches)
  Errors: none (import errors bubble from submodules)
ConnectOnion - A simple agent framework with behavior tracking.
"""

__version__ = "0.7.0"

# Auto-load .env files for the entire framework
from dotenv import load_dotenv
from pathlib import Path as _Path

# SDK only loads from current working directory (where user runs their script)
# CLI commands (co ai, co browser, etc.) handle global fallback separately
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
from .useful_tools import (
    send_email, get_emails, mark_read, mark_unread,
    Memory, Gmail, GoogleCalendar, Outlook, MicrosoftCalendar,
    WebFetch, GatherIs, Shell, bash, DiffWriter, MODE_NORMAL, MODE_AUTO, MODE_PLAN,
    pick, yes_no, autocomplete, TodoList, SlashCommand,
    # Claude Code-style file tools
    read_file, edit, multi_edit, glob, grep, write, FileWriter,
)
from .network import connect, RemoteAgent, Response, host, create_app, IO
from .network import relay, announce
from . import address

__all__ = [
    # Core
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
    "auto_debug_exception",
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
    "GatherIs",
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
    # Claude Code-style file tools
    "read_file",
    "edit",
    "multi_edit",
    "glob",
    "grep",
    "write",
    "FileWriter",
    # Networking
    "connect",
    "RemoteAgent",
    "Response",
    "host",
    "create_app",
    "IO",
    "relay",
    "announce",
    "address",
    # Event decorators
    "after_user_input",
    "before_llm",
    "after_llm",
    "before_each_tool",
    "before_tools",
    "after_each_tool",
    "after_tools",
    "on_error",
    "on_complete",
]