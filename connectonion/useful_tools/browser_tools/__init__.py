"""
Purpose: Public entry point for the built-in browser automation tools — exposes BrowserAutomation (Playwright-driven, anti-detection-tuned) and ElementNotFoundError so user agents can `from connectonion.useful_tools.browser_tools import BrowserAutomation`.
LLM-Note:
  Dependencies: re-exports from [.browser.BrowserAutomation, .element_finder.ElementNotFoundError] | imported by [cli/browser_agent/agent.py, cli/templates/browser/agent.py, cli/templates/minimal/agent.py, user code] | sibling modules: browser.py (main automation class), element_finder.py (LLM-aided element locator), browser_config.py (Chrome args), highlight_screenshot.py, scroll.py
  Data flow: aggregator only — no logic
  Integration: exposes BrowserAutomation, ElementNotFoundError
"""

from .browser import BrowserAutomation
from .element_finder import ElementNotFoundError
