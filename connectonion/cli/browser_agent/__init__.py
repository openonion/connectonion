"""
Purpose: Lazy browser-agent exports that keep direct `co browser` RPC clients lightweight.
LLM-Note:
  Dependencies: lazy imports from [agent.py, browser_tools] | imported by [cli/commands/browser_commands.py] | no direct tests
  Data flow: resolves execute_browser_command or BrowserAutomation only when a caller asks for that public export
  State/Effects: no state
  Integration: exposes execute_browser_command(), BrowserAutomation class for `co browser` command
  Performance: importing a browser_agent submodule does not load Agent, Playwright, TUI, or provider integrations
  Errors: none
Browser agent module for ConnectOnion CLI.
"""

__all__ = ['execute_browser_command', 'BrowserAutomation']


def __getattr__(name):
    if name == "execute_browser_command":
        from .agent import execute_browser_command
        return execute_browser_command
    if name == "BrowserAutomation":
        from connectonion.useful_tools.browser_tools import BrowserAutomation
        return BrowserAutomation
    raise AttributeError(name)
