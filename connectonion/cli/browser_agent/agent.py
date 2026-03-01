"""Browser Agent CLI - High-level command execution wrapper.

This module provides the execute_browser_command function that wraps
the BrowserAutomation class with ConnectOnion Agent for natural language
command execution.
"""

import os
from pathlib import Path
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter, ui_stream
from dotenv import load_dotenv
from connectonion.useful_tools.browser_tools import BrowserAutomation

# Prompt path for browser agent
PROMPT_PATH = Path(__file__).parent / "prompts" / "agent.md"


def execute_browser_command(command: str, headless: bool = True) -> str:
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
