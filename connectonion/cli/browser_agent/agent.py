"""Browser Agent CLI - High-level command execution wrapper.

Purpose: Build the ConnectOnion browser Agent; `co browser do` supplies a daemon-backed proxy so model waits stay in the CLI process.
LLM-Note:
  Dependencies: imports from [pathlib, connectonion.Agent, connectonion.useful_plugins (image_result_formatter, ui_stream), connectonion.useful_tools.browser_tools.BrowserAutomation, cli.commands.project_cmd_lib.load_api_key (lazy)] | imported by [cli/browser_agent/__init__.py (re-exported), cli/commands/browser_commands.py (lazy import), cli/browser_agent/daemon.py] | tested by [tests/unit/test_the_browser_agent_bills_this_account.py]
  Data flow: browser_commands.handle_browser() → client._run_do() resolves OPENONION_API_KEY through load_api_key(), which verifies the token belongs to this machine's account → builds Agent("browser_cli", model="co/gemini-3.7-flash", tools=[DaemonBrowserProxy]) → model thinking stays local and each tool call is one short daemon request
  State/Effects: resolves OPENONION_API_KEY in the caller environment (env, ./.env, ~/.co/keys.env; re-authenticates if the token names another account) | may create screenshots/files through daemon-backed tool calls | streams UI events via ui_stream plugin
  Integration: exposes execute_browser_command(command, headless=False) -> str | PROMPT_PATH points to ./prompts/agent.md (sibling to this file)
  Performance: synchronous in the caller, blocks that CLI for up to 200 iterations | does not block the daemon between tool calls | reuses the daemon's persistent browser/profile
  Errors: returns auth-error string when no OPENONION_API_KEY found instead of raising | other errors bubble from Agent/BrowserAutomation
"""

from pathlib import Path

from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter, ui_stream
from connectonion.useful_tools.browser_tools import BrowserAutomation

# Prompt path for browser agent
PROMPT_PATH = Path(__file__).parent / "prompts" / "agent.md"


def resolve_api_key() -> str:
    """Return the OpenOnion API key for *this machine* (empty string if absent).

    This used to do its own lookup — environment, else ``~/.co/keys.env`` — which
    is `load_api_key()` minus the one thing that matters here: the check that the
    token belongs to the account whose key this machine holds.

    That check belongs on this path more than on most. `co browser do` bills a
    model call to whatever the caller's token says. A stray ``.env`` naming a
    drained agent once showed up as "insufficient credit" against an account
    that had plenty; resolving in the caller keeps the payer explicit per run.
    """
    from ..commands.project_cmd_lib import load_api_key

    return load_api_key() or ""


def build_browser_agent(browser, api_key: str) -> Agent:
    """Build the natural-language browser Agent driving an existing BrowserAutomation."""
    return Agent(
        name="browser_cli",
        model="co/gemini-3.7-flash",
        api_key=api_key,
        system_prompt=PROMPT_PATH,
        tools=[browser],
        plugins=[image_result_formatter, ui_stream],
        max_iterations=200,
    )


def execute_browser_command(command: str, headless: bool = False) -> str:
    """Execute a browser command using natural language.

    Returns the agent's natural language response directly.
    """
    api_key = resolve_api_key()
    if not api_key:
        return 'Browser agent requires authentication. Run: co auth'

    with BrowserAutomation(headless=headless) as browser:
        return build_browser_agent(browser, api_key).input(command)
