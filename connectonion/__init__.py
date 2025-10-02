"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.1.3"

from .agent import Agent
from .tool_factory import create_tool_from_function
from .llm import LLM
from .llm_do import llm_do
from .history import History
from .xray import xray
from .decorators import replay, xray_replay
from .useful_tools import send_email, get_emails, mark_read
from .auto_debug_exception import auto_debug_exception

__all__ = ["Agent", "LLM", "History", "create_tool_from_function", "llm_do", "xray", "replay", "xray_replay", "send_email", "get_emails", "mark_read", "auto_debug_exception"]