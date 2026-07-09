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
from pathlib import Path

from ..browser_agent.client import send
from ..browser_agent.daemon import list_functions

USAGE = (
    "co browser — drive one persistent browser from the shell\n"
    "\n"
    "  co browser <function> [args]     run a browser function directly (deterministic)\n"
    '  co browser do "<instruction>"    let the AI agent do it (natural language)\n'
    '  co browser newtab <url> --purpose="..." --who=<name> [--hours=2]   open + occupy a new tab\n'
    "  co browser use <tab>             switch the active tab (alias: switch; 'default' = base tab)\n"
    "  co browser status                show open tabs, the last command, who and why\n"
    "  co browser closetab <tab>        close ONE tab (id from status); 'close' stops everything\n"
    "  co browser close                 close the browser and stop the daemon\n"
    "  co browser help                  list every browser function\n"
    "\n"
    "The browser stays open between commands (one shared session) until `close`.\n"
    "`newtab` opens a new occupied tab and makes it active; `use` switches between tabs.\n"
    "A new tab needs --purpose and --who (and optional --hours); reusing an occupied tab does not.\n"
    "Add --headless before the function to run without a visible window.\n"
    "Output goes to stdout, errors to stderr; exit code is 0 on success, 1 on failure."
)

TIPS = [
    "See every open tab, its owner and purpose:  co browser status",
    'Open a dedicated tab:  co browser newtab <url> --purpose="..." --who=<name> --hours=2',
    "Switch between tabs:  co browser use <id>   (default = the first tab)",
    "Close just one tab:  co browser closetab <id>   (close stops the whole browser)",
    'Let the AI do it:  co browser do "log in and download my invoices"',
    "List every function you can call directly:  co browser help",
    "Run without a visible window:  co browser --headless <function>",
    "The browser stays open between commands — one shared session until close.",
]


def _next_tip():
    """Rotate through TIPS so each run teaches something new; index persists in ~/.co."""
    state = Path.home() / ".co" / ".browser_tip"
    idx = int(state.read_text()) if state.exists() else 0
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(str((idx + 1) % len(TIPS)))
    return TIPS[idx % len(TIPS)]


def handle_browser(args, headless: bool = False) -> int:
    """Forward a browser command to the daemon, or print help. Returns the process exit code."""
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    if args[0] in ("help", "--list", "list"):
        print(USAGE + "\n\nFunctions:\n" + list_functions())
        return 0
    code = send(shlex.join(args), headless=headless)
    if code == 0 and sys.stdout.isatty():
        print(f"\n\033[2m💡 {_next_tip()}\033[0m")
    return code
