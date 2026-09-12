"""
Purpose: Thin CLI handler for `co browser` — parses -t/--tab targeting, forwards one command to the persistent browser daemon, and serves self-describing help.
LLM-Note:
  Dependencies: imports from [sys, shlex, browser_agent.client.send | lazy: command_tips.rotating_tip for the success tip, browser_agent.daemon.list_functions for help] | imported by [cli/main.py via browser()] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: receives args: list[str] (+ headless and engine_mode) from CLI → validates auto/system/onion → `install-onion` (alone or with --break-system-packages) runs the signed private-client bootstrap and returns before daemon contact → `help`/`--list` printed locally by introspecting BrowserAutomation (no browser launched) → else _extract_tab() pulls the LEADING -t/--tab NAME run (stops at the verb, so a -t that is a function's own arg passes through; empty --tab= is a usage error) → shlex.join(remaining args) + tab + engine mode → client.send() → a mode-pinned daemon runs it → payload/exit code surfaced by the client
  State/Effects: `install-onion` explicitly installs a signature/checksum-verified wheel into the current Python environment, and on an externally-managed interpreter says so and names the opt-in flag rather than reporting an exit code | otherwise no local state except a best-effort rotating-tip index at ~/.co/.browser_tip (a garbled index resets to the first tip) | a session-starting verb on the paid engine prints a billing notice to STDERR BEFORE the command is sent | the success tip is printed to STDERR (stdout stays pure data) | `help` introspects the class only | direct verbs delegate to the daemon; `do` runs its model loop in this CLI process and delegates each tool call
  Integration: exposes _extract_tab(args) -> (tab|None, remaining|None), _next_tip(), handle_browser(args, headless=False, engine_mode="auto") -> int | called from main.py browser command | USAGE/TIPS document the tab lifecycle, engine modes, and exit-code contract
  Performance: direct verbs do not import the browser-owning daemon, Agent, or Playwright; `help` lazily imports the schema (no socket, no Chrome) | other verbs: one socket round-trip, first call spawns the daemon
  Errors: no-args / bad -t → prints usage to stderr, exit 2 | daemon errors come back as ERR[ <code>] → stderr + the mirrored exit code (0 ok · 1 failure · 2 usage · 3 unknown tab · 4 tab busy)
"""

import shlex
import sys

from ..browser_agent.client import send

USAGE = (
    "co browser — drive one persistent browser from the shell\n"
    "\n"
    "  co browser [-t TAB] <function> [args]    run a browser function (bare = the shared 'main' tab)\n"
    "  co browser --engine wtf <function> [args]     pay for the WTF Browser (default: system Chrome)\n"
    "  co browser config wtf                     make the WTF Browser this machine's default\n"
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
    "The browser stays open between commands, one shared session, until you run:  co browser close",
]


def _starts_a_session(args: list) -> bool:
    """True for the verbs that open a browser, i.e. that begin a paid interval."""
    return args[0] in ("newtab", "open_browser") or args[:2] == ["tab", "open"]


def _next_tip():
    """Rotate through TIPS so each run teaches something new; cursor at ~/.co/.browser_tip."""
    from .command_tips import rotating_tip
    return rotating_tip("browser", TIPS)


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


def handle_browser(args, headless: bool = False, engine_mode: str = "auto") -> int:
    """Forward a browser command to the daemon, or print help. Returns the process exit code."""
    # `wtf` is what a person types and what effective_mode() returns; `onion`
    # is what the daemon protocol calls the same engine. Translated here, at
    # the one boundary between the two, rather than in either of them.
    if engine_mode == "wtf":
        engine_mode = "onion"
    if engine_mode not in ("auto", "system", "onion"):
        print("--engine must be one of: auto, system, wtf", file=sys.stderr)
        return 2
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] == "install-onion":
        # The flag is opt-in and named after pip's own, because it overrides a
        # policy the OS set on its interpreter. The failure message is where a
        # caller learns it exists; nothing chooses it for them.
        rest = args[1:]
        override = rest == ["--break-system-packages"]
        if rest and not override:
            print(
                "usage: co browser install-onion [--break-system-packages]",
                file=sys.stderr,
            )
            return 2
        from connectonion.credentials import AmbientCredentialError

        from .onionwright_install import OnionwrightInstallError, install_onionwright

        try:
            result = install_onionwright(break_system_packages=override)
        except (OnionwrightInstallError, AmbientCredentialError) as exc:
            print(f"Could not install Onionwright: {exc}", file=sys.stderr)
            return 1
        if result.already_installed:
            print(f"Onionwright {result.version} is already installed.")
        else:
            print(f"Installed Onionwright {result.version} from the signed OpenOnion release.")
        print("Use it:  co browser --engine wtf <function> [args]", file=sys.stderr)
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
        print("\nRun one directly:  co browser <function> [args]", file=sys.stderr)
        return 0
    if args[-1] == "--stdin":
        if args[0] not in ("fill_text_by_selector", "type_text_by_selector", "keyboard_type"):
            print("--stdin is only supported by fill_text_by_selector, type_text_by_selector, and keyboard_type", file=sys.stderr)
            return 2
        if sys.stdin.isatty():
            print("--stdin needs piped or redirected text", file=sys.stderr)
            return 2
        args = [*args[:-1], sys.stdin.read()]
    if engine_mode == "onion" and _starts_a_session(args):
        # Before the spend, not in the receipt. The Airbnb round of 2026-09-12
        # ran an authenticated host dashboard on the paid engine for 40 minutes,
        # then finished the same work on the free one with the logins intact —
        # nothing anywhere had said which engine was about to bill (#1510).
        print(
            "⏱  The WTF Browser bills for the session this starts.\n"
            "   A site you are already logged into rarely needs it:  "
            "co browser --engine system <verb>",
            file=sys.stderr,
        )
    code = send(shlex.join(args), headless=headless, tab=tab, engine_mode=engine_mode)
    from .command_tips import tips_enabled
    if code == 0 and tips_enabled():
        # Not gated on a terminal: an agent captures stdout, and it is the
        # reader this tip exists for. stderr keeps stdout pure data.
        tip = f"💡 {_next_tip()}"
        if sys.stderr.isatty():
            tip = f"\033[2m{tip}\033[0m"
        print(f"\n{tip}", file=sys.stderr)
    return code
