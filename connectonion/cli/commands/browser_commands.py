"""
Purpose: Thin CLI handler for `co browser` — parses -t/--tab targeting, forwards one command to the persistent browser daemon, and serves self-describing help.
LLM-Note:
  Dependencies: imports from [sys, shlex, pathlib, browser_agent.client.send, browser_agent.daemon.list_functions] | imported by [cli/main.py via browser()] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: receives args: list[str] (+ headless: bool) from CLI → `help`/`--list` printed locally by introspecting BrowserAutomation (no browser launched) → else _extract_tab() pulls the LEADING -t/--tab NAME run (stops at the verb, so a -t that is a function's own arg passes through; empty --tab= is a usage error) → shlex.join(remaining args) + tab → client.send(line, headless, tab=NAME) → daemon runs it → payload/exit code surfaced by the client
  State/Effects: no local state except a best-effort rotating-tip index at ~/.co/.browser_tip (parsed defensively, written atomically, never affects the command's exit code) | the success tip is printed to STDERR (stdout stays pure data) | `help` introspects the class only | other verbs delegate browser/process lifecycle to the daemon
  Integration: exposes _extract_tab(args) -> (tab|None, remaining|None), _next_tip(), handle_browser(args, headless=False) -> int | called from main.py browser command | USAGE/TIPS document the tab lifecycle and the exit-code contract
  Performance: `help` is import-only (no socket, no Chrome) | other verbs: one socket round-trip, first call spawns the daemon
  Errors: no-args / bad -t → prints usage to stderr, exit 2 | daemon errors come back as ERR[ <code>] → stderr + the mirrored exit code (0 ok · 1 failure · 2 usage · 3 unknown tab · 4 tab busy)
"""

import sys
import shlex
from pathlib import Path

from ..browser_agent.client import send
from ..browser_agent.daemon import list_functions

USAGE = (
    "co browser — drive one persistent browser from the shell\n"
    "\n"
    "  co browser [-t TAB] <function> [args]    run a browser function (bare = the shared 'main' tab)\n"
    '  co browser [-t TAB] do "<instruction>"   let the AI agent do it — same targeting grammar\n'
    '  co browser tab open [NAME] [--who <agent>] [--for "<purpose>"]   register a tab; prints its name\n'
    "  co browser tab ls [--json]               the board: every tab, who runs it, last command\n"
    "  co browser tab close <NAME>              release your tab when the task is done\n"
    "  co browser close                         close the browser and stop the daemon\n"
    "  co browser help                          list every browser function\n"
    "\n"
    "One task = one tab. Solo use needs no -t at all. Running several agents on this\n"
    "browser? Each opens its own tab once, adds -t <name> to EVERY command (including\n"
    "do), and closes it when finished. The browser stays open until `close`.\n"
    "\n"
    "Contention: if another agent is mid-task on the shared main tab, your bare command\n"
    "fails with exit 4 and tells you who has it and what to run instead — agents discover\n"
    "each other through this error and through `tab ls`. Set CO_WHO=<name> so the board\n"
    "shows a real name for you (Claude Code sessions are identified automatically).\n"
    "Add --headless before the function to run without a visible window.\n"
    "stdout = data, stderr = errors; exit 0 ok · 1 failure · 2 usage · 3 unknown tab · 4 tab busy."
)

TIPS = [
    "See every tab, its owner and last command:  co browser tab ls",
    'Your own tab for a task:  co browser tab open mytask --who me --for "posting"',
    "Target your tab on every command:  co browser -t mytask go_to <url>",
    "Done with a task? Release its tab:  co browser tab close mytask",
    'Let the AI do it:  co browser do "log in and download my invoices"',
    "List every function you can call directly:  co browser help",
    "Run without a visible window:  co browser --headless <function>",
    "The browser stays open between commands — one shared session until close.",
]


def _next_tip():
    """Rotate through TIPS so each run teaches something new; index persists in ~/.co.
    Best-effort and crash-proof — a corrupt/racing state file must never change the
    command's exit status, so parse defensively and write atomically."""
    state = Path.home() / ".co" / ".browser_tip"
    try:
        idx = int(state.read_text().strip())
    except (OSError, ValueError):
        idx = 0
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        tmp = state.with_suffix(".tmp")
        tmp.write_text(str((idx + 1) % len(TIPS)))
        tmp.replace(state)
    except OSError:
        pass
    return TIPS[idx % len(TIPS)]


def _extract_tab(args):
    """Pull the leading -t/--tab NAME out of args, then stop.

    Only the run of flags BEFORE the verb is scanned, so a value equal to '-t' or
    '--tab=' that belongs to a browser function (e.g. `type_text '#q' -t`) is passed
    through untouched. Returns (tab_or_None, remaining_args) — or (None, None) on a
    dangling or empty flag, which the caller reports as a usage error (exit 2).
    """
    tab, i = None, 0
    while i < len(args):
        tok = args[i]
        if tok in ("-t", "--tab"):
            if i + 1 >= len(args):
                return None, None
            tab = args[i + 1]
            i += 2
        elif tok.startswith("--tab="):
            tab = tok.split("=", 1)[1]
            i += 1
        else:
            break  # first non-tab token is the verb; everything from here is the command
    if tab == "":  # --tab= / -t "" must fail loudly, not silently fall back to main
        return None, None
    return tab, args[i:]


def handle_browser(args, headless: bool = False) -> int:
    """Forward a browser command to the daemon, or print help. Returns the process exit code."""
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] in ("help", "--list", "list"):
        print(USAGE + "\n\nFunctions:\n" + list_functions())
        return 0
    tab, args = _extract_tab(args)
    if args is None:
        print("usage: -t needs a tab name, e.g.  co browser -t mytask go_to <url>", file=sys.stderr)
        return 2
    if not args:
        print("usage: -t targets a command, e.g.  co browser -t mytask go_to <url>", file=sys.stderr)
        return 2
    code = send(shlex.join(args), headless=headless, tab=tab)
    if code == 0 and sys.stdout.isatty():
        print(f"\n\033[2m💡 {_next_tip()}\033[0m", file=sys.stderr)
    return code
