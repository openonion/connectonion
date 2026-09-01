"""
Purpose: Public entry point for browser tools — exposes the synchronous BrowserAutomation facade over the async Onionwright core and ElementNotFoundError.
LLM-Note:
  Dependencies: re-exports from [.browser.BrowserAutomation, .element_finder.ElementNotFoundError] | imported by [cli/browser_agent/agent.py, cli/templates/browser/agent.py, cli/templates/minimal/agent.py, user code] | browser.py copies the 1.7 public signatures/docstrings onto the async-core facade
  Data flow: aggregator only — no logic
  Integration: exposes BrowserAutomation, ElementNotFoundError
"""

from .browser import BrowserAutomation as BrowserAutomation
from .element_finder import ElementNotFoundError as ElementNotFoundError
