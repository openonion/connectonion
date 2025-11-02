"""
Purpose: Execute browser automation commands using Playwright-based browser agent
LLM-Note:
  Dependencies: imports from [rich.console, cli/browser_agent/browser.execute_browser_command] | imported by [cli/main.py via handle_browser()] | requires Playwright installation | tested by [tests/cli/test_cli_browser.py]
  Data flow: receives command: str from CLI parser (e.g., "screenshot localhost:3000") → calls execute_browser_command(command) → browser agent parses command and executes via Playwright → returns result string → prints to console via rich.Console
  State/Effects: no persistent state | launches headless browser via Playwright | may create screenshot files in current directory | writes to stdout via rich.Console | browser process lifecycle managed by browser_agent module
  Integration: exposes handle_browser(command) | called from main.py via --browser flag or 'browser' subcommand | delegates to browser_agent/browser.execute_browser_command() | supports commands like "screenshot URL", "navigate URL", "click selector"
  Performance: browser launch overhead (1-3s) | Playwright operations vary by command | screenshot generation is fast (<1s)
  Errors: fails if Playwright not installed | fails if browser launch fails | fails if invalid command syntax | prints error to console but doesn't raise exception
"""

from rich.console import Console

console = Console()


def handle_browser(command: str):
    """Execute browser automation commands - guide browser to do something.

    This is an alternative to the -b flag. Both 'co -b' and 'co browser' are supported.

    Args:
        command: The browser command to execute
    """
    from ..browser_agent.browser import execute_browser_command
    result = execute_browser_command(command)
    console.print(result)