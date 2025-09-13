"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.0.7"

from .agent import Agent
from .tools import create_tool_from_function
from .llm import LLM
from .llm_do import llm_do
from .history import History
from .decorators import xray, replay, xray_replay
from .useful_tools import send_email, get_emails, mark_read

__all__ = ["Agent", "LLM", "History", "create_tool_from_function", "llm_do", "xray", "replay", "xray_replay", "send_email", "get_emails", "mark_read"]