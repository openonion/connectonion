"""ConnectOnion - A simple agent framework with behavior tracking."""

__version__ = "0.1.0"

from .agent import Agent
from .tools import Tool
from .llm import LLM
from .history import History

__all__ = ["Agent", "Tool", "LLM", "History"]