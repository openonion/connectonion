"""
Purpose: Thin CLI handler for `co browser` — parses -t/--tab targeting, forwards one command to the persistent browser daemon, and serves self-describing help.
LLM-Note:
  Dependencies: imports from [sys, shlex, pathlib, browser_agent.client.send | lazy: browser_agent.daemon.list_functions for help] | imported by [cli/main.py via browser()] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: receives args: list[str] (+ headless and optional engine_mode) from CLI → loads the persisted wtf/chrome choice (wtf by default) → exact `install-onion` runs the signed private-client bootstrap and returns before daemon contact → `help`/`--list` printed locally by introspecting BrowserAutomation (no browser launched) → else _extract_tab() pulls the LEADING -t/--tab NAME run (stops at the verb, so a -t that is a function's own arg passes through; empty --tab= is a usage error) → shlex.join(remaining args) + tab + engine mode → client.send() → a mode-pinned daemon runs it → payload/exit code surfaced by the client
  State/Effects: `install-onion` explicitly installs a signature/checksum-verified wheel into the current Python environment | otherwise no local state except a best-effort rotating-tip index at ~/.co/.browser_tip (a garbled index resets to the first tip) | the success tip is printed to STDERR (stdout stays pure data) | `help` introspects the class only | direct verbs delegate to the daemon; `do` runs its model loop in this CLI process and delegates each tool call
  Integration: exposes _extract_tab(args) -> (tab|None, remaining|None), _next_tip(), handle_browser(args, headless=False, engine_mode=None) -> int | called from main.py browser command | USAGE/TIPS document the tab lifecycle, engine modes, and exit-code contract
  Performance: direct verbs do not import the browser-owning daemon, Agent, or Playwright; `help` lazily imports the schema (no socket, no Chrome) | other verbs: one socket round-trip, first call spawns the daemon
  Errors: no-args / bad -t → prints usage to stderr, exit 2 | daemon errors come back as ERR[ <code>] → stderr + the mirrored exit code (0 ok · 1 failure · 2 usage · 3 unknown tab · 4 tab busy)
"""

import shlex
import sys
from pathlib import Path

from ..browser_agent.client import send
USAGE = (
    "co browser — drive one persistent browser from the shell\n"
    "\n"
    "  co browser [-t TAB] <function> [args]    run a browser function (bare = the shared 'main' tab)\n"
    "  co browser --engine wtf|chrome <function> [args]\n"
    "  co browser config set engine wtf|chrome  save the default engine\n"
    "  co browser config get engine             print the saved/default engine\n"
    '  co browser [-t TAB] do "<instruction>"   let the AI agent do it — same targeting grammar\n'
    '  co browser tab open [NAME] [--who <agent>] [--for "<purpose>"]   register a tab; prints its name\n'
    "  co browser tab ls [--json]               the board: every tab, who runs it, last command\n"
    "  co browser tab close <NAME>              release your tab when the task is done\n"
    "  co browser close                         close the browser and stop the daemon\n"
    "  co browser install-onion                  install the signed private Onionwright client\n"
    "  co browser help                          list every browser function\n"
    "  printf secret | co browser fill_text_by_selector '#field' --stdin\n"
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
    "Engine default: WTFbrowser (paid). Chrome is an explicit compatibility mode and may be detected.\n"
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


def _load_default_engine() -> str:
    from ...useful_tools.browser_tools.engine_preferences import load_default_engine

    return load_default_engine()


def _next_tip():
    """Rotate through TIPS so each run teaches something new; index persists in ~/.co.
    A garbled state file (e.g. two commands racing the write) resets to the first tip."""
    state = Path.home() / ".co" / ".browser_tip"
    raw = state.read_text(encoding="utf-8").strip() if state.exists() else ""
    idx = int(raw) if raw.isdigit() else 0
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(str((idx + 1) % len(TIPS)), encoding="utf-8")
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


def _handle_config(args) -> int:
    from ...useful_tools.browser_tools import engine as browser_engine
    from ...useful_tools.browser_tools.engine_preferences import (
        BrowserEnginePreferenceError,
        load_default_engine,
        save_default_engine,
    )

    if args == ["config", "get", "engine"]:
        try:
            print(load_default_engine())
        except BrowserEnginePreferenceError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    if len(args) == 5 and args[:4] == ["config", "set", "engine", "--"]:
        # Do not create a second spelling merely because a shell inserted `--`.
        args = ["config", "set", "engine", args[4]]
    if len(args) == 4 and args[:3] == ["config", "set", "engine"]:
        try:
            selected = browser_engine.normalize_mode(args[3])
            path = save_default_engine(selected)
        except (browser_engine.BrowserEngineError, BrowserEnginePreferenceError) as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"Default browser engine: {selected} ({path})")
        if selected == browser_engine.CHROME:
            print(f"WARNING: {browser_engine.CHROME_WARNING}", file=sys.stderr)
        return 0
    print(
        "usage: co browser config get engine | "
        "co browser config set engine wtf|chrome",
        file=sys.stderr,
    )
    return 2


def handle_browser(args, headless: bool = False, engine_mode: str | None = None) -> int:
    """Forward a browser command to the daemon, or print help. Returns the process exit code."""
    if args and args[0] == "config":
        return _handle_config(args)
    from ...useful_tools.browser_tools import engine as browser_engine
    from ...useful_tools.browser_tools.engine_preferences import BrowserEnginePreferenceError
    try:
        selected_engine = browser_engine.normalize_mode(
            engine_mode if engine_mode is not None else _load_default_engine()
        )
    except (browser_engine.BrowserEngineError, BrowserEnginePreferenceError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] == "install-onion":
        if args != ["install-onion"]:
            print("usage: co browser install-onion", file=sys.stderr)
            return 2
        from connectonion.credentials import AmbientCredentialError

        from .onionwright_install import OnionwrightInstallError, install_onionwright

        try:
            result = install_onionwright()
        except (OnionwrightInstallError, AmbientCredentialError) as exc:
            print(f"Could not install Onionwright: {exc}", file=sys.stderr)
            return 1
        if result.already_installed:
            print(f"Onionwright {result.version} is already installed.")
        else:
            print(f"Installed Onionwright {result.version} from the signed OpenOnion release.")
        return 0
    tab, args = _extract_tab(args)
    if args is None:
        print("usage: -t needs a tab name, e.g.  co browser -t mytask go_to <url>", file=sys.stderr)
        return 2
    if not args:
        print("usage: -t targets a command, e.g.  co browser -t mytask go_to <url>", file=sys.stderr)
        return 2
    if args[0] in ("help", "--list", "list"):  # after -t extraction: `-t x help` is still help
        from ..browser_agent.daemon import list_functions
        print(USAGE + "\n\nFunctions:\n" + list_functions())
        return 0
    if args[-1] == "--stdin":
        if args[0] not in ("fill_text_by_selector", "type_text_by_selector", "keyboard_type"):
            print("--stdin is only supported by fill_text_by_selector, type_text_by_selector, and keyboard_type", file=sys.stderr)
            return 2
        if sys.stdin.isatty():
            print("--stdin needs piped or redirected text", file=sys.stderr)
            return 2
        args = [*args[:-1], sys.stdin.read()]
    if selected_engine == browser_engine.CHROME:
        print(f"WARNING: {browser_engine.CHROME_WARNING}", file=sys.stderr)
    code = send(
        shlex.join(args), headless=headless, tab=tab, engine_mode=selected_engine
    )
    if code == 0 and sys.stdout.isatty():
        print(f"\n\033[2m💡 {_next_tip()}\033[0m", file=sys.stderr)
    return code
