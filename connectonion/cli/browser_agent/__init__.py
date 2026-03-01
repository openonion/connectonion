"""
Purpose: Browser agent module exports for CLI browser automation
LLM-Note:
  Dependencies: imports from [browser.py] | imported by [cli/commands/browser_commands.py] | no direct tests
  Data flow: re-exports execute_browser_command and BrowserAutomation
  State/Effects: no state
  Integration: exposes execute_browser_command(), BrowserAutomation class for `co browser` command
  Performance: trivial
  Errors: none
Browser agent module for ConnectOnion CLI.
"""

from .agent import execute_browser_command
from connectonion.useful_tools.browser_tools import BrowserAutomation

__all__ = ['execute_browser_command', 'BrowserAutomation']