"""
Purpose: Thin CLI handler for `co browser` — forwards verbs to the persistent browser daemon, and serves self-describing help.
LLM-Note:
  Dependencies: imports from [sys, shlex, browser_agent.client.send, browser_agent.daemon.list_functions] | imported by [cli/main.py via browser()] | tested by [tests/e2e/cli/test_cli_browser.py, tests/e2e/cli/test_browser_daemon.py]
  Data flow: receives args: list[str] (+ headless: bool) from CLI → `help`/`--list` printed locally by introspecting BrowserAutomation (no browser launched) → otherwise shlex.join → client.send() → daemon matches the first word to a BrowserAutomation method and executes it (or runs the NL agent for the `do` verb) → result printed to stdout/stderr by client, exit code returned
  State/Effects: no local state | `help` introspects the class only | other verbs delegate browser/process lifecycle to the daemon | prints usage to stderr when called with no args
  Integration: exposes handle_browser(args, headless=False) -> int (exit code) | called from main.py browser command
  Performance: `help` is import-only (no socket, no Chrome) | other verbs: one socket round-trip, first call spawns the daemon
  Errors: daemon-side errors come back as ERR → stderr + exit 1; unknown verbs and wrong-argument errors include a next-step hint
"""

import sys
import shlex

from ..browser_agent.client import send
from ..browser_agent.daemon import list_functions

USAGE = (
    "co browser — drive one persistent browser from the shell\n"
    "\n"
    "  co browser <function> [args]     run a browser function directly (deterministic)\n"
    '  co browser do "<instruction>"    let the AI agent do it (natural language)\n'
    "  co browser close                 close the browser and stop the daemon\n"
    "  co browser help                  list every browser function\n"
    "\n"
    "The browser stays open between commands (one shared session) until `close`.\n"
    "Add --headless before the function to run without a visible window.\n"
    "Output goes to stdout, errors to stderr; exit code is 0 on success, 1 on failure."
)


def handle_browser(args, headless: bool = False) -> int:
    """Forward a browser command to the daemon, or print help. Returns the process exit code."""
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    if args[0] in ("help", "--list", "list"):
        print(USAGE + "\n\nFunctions:\n" + list_functions())
        return 0
    return send(shlex.join(args), headless=headless)
