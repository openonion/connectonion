"""Browser Agent CLI - High-level command execution wrapper.

Purpose: Wrap BrowserAutomation with a ConnectOnion Agent so the `co browser` CLI can run natural-language browser commands end-to-end.
LLM-Note:
  Dependencies: imports from [os, pathlib, dotenv, connectonion.Agent, connectonion.useful_plugins (image_result_formatter, ui_stream), connectonion.useful_tools.browser_tools.BrowserAutomation] | imported by [cli/browser_agent/__init__.py (re-exported), cli/commands/browser_commands.py (lazy import)] | tested by [tests/cli/test_cli_browser.py]
  Data flow: receives command: str (+ headless: bool) from browser_commands.handle_browser() → loads OPENONION_API_KEY (env or ~/.co/keys.env via dotenv) → builds BrowserAutomation context → spins up Agent("browser_cli", model="co/gemini-3-flash-preview", system_prompt=PROMPT_PATH, tools=[browser], plugins=[image_result_formatter, ui_stream], max_iterations=200) → returns agent.input(command) raw string
  State/Effects: launches Playwright browser process via BrowserAutomation context manager (auto-closes on exit) | reads OPENONION_API_KEY from process env or ~/.co/keys.env | may create screenshots/files inside the BrowserAutomation tool calls | streams UI events via ui_stream plugin
  Integration: exposes execute_browser_command(command, headless=False) -> str | PROMPT_PATH points to ./prompts/agent.md (sibling to this file)
  Performance: synchronous, blocks for full agent loop (up to 200 iterations) | one browser session per call (no pooling)
  Errors: returns auth-error string when no OPENONION_API_KEY found instead of raising | other errors bubble from Agent/BrowserAutomation
"""

import os
from pathlib import Path
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter, ui_stream
from dotenv import load_dotenv
from connectonion.useful_tools.browser_tools import BrowserAutomation

# Prompt path for browser agent
PROMPT_PATH = Path(__file__).parent / "prompts" / "agent.md"


def execute_browser_command(command: str, headless: bool = False) -> str:
    """Execute a browser command using natural language.

    Returns the agent's natural language response directly.
    """
    api_key = os.getenv('OPENONION_API_KEY')

    if not api_key:
        global_env = Path.home() / ".co" / "keys.env"
        if global_env.exists():
            load_dotenv(global_env)
            api_key = os.getenv('OPENONION_API_KEY')

    if not api_key:
        return 'Browser agent requires authentication. Run: co auth'

    with BrowserAutomation(headless=headless) as browser:
        agent = Agent(
            name="browser_cli",
            model="co/gemini-3-flash-preview",
            api_key=api_key,
            system_prompt=PROMPT_PATH,
            tools=[browser],
            plugins=[image_result_formatter, ui_stream],
            max_iterations=200
        )
        return agent.input(command)
