"""
Purpose: Thin CLI handler for `co browser` — forwards verbs to the persistent browser daemon.
LLM-Note:
  Dependencies: imports from [shlex, browser_agent.client.send] | imported by [cli/main.py via browser()] | tested by [tests/e2e/cli/test_cli_browser.py]
  Data flow: receives args: list[str] (+ headless: bool) from CLI → shlex.join → client.send() → connects to daemon (spawns if absent) → daemon matches the first word to a BrowserAutomation method and executes it (or runs the NL agent for the `do` verb) → result printed to stdout/stderr by client, exit code returned
  State/Effects: no local state | delegates browser/process lifecycle to the daemon | prints usage to stderr when called with no args
  Integration: exposes handle_browser(args, headless=False) -> int (exit code) | called from main.py browser command
  Performance: one socket round-trip per call | first call spawns the daemon (browser launch latency)
  Errors: daemon-side errors come back as ERR → stderr + exit 1
"""

import sys
import shlex

from ..browser_agent.client import send

USAGE = (
    "Usage: co browser <command> [args]\n"
    "  co browser go_to x.com           run a browser function directly\n"
    "  co browser take_screenshot       (any BrowserAutomation method works)\n"
    "  co browser do \"<instruction>\"    run the natural-language agent\n"
    "  co browser close                 close the browser (stops the daemon)"
)


def handle_browser(args, headless: bool = False) -> int:
    """Forward a browser command to the daemon. Returns the process exit code."""
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    return send(shlex.join(args), headless=headless)
