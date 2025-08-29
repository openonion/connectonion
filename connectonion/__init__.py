"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.0.1b6"

from .agent import Agent
from .tools import create_tool_from_function
from .llm import LLM
from .llm_function import llm
from .history import History
from .decorators import xray, replay, xray_replay

__all__ = ["Agent", "LLM", "History", "create_tool_from_function", "llm", "xray", "replay", "xray_replay"]