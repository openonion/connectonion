"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.4.2"

# Auto-load .env files for the entire framework
from dotenv import load_dotenv
from pathlib import Path as _Path

# Load from current working directory (where user runs their script)
# NOT from the module's location (framework directory)
load_dotenv(_Path.cwd() / ".env")

from .agent import Agent
from .tool_factory import create_tool_from_function
from .llm import LLM
from .llm_do import llm_do
from .xray import xray
from .decorators import replay, xray_replay
from .useful_tools import send_email, get_emails, mark_read
from .auto_debug_exception import auto_debug_exception
from .connect import connect, RemoteAgent
from .events import (
    after_user_input,
    before_llm,
    after_llm,
    before_tool,
    after_tool,
    on_error
)

__all__ = [
    "Agent",
    "LLM",
    "create_tool_from_function",
    "llm_do",
    "xray",
    "replay",
    "xray_replay",
    "send_email",
    "get_emails",
    "mark_read",
    "auto_debug_exception",
    "connect",
    "RemoteAgent",
    "after_user_input",
    "before_llm",
    "after_llm",
    "before_tool",
    "after_tool",
    "on_error"
]