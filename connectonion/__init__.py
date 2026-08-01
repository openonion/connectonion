"""
Purpose: Main package entry point exposing public API for ConnectOnion framework
LLM-Note:
  Dependencies: imports from [core/, logger.py, llm_do.py, transcribe.py, prompts.py, debug/, useful_tools/, network/, address.py] | imported by [user code, tests/, examples/] | no direct tests (integration tests import from here)
  Data flow: loads cwd .env then ~/.co/keys.env via load_dotenv() (first file to define a key wins) → exports all public API symbols → user imports `from connectonion import Agent, llm_do, ...`
  State/Effects: auto-loads both the cwd .env (NOT module directory) and the global ~/.co/keys.env at import time
  Integration: exposes complete public API: Agent, LLM, Logger, create_tool_from_function, llm_do, transcribe, xray, event decorators, built-in tools, networking functions | __all__ defines explicit public exports
  Performance: .env loading happens once at first import (dotenv caches)
  Errors: none (import errors bubble from submodules)
ConnectOnion - A simple agent framework with behavior tracking.
"""

__version__ = "1.5.10"

# Auto-load .env files for the entire framework
import os as _os
import sys as _sys
from dotenv import load_dotenv
from pathlib import Path as _Path

# Load BOTH the project .env and the global ~/.co/keys.env, in that order.
# load_dotenv never overrides an already-set variable, so the first file to
# define a key wins: the project .env overrides, keys.env fills in the rest.
# Loading only one of them silently hid every credential that lives solely in
# keys.env (OAuth tokens land there) from any project that had its own .env.
# The [env] diagnostic answers "which file won?" for a human at a terminal.
# It is written to stderr only when stderr IS a terminal: agents drive `co`
# through bash, which appends any stderr to the tool result as "STDERR:" no
# matter what the exit code was, so an unconditional print made every
# successful command look like it had failed. CO_DEBUG_ENV=1 forces it on for
# piped or redirected debugging.
_show_env = _sys.stderr.isatty() or _os.getenv("CO_DEBUG_ENV") == "1"
for _env_file in (_Path.cwd() / ".env", _Path.home() / ".co" / "keys.env"):
    if _env_file.exists():
        load_dotenv(_env_file)
        if _show_env:
            print(f"[env] {_env_file.resolve()}", file=_sys.stderr)

from .core import Agent, LLM, create_tool_from_function
from .core import (
    on_agent_ready,
    after_user_input,
    before_iteration,
    after_iteration,
    before_llm,
    after_llm,
    before_each_tool,
    before_tools,
    after_each_tool,
    after_tools,
    on_error,
    on_complete,
    on_stop_signal,
)
from .logger import Logger
from .llm_do import llm_do
from .transcribe import transcribe
from .prompts import load_system_prompt
from .debug import xray, auto_debug_exception, replay, xray_replay
from .useful_tools import (
    send_email, get_emails, mark_read, mark_unread,
    Memory, Gmail, GDrive, Synology, GoogleCalendar, Outlook, MicrosoftCalendar,
    WebFetch, Shell, bash, codex, DiffWriter, MODE_NORMAL, MODE_AUTO, MODE_PLAN,
    pick, yes_no, autocomplete, TodoList, SlashCommand,
    # Claude Code-style file tools
    read_file, edit, multi_edit, glob, grep, write,
)
from .network import connect, RemoteAgent, Response, ExecResult, host, create_app, IO
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
    "GDrive",
    "Synology",
    "GoogleCalendar",
    "Outlook",
    "MicrosoftCalendar",
    "WebFetch",
    "Shell",
    "bash",
    "codex",
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
    # Networking
    "connect",
    "RemoteAgent",
    "Response",
    "ExecResult",
    "host",
    "create_app",
    "IO",
    "relay",
    "announce",
    "address",
    # Event decorators
    "on_agent_ready",
    "after_user_input",
    "before_iteration",
    "after_iteration",
    "before_llm",
    "after_llm",
    "before_each_tool",
    "before_tools",
    "after_each_tool",
    "after_tools",
    "on_error",
    "on_complete",
    "on_stop_signal",
]
