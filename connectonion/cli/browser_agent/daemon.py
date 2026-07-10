"""
Purpose: Persistent browser daemon — owns one BrowserAutomation and dispatches CLI verbs to it over a Unix socket.
LLM-Note:
  Dependencies: imports from [socket, os, sys, shlex, inspect, signal, atexit, pathlib, useful_tools.browser_tools.BrowserAutomation, browser_agent.agent (resolve_api_key, build_browser_agent)] | imported by [browser_agent/client.py (spawns via python -m), cli/commands/browser_commands.py (indirectly)] | tested by [tests/e2e/cli/test_cli_browser.py]
  Data flow: client sends one request line over AF_UNIX socket → shlex.split → `status` returns a read-only report (browser state + last command + tabs); otherwise the line is recorded as last_command → first token compared against BrowserAutomation method names → match: coerce args via signature type hints + getattr(browser, verb)(*args) → no match: whole line handed to NL Agent on the same live browser → response "OK\n<payload>" or "ERR\n<message>" written back, connection closed
  State/Effects: single-threaded serial server (sync Playwright requires one thread) | owns one BrowserAutomation for daemon lifetime | tracks last_command (line + timestamp) for `status` | binds AF_UNIX socket at default_sock_path() | daemon exits once an opened browser becomes unusable (close / crash / window shut) | unlinks socket on exit
  Integration: exposes default_sock_path(), BrowserDaemon, main() | launched detached via `python -m connectonion.cli.browser_agent.daemon <sock_path> [--headless]`
  Performance: one request at a time | browser launch overhead on first verb (1-3s) | NL verb builds a fresh Agent per call
  Errors: method exceptions are caught at the dispatch boundary and returned as "ERR\n<message>" (the protocol's purpose) | bind race with a second daemon → loser exits
"""

import os
import sys
import time
import socket
import json
import shlex
import inspect
import signal
import atexit
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_tools.browser_tools.browser import driver_stealth_status
from .agent import resolve_api_key, build_browser_agent


def default_sock_path() -> str:
    """Runtime socket path: $CO_BROWSER_SOCK, else $XDG_RUNTIME_DIR/co, else $TMPDIR/co."""
    override = os.environ.get("CO_BROWSER_SOCK")
    if override:
        return override
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    base = Path(runtime) / "co"
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    return str(base / "browser.sock")


def _coerce(value: str, annotation):
    """Coerce a shell string token to the parameter's annotated type."""
    if annotation is bool:
        return value.lower() in ("1", "true", "yes", "on")
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    return value


def _split_tokens(tokens):
    """Split shell tokens into positional args and --key[=value] kwargs."""
    positional, kwargs = [], {}
    for tok in tokens:
        if tok.startswith("--"):
            key, eq, val = tok[2:].partition("=")
            kwargs[key.replace("-", "_")] = val if eq else True
        else:
            positional.append(tok)
    return positional, kwargs


def _is_verb(browser, name: str) -> bool:
    """True when `name` is a public, callable method on the browser instance."""
    if name.startswith("_"):
        return False
    attr = getattr(browser, name, None)
    return callable(attr)


def signature_str(method) -> str:
    """Render a method's call signature without `self`, e.g. '(url)' or '(path=None, full_page=False)'."""
    parts = []
    for p in inspect.signature(method).parameters.values():
        if p.name == "self":
            continue
        parts.append(p.name if p.default is inspect.Parameter.empty else f"{p.name}={p.default!r}")
    return "(" + ", ".join(parts) + ")"


def list_functions() -> str:
    """One line per public browser function: `name(args) — first docstring line`.

    Introspects the BrowserAutomation class (no browser launched) so the CLI is
    self-describing — an agent can run `co browser help` to discover what it can call.
    """
    lines = []
    for name, method in inspect.getmembers(BrowserAutomation, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        doc = (inspect.getdoc(method) or "").splitlines()
        summary = doc[0] if doc else ""
        lines.append(f"  {name}{signature_str(method)}" + (f" — {summary}" if summary else ""))
    return "\n".join(lines)


class BrowserDaemon:
    """Single-threaded server owning one BrowserAutomation, dispatching verbs to it."""

    def __init__(self, sock_path: str, headless: bool = False):
        self.sock_path = sock_path
        self.browser = BrowserAutomation(headless=headless)
        self._srv = None
        self._had_browser = False
        self.last_command = None  # {"line": str, "at": float} of the last real command
        self.current_session = None  # active tab (session key); None = default/base tab
        self._next_tab = 1           # id allocator for newtab
        self._main_claim = None      # {"caller", "at", "line"}: who is mid-task on the shared main tab

    def dispatch(self, line: str) -> tuple:
        """Run one request. Returns (ok: bool, payload: str)."""
        tokens = shlex.split(line)
        if not tokens:
            return False, "empty request"

        # `%<caller>` (added by the client): who is asking — lets the board show real
        # occupants and lets us detect two agents unknowingly sharing the main tab.
        caller = ""
        if tokens[0].startswith("%") and len(tokens[0]) > 1:
            caller = tokens[0][1:]
            tokens = tokens[1:]
            if not tokens:
                return False, "empty request"
            line = line.split(None, 1)[1]

        # `@<tab> <command>` (the wire form of `co browser -t <tab> ...`): this request
        # drives its OWN tab, without touching the shared active-tab pointer — concurrent
        # clients coexist instead of stomping one page. 'main' is the bare-command
        # default tab; any other name must be registered first via `tab open`.
        session = self.current_session
        if tokens[0].startswith("@") and len(tokens[0]) > 1:
            name = tokens[0][1:]
            tokens = tokens[1:]
            if not tokens:
                return False, "empty request"
            line = line.split(None, 1)[1]
            session = None if name in ("main", "default") else name
            if session is not None and session not in self.browser._tab_meta:
                return 3, self._unknown_tab(name)
        self.browser._bind_session(session)

        verb = tokens[0]
        # Contention guard for the shared main tab: a bare command from a DIFFERENT
        # agent while someone else is mid-task here fails loudly (exit 4) and teaches
        # the tab lifecycle — never silent interleaving on one page.
        if session is None and verb not in ("status", "tab", "close", "help"):
            if caller:
                claim = self._main_claim
                if claim and claim["caller"] != caller and time.time() - claim["at"] < 120:
                    return 4, self._main_busy(claim)
                self._main_claim = {"caller": caller, "at": time.time(), "line": line}
            # main is the zero-ceremony tab: register it implicitly (the claim guard
            # above is its protection) so go_to's who/purpose gate never blocks it.
            self.browser._tab_meta.setdefault(
                None, {"who": caller or "main", "purpose": "shared main tab", "opened_at": datetime.now()}
            )
        if verb == "tab":  # tab lifecycle: open / ls / close
            return self._tab(tokens[1:], caller)
        if verb == "status":  # read-only report; does not count as the last command
            return self._status()
        if verb in ("use", "switch"):  # change the active tab
            return self._use(tokens[1:])
        if verb == "newtab":  # allocate a fresh tab id, then occupy it
            return self._newtab(line, tokens)
        if verb == "closetab":  # close ONE tab, leave the rest of the browser open
            return self._closetab(tokens[1:])

        self.last_command = {"line": line, "at": time.time()}
        meta = self.browser._tab_meta.get(session)
        if meta is not None:  # stamp the board: what this tab last ran, and when
            meta["last_line"], meta["last_at"] = line, time.time()
        if verb == "do":  # explicit natural-language agent
            command = line.split(None, 1)[1] if len(tokens) > 1 else ""
            return self._run_nl(command)
        if _is_verb(self.browser, verb):
            return self._call_verb(verb, tokens[1:])
        return False, (
            f"unknown command: {verb}\n"
            f"Run 'co browser help' to list functions, or "
            f"'co browser do \"<instruction>\"' for natural language."
        )

    def _call_verb(self, verb: str, raw_args) -> tuple:
        """Match the verb to a browser method and execute it with coerced args."""
        method = getattr(self.browser, verb)
        positional, kwargs = _split_tokens(raw_args)

        params = list(inspect.signature(method).parameters.values())
        args = [_coerce(v, params[i].annotation if i < len(params) else str)
                for i, v in enumerate(positional)]
        kw = {}
        param_by_name = {p.name: p for p in params}
        for k, v in kwargs.items():
            ann = param_by_name[k].annotation if k in param_by_name else str
            kw[k] = v if v is True else _coerce(v, ann)

        try:
            result = method(*args, **kw)
        except Exception as exc:  # dispatch boundary: report to client as ERR
            if self.browser._launch_failed():
                # Chrome aborted at startup: str(exc) is a huge patchright "Call log".
                # Keep the first line and point at the full log instead of dumping it.
                first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
                return False, (
                    f"{type(exc).__name__}: {first}\n"
                    f"Chrome failed to start — full log at ~/.co/browser.log.\n"
                    f"On macOS, run `co browser` from a desktop Terminal (a logged-in "
                    f"window session), not over ssh/cron/detached."
                )
            # On wrong arguments, show the expected signature so an agent can self-correct.
            hint = f"\nusage: {verb}{signature_str(method)}" if isinstance(exc, TypeError) else ""
            return False, f"{type(exc).__name__}: {exc}{hint}"

        payload = _stringify(result)
        if payload.startswith("data:image/"):
            # A human at the shell doesn't want a base64 blob — the image is on disk.
            # (The NL agent path keeps the data URL for vision; it goes through _run_nl.)
            return True, f"Screenshot saved to: {self.browser.last_screenshot_path}"
        return True, payload

    def _status(self) -> tuple:
        """Report browser state, the active tab, the last command, and open tabs."""
        open_state = "open" if self.browser._browser_is_usable() else "not open"
        headless = str(getattr(self.browser, "_headless", False)).lower()
        cur = "default" if self.current_session is None else self.current_session
        lines = [f"Browser: {open_state} · headless={headless} · active tab={cur}"]
        # Surface stealth-driver health here so a misconfigured driver (webdriver leak) is
        # visible where users look for browser state, not only in `co doctor`.
        stealth, version, detail = driver_stealth_status()
        mark = {"ok": "✓", "broken": "✗", "missing": "○"}[stealth]
        lines.append(f"Stealth driver: {mark} patchright {version} — {detail}".rstrip(" —"))
        if self.last_command:
            lines.append(f'Last command: "{self.last_command["line"]}" · {_ago(time.time() - self.last_command["at"])}')
        else:
            lines.append("Last command: (none yet)")
        lines.append("")
        lines.append(self.browser.tab_status())
        return True, "\n".join(lines)

    def _tab(self, args, caller: str = "") -> tuple:
        """Tab lifecycle: `tab open [NAME] [--who X] [--for "..."]` · `tab ls [--json]` · `tab close NAME`."""
        if not args:
            return False, self._tab_usage()
        action, rest = args[0], args[1:]
        if action == "open":
            return self._tab_open(rest, caller)
        if action in ("ls", "list"):
            if "--json" in rest:
                board = [
                    {"tab": "main" if k is None else k, **{f: m.get(f) for f in ("who", "purpose", "last_line", "last_at")}}
                    for k, m in self.browser._tab_meta.items()
                ]
                return True, json.dumps(board)
            return self._status()
        if action == "close":
            return self._closetab(rest)
        return False, self._tab_usage()

    def _tab_open(self, rest, caller: str = "") -> tuple:
        """Register a named tab (page is created lazily on its first command). Prints ONLY the name."""
        name, who, purpose = "", "", ""
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in ("--who", "--for") and i + 1 < len(rest):
                i += 1
                if tok == "--who":
                    who = rest[i]
                else:
                    purpose = rest[i]
            elif tok.startswith("--who="):
                who = tok.split("=", 1)[1]
            elif tok.startswith("--for="):
                purpose = tok.split("=", 1)[1]
            elif not tok.startswith("-") and not name:
                name = tok
            i += 1
        name = name or f"t-{self._next_tab}"
        self._next_tab += 1
        if name in ("main", "default"):
            return False, "'main' is the shared default tab — it always exists; just run commands without -t."
        self.browser._tab_meta.setdefault(
            name, {"who": who or caller or name, "purpose": purpose or name, "opened_at": datetime.now()}
        )
        return True, name

    def _tab_usage(self) -> str:
        return (
            "usage: co browser tab open [NAME] [--who <agent>] [--for \"<purpose>\"]   # register; prints the name\n"
            "       co browser tab ls [--json]                                        # who runs where\n"
            "       co browser tab close <NAME>                                       # release when done\n"
            "then target your tab on EVERY command, including do:\n"
            "       co browser -t <NAME> <verb> [args]"
        )

    def _main_busy(self, claim) -> str:
        """Error-as-documentation: another agent owns main right now — get your own tab."""
        ago = _ago(time.time() - claim["at"])
        return (
            f"tab 'main' is in use by {claim['caller']} — last: \"{claim['line'][:60]}\" · {ago}\n\n"
            f"You are a second agent on this browser. Two agents cannot share one tab.\n"
            f"Run your task in your own tab — three commands:\n"
            f"  1. co browser tab open <name> --who <your-name> --for \"<what you are doing>\"\n"
            f"  2. co browser -t <name> <verb> [args]      # add -t <name> to EVERY command, including do\n"
            f"  3. co browser tab close <name>             # when your task is done\n\n"
            f"see who owns what:  co browser tab ls"
        )

    def _unknown_tab(self, name: str) -> str:
        """Error-as-documentation: list what exists and teach the full tab lifecycle."""
        return (
            f"no tab named '{name}'\n\n"
            f"{self.browser.tab_status()}\n\n"
            f"create it first:  co browser tab open {name} --who <your-name> --for \"<one-line purpose>\"\n"
            f"then target it on every command, including do:\n"
            f"                  co browser -t {name} <verb> [args]\n"
            f"when finished:    co browser tab close {name}"
        )

    def _use(self, args) -> tuple:
        """Switch the active tab that subsequent commands operate on."""
        if not args:
            return False, "usage: use <tab>   (a tab id from `co browser status`, or 'default')"
        target = args[0]
        key = None if target in ("default", "none") else target
        if key is not None and key not in self.browser._pages:
            return False, f"unknown tab: {target}. Run 'co browser status' to list tabs."
        self.current_session = key
        self.browser._bind_session(key)
        return True, f"Switched to tab {target}."

    def _newtab(self, line, tokens) -> tuple:
        """Bind a fresh session key, then occupy a new tab via BrowserAutomation.newtab."""
        prev = self.current_session
        key = str(self._next_tab)
        self._next_tab += 1
        self.current_session = key
        self.browser._bind_session(key)
        self.last_command = {"line": line, "at": time.time()}
        ok, payload = self._call_verb("newtab", tokens[1:])
        if not ok:                      # creation refused (missing who/purpose) → roll back
            self.current_session = prev
            self.browser._bind_session(prev)
            return False, payload
        return True, f"[tab {key}] {payload}"

    def _closetab(self, args) -> tuple:
        """Close ONE tab, leaving the rest of the browser open."""
        if not args:
            return False, "usage: closetab <tab>   (a tab id from `co browser status`)"
        target = args[0]
        key = None if target in ("default", "none", "main") else target
        if key not in self.browser._pages and key not in self.browser._tab_meta:
            return False, f"unknown tab: {target}. Run 'co browser tab ls' to list tabs."
        self.last_command = {"line": "closetab " + target, "at": time.time()}
        # A tab registered via `tab open` but never navigated has meta and no page —
        # releasing it is just dropping the registration.
        message = self.browser.close_tab(key) if key in self.browser._pages else "Tab released"
        self.browser._tab_meta.pop(key, None)
        if self.current_session == key:                       # closed the active tab
            remaining = list(self.browser._pages)             # live tabs after the close
            self.current_session = remaining[0] if remaining else None
            self.browser._bind_session(self.current_session)
        return True, f"Closed tab {target}. {message}"

    def _run_nl(self, command: str) -> tuple:
        """Hand the command to the NL agent driving the same live browser."""
        api_key = resolve_api_key()
        if not api_key:
            return False, "Browser agent requires authentication. Run: co auth"
        try:
            result = build_browser_agent(self.browser, api_key).input(command)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, _stringify(result)

    def serve(self):
        self._bind()
        atexit.register(self._cleanup)
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

        while True:
            conn, _ = self._srv.accept()
            try:
                request = _recv_all(conn).decode().strip()
                ok, payload = self.dispatch(request)
                # ok is True, False, or an int error code (3 = unknown tab, 4 = tab busy)
                # so orchestrating agents can branch on the exit code without parsing prose.
                header = "OK" if ok is True else ("ERR" if ok is False else f"ERR {ok}")
                conn.sendall((header + "\n" + payload).encode())
            except (BrokenPipeError, ConnectionResetError):
                # The client died mid-request (bash timeout, Ctrl-C). Its death must not
                # kill the daemon: before this catch, sendall() raised, serve() unwound,
                # and atexit closed the whole browser — one impatient client destroyed
                # every other client's session.
                pass
            finally:
                conn.close()

            usable = self.browser._browser_is_usable()
            self._had_browser = self._had_browser or usable
            # Exit (releasing the socket) when the browser can no longer be driven, so the
            # next command spawns a fresh daemon instead of reusing a dead one. Two cases:
            #   - a launch that never produced a context (Chrome aborted at startup) — a
            #     daemon that can't open a browser must not linger as a socket-holding zombie;
            #   - a browser that was usable and has since closed/crashed.
            if self.browser._launch_failed() or (self._had_browser and not usable):
                break

    def _bind(self):
        """Bind the socket, yielding to any daemon that already owns it."""
        if os.path.exists(self.sock_path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(self.sock_path)
                probe.close()
                sys.exit(0)  # another daemon already serving
            except OSError:
                os.unlink(self.sock_path)  # stale socket
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.sock_path)
        self._srv.listen(8)

    def _cleanup(self):
        self.browser.close()
        if self._srv:
            self._srv.close()
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)


def _ago(seconds: float) -> str:
    """Render an elapsed duration as a compact 'Xs/Xm/Xh/Xd ago' string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _recv_all(conn) -> bytes:
    """Read until the client half-closes (EOF)."""
    chunks = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _stringify(result) -> str:
    """Methods return str or list[str]; lists print one item per line for piping."""
    if isinstance(result, list):
        return "\n".join(str(x) for x in result)
    return "" if result is None else str(result)


def main():
    sock_path = sys.argv[1] if len(sys.argv) > 1 else default_sock_path()
    headless = "--headless" in sys.argv[2:]
    BrowserDaemon(sock_path, headless=headless).serve()


if __name__ == "__main__":
    main()
