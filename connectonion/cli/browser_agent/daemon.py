"""
Purpose: Persistent browser daemon — owns one BrowserAutomation and dispatches CLI requests to it over the platform transport (POSIX Unix socket / Windows named pipe), arbitrating concurrent agents through per-tab ownership.
LLM-Note:
  Dependencies: imports from [socket, os, sys, time, json, shlex, inspect, signal, atexit, threading, datetime, pathlib, useful_tools.browser_tools.BrowserAutomation, useful_tools.browser_tools.browser.driver_stealth_status, browser_agent.agent (resolve_api_key, build_browser_agent), browser_agent.transport] | imported by [browser_agent/client.py (spawns via python -m), cli/commands/browser_commands.py (list_functions)] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: client sends ONE request = wire-v1 JSON envelope {v, caller, tab, line} (a bare string is accepted as an anonymous main-tab request) → _parse_envelope → shlex.split(line) → dispatch: `tab`/`status`/`use`/`newtab`/`closetab` route first; a -t target that is not `main`/registered is exit 3 unless the verb is READONLY → an unknown verb is rejected BEFORE any claim → page-driving verbs and a targeted `close` pass _register_tab + _held_by_other (exit-4-busy if a DIFFERENT identity holds the tab within GUARD_WINDOW, 120s) then _stamp_claim → `do` hands the parsed instruction to the NL Agent on the same live browser; a matched method is called via getattr(browser, verb)(*coerced args); an unmatched verb returns "unknown command" (it is NOT auto-run as NL — only `do` is) → reply "OK\n<payload>" | "ERR\n<msg>" | "ERR <code>\n<msg>" (code ∈ {2 usage,3 unknown tab,4 busy}) written back, connection closed
  State/Effects: single-threaded serial server (sync Playwright requires one thread) | owns one BrowserAutomation for daemon lifetime | the tab REGISTRY + claims live on browser._tab_meta[key] (key None = shared 'main'): who/purpose/opened_at/caller/claim_at/last_line/last_at | tracks last_command for `status` | binds the endpoint at default_sock_path() via `transport` — POSIX: a raw AF_UNIX socket (unchanged); Windows: a native named pipe (multiprocessing.connection) with an HMAC authkey — under a lifetime OS lock (transport.lock_path: fcntl.flock POSIX / msvcrt Windows, released by the OS on any death, so simultaneous cold-starts can't both bind) and records its owner pid in transport.pid_path so a refused probe can tell busy from stale; 120s per-connection recv timeout | _cleanup closes the listener (POSIX also unlinks the socket) + pidfile only while the pidfile still names this process (browser teardown is the driver pipe closing on process death — the executor is already gone when atexit runs) | serve() exits (releasing the endpoint) when browser._context_is_alive() goes false or _launch_failed()
  Integration: exposes default_sock_path(), signature_str(), list_functions(), BrowserDaemon, main() | launched detached via `python -m connectonion.cli.browser_agent.daemon <sock_path> [--headless]` | module helpers _key()/_tab_label()/_held_by_other()/_owner_alive() define the None↔main aliasing, the shared claim-expiry predicate (dispatch, _tab_open, _closetab), and the socket-owner liveness check (client + _bind)
  Performance: one request at a time | browser launch overhead on first page verb (1-3s) | `do` builds a fresh Agent per call | tab lifecycle/status verbs never launch Chrome
  Errors: dispatch/handler exceptions are caught at the request boundary in serve() and returned to THAT client (never unwind the loop and kill the shared browser) | a client that vanishes mid-reply is logged to ~/.co/browser.log, not fatal | bind race with a second daemon → loser exits
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
import threading
from datetime import datetime
from pathlib import Path

from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_tools.browser_tools.browser import driver_stealth_status
from .agent import resolve_api_key, build_browser_agent
from . import transport


def default_sock_path() -> str:
    """The daemon endpoint address (cross-platform).

    POSIX: a Unix-socket path ($CO_BROWSER_SOCK, else $XDG_RUNTIME_DIR/co, else $TMPDIR/co).
    Windows: a per-user named pipe. See transport.default_address().
    """
    return transport.default_address()


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


GUARD_WINDOW = 120  # seconds a tab's last claim keeps excluding other callers


def _key(name):
    """Canonical session key — the shared main tab is stored as None."""
    return None if name in (None, "main", "default", "none") else name


def _tab_label(key) -> str:
    return "main" if key is None else key


def _owner_alive(sock_path: str) -> bool:
    """True when the daemon that bound `sock_path` is still a running process.
    No pid file (pre-pidfile daemon, or already cleaned up) reads as dead."""
    pid_file = Path(transport.pid_path(sock_path))
    if not pid_file.exists():
        return False
    raw = pid_file.read_text().strip()
    if not raw.isdigit():
        return False
    return transport.pid_alive(int(raw))


def _held_by_other(meta, caller: str) -> bool:
    """True when this tab carries a live claim (within GUARD_WINDOW) by a DIFFERENT
    identity than `caller`. An anonymous request (caller="") is still held OUT of a
    named claim; two anonymous requests cannot be told apart, so they are not guarded."""
    holder = meta.get("caller")
    return bool(holder and holder != caller and time.time() - (meta.get("claim_at") or 0) < GUARD_WINDOW)


class BrowserDaemon:
    """Single-threaded server owning one BrowserAutomation, dispatching verbs to it."""

    def __init__(self, sock_path: str, headless: bool = False):
        self.sock_path = sock_path
        self.browser = BrowserAutomation(headless=headless)
        self._srv = None
        self._had_browser = False
        self.last_command = None  # {"line": str, "at": float} of the last real command
        self._next_tab = 1        # id allocator for auto-named tabs

    def _parse_envelope(self, raw: str) -> tuple:
        """Wire v1: one JSON object {"caller","tab","line"} — quote-safe by construction
        (a caller or tab name can hold any character without breaking shlex). A plain
        line (old client) is accepted as an anonymous request for the main tab."""
        if not raw.startswith("{"):
            return "", None, raw
        req = json.loads(raw)
        tab = req.get("tab")
        return str(req.get("caller") or ""), (str(tab) if tab is not None else None), str(req.get("line") or "")

    # Verbs that neither drive nor destroy a page: never guarded, and a not-yet-registered
    # -t target is fine (you may inspect or create it). `help` never reaches the daemon —
    # the CLI answers it locally.
    READONLY = ("tab", "status", "use", "switch")

    def dispatch(self, raw: str) -> tuple:
        """Run one request. Returns (ok, payload); ok is True, False, or an int error
        code the client mirrors into its exit (2 usage · 3 unknown tab · 4 tab busy)."""
        try:
            caller, tab, line = self._parse_envelope(raw)
            tokens = shlex.split(line)
        except (ValueError, TypeError) as exc:  # malformed envelope/quoting is the CLIENT's error
            return 2, f"unparseable request: {exc}"
        if not tokens:
            return 2, "empty request"
        verb = tokens[0]

        # -t targeting: each task drives its OWN tab. Unknown-tab is only an error for a
        # command that would DRIVE the tab — read-only/lifecycle verbs may name a tab that
        # is not registered yet (to inspect it, or `tab open` it).
        session = _key(tab)
        if session is not None and session not in self.browser._tab_meta and verb not in self.READONLY:
            return 3, self._unknown_tab(session)
        self.browser._bind_session(session)

        if verb == "tab":  # tab lifecycle: open / ls / close
            return self._tab(tokens[1:], caller)
        if verb == "status":  # read-only report; does not count as the last command
            return self._status()
        if verb in ("use", "switch"):  # removed: no server-side cursor, targeting is per-command
            return False, "use/switch removed — target a tab per command instead:  co browser -t <tab> <verb>"
        if verb == "newtab":  # legacy spelling of `tab open` + go_to
            if session is not None:  # it allocates its OWN tab — a -t target would be ignored
                return 2, "newtab allocates its own tab and ignores -t — use:  co browser tab open <name>, then  co browser -t <name> go_to <url>"
            return self._newtab(line, tokens, caller)
        if verb == "closetab":  # legacy spelling of `tab close`
            return self._closetab(tokens[1:], caller)

        # `close` with no -t is a deliberate whole-browser shutdown (unguarded). `-t X close`
        # closes ONE tab and so must pass the same ownership guard as any destructive write.
        if verb == "close" and session is None:
            return self._call_verb("close", tokens[1:])

        # A command that would execute nothing must not acquire anything: reject an
        # unknown verb BEFORE the claim, or a typo would hold the tab for GUARD_WINDOW.
        if verb != "do" and not _is_verb(self.browser, verb):
            return False, (
                f"unknown command: {verb}\n"
                f"Run 'co browser help' to list functions, or "
                f"'co browser do \"<instruction>\"' for natural language."
            )

        # Every page-driving command (and a targeted close) claims its tab: a DIFFERENT
        # agent mid-task there fails loudly (exit 4) and is taught the tab lifecycle —
        # never silent interleaving on one page.
        meta = self._register_tab(session, caller)
        if _held_by_other(meta, caller):
            return 4, self._tab_busy(session, meta)
        self._stamp_claim(meta, caller, line)
        self.last_command = {"line": line, "at": time.time()}
        if verb == "do":  # explicit natural-language agent — use the PARSED remainder,
            command = " ".join(tokens[1:])  # not the still-quoted raw line
            return self._run_nl(command)
        return self._call_verb(verb, tokens[1:])

    def _register_tab(self, key, caller: str) -> dict:
        """Return the tab's board entry, creating the shared main tab's on first use.

        The default who/purpose deliberately satisfies go_to's occupancy ceremony,
        which is the DIRECT-API declaration layer. Through the daemon, declaring
        happens at the tab layer instead (`tab open --who/--for`; bare main needs
        no ceremony, per docs). A named -t target was validated before this point."""
        return self.browser._tab_meta.setdefault(
            key, {"who": caller or "main",
                  "purpose": "shared main tab" if key is None else key,
                  "opened_at": datetime.now()}
        )

    def _stamp_claim(self, meta: dict, caller: str, line: str) -> None:
        """Record who is driving the tab right now. Only a NAMED caller holds a claim
        (two anonymous callers can't be told apart); each successful command refreshes
        it, so an active owner is never expired out from under a running task."""
        if caller:
            if meta.get("caller") != caller:
                meta["who"] = caller  # takeover after expiry: the board shows the current occupant
            meta["caller"], meta["claim_at"] = caller, time.time()
        meta["last_line"], meta["last_at"] = line, time.time()

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
        """Report browser state, the last command, and the tab board."""
        open_state = "open" if self.browser._context_is_alive() else "not open"
        headless = str(getattr(self.browser, "_headless", False)).lower()
        lines = [f"Browser: {open_state} · headless={headless} · targeting is per-command (-t <tab>; bare = main)"]
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
            return 2, self._tab_usage()
        action, rest = args[0], args[1:]
        if action == "open":
            return self._tab_open(rest, caller)
        if action in ("ls", "list"):
            if "--json" in rest:
                board = [
                    {"tab": _tab_label(k), **{f: m.get(f) for f in ("who", "purpose", "last_line", "last_at")}}
                    for k, m in self.browser._tab_meta.items()
                ]
                return True, json.dumps(board)
            return self._status()
        if action == "close":
            return self._closetab(rest, caller)
        return 2, self._tab_usage()

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
        if not name:  # auto-name only when none given; guarantee it is fresh
            while f"t-{self._next_tab}" in self.browser._tab_meta:
                self._next_tab += 1
            name = f"t-{self._next_tab}"
            self._next_tab += 1
        if _key(name) is None:
            return 2, "'main' is the shared default tab — it always exists; just run commands without -t."
        existing = self.browser._tab_meta.get(name)
        if existing is not None:
            if not _held_by_other(existing, caller):
                # yours, or the previous owner's claim has expired → (re)claim the name
                existing.update(who=who or caller or name, purpose=purpose or existing.get("purpose") or name,
                                caller=caller, claim_at=time.time() if caller else 0)
                return True, name
            # A DIFFERENT agent is mid-task under this name: sharing would collide.
            return 4, self._tab_busy(name, existing) + "\n\nor pick a different name for your own tab."
        self.browser._tab_meta[name] = {
            "who": who or caller or name, "purpose": purpose or name,
            "opened_at": datetime.now(), "caller": caller, "claim_at": time.time() if caller else 0,
        }
        return True, name

    def _tab_usage(self) -> str:
        return (
            "usage: co browser tab open [NAME] [--who <agent>] [--for \"<purpose>\"]   # register; prints the name\n"
            "       co browser tab ls [--json]                                        # who runs where\n"
            "       co browser tab close <NAME>                                       # release when done\n"
            "then target your tab on EVERY command, including do:\n"
            "       co browser -t <NAME> <verb> [args]"
        )

    def _tab_busy(self, key, meta) -> str:
        """Error-as-documentation: another agent owns this tab right now — get your own."""
        who = meta.get("who") or meta.get("caller") or "someone"
        last = (meta.get("last_line") or "")[:60]
        ago = _ago(time.time() - (meta.get("claim_at") or meta.get("last_at") or time.time()))
        return (
            f"tab '{_tab_label(key)}' is in use by {who} — last: \"{last}\" · {ago}\n\n"
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

    def _newtab(self, line, tokens, caller: str = "") -> tuple:
        """Legacy `newtab <url> --purpose=.. --who=..`: register + occupy a fresh tab.
        Unlike the old behavior it does NOT repoint what bare commands target."""
        # A numeric id can collide with a NAME someone registered via `tab open` —
        # skip taken keys or this would occupy another agent's live tab.
        while str(self._next_tab) in self.browser._tab_meta:
            self._next_tab += 1
        key = str(self._next_tab)
        self._next_tab += 1
        self.browser._bind_session(key)
        self.last_command = {"line": line, "at": time.time()}
        ok, payload = self._call_verb("newtab", tokens[1:])
        if not ok:
            return False, payload
        meta = self.browser._tab_meta.get(key)
        if meta is not None and caller:
            meta["caller"], meta["claim_at"] = caller, time.time()
        return True, f"[tab {key}] {payload}"

    def _closetab(self, args, caller: str = "") -> tuple:
        """Close ONE tab, leaving the rest of the browser open."""
        if not args:
            return 2, "usage: co browser tab close <tab>   (a name from `co browser tab ls`)"
        target = args[0]
        key = _key(target)
        meta = self.browser._tab_meta.get(key)
        if key not in self.browser._pages and meta is None:
            if key is None:  # main always exists conceptually; nothing to release is fine
                return True, "main is already free — nothing to close."
            return 3, self._unknown_tab(target)
        # Closing someone's mid-task tab is the most destructive write there is —
        # it gets the same guard as driving the page (and blocks anonymous callers too).
        if meta and _held_by_other(meta, caller):
            return 4, self._tab_busy(key, meta)
        self.last_command = {"line": "closetab " + target, "at": time.time()}
        # close_tab releases the page, the registration (claim included), AND the
        # remembered URL — a later tab reusing this name must start blank, never
        # on the previous owner's page.
        message = self.browser.close_tab(_tab_label(key))
        return True, f"Closed tab {_tab_label(key)}. {message}"

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
            conn = self._accept()
            if conn is None:
                continue  # a client that failed the auth handshake (Windows) — keep serving
            request = ""
            try:
                request = self._read_request(conn)  # a client that connects then stalls
                if request is None:                  # must not wedge the single-threaded daemon
                    conn.close()
                    continue
                ok, payload = self.dispatch(request)
            except Exception as exc:
                # Request boundary: one bad request (malformed envelope, encoding, an
                # unexpected dispatch bug) is reported to ITS client — it must never
                # unwind serve() and take the shared browser down with it.
                ok, payload = False, f"{type(exc).__name__}: {exc}"
            try:
                # ok is True, False, or an int error code (2/3/4) so orchestrating
                # agents can branch on the exit code without parsing prose.
                header = "OK" if ok is True else ("ERR" if ok is False else f"ERR {ok}")
                self._send_reply(conn, (header + "\n" + payload).encode())
            except (BrokenPipeError, ConnectionResetError, socket.timeout, EOFError):
                # The client died or stalled mid-reply (bash timeout, Ctrl-C; on Windows
                # socket.timeout IS TimeoutError, which bounded_io raises for a reader
                # that stopped consuming). Its death must not kill the daemon — log the
                # drop (stderr goes to ~/.co/browser.log) so "my command printed
                # nothing" stays diagnosable. Any OTHER OSError is a daemon-side fault
                # and propagates: a broken daemon must die and be respawned, not loop.
                print(f"client vanished before reply: {request[:80]!r}", file=sys.stderr)
            finally:
                conn.close()

            # Exit (releasing the socket) when the browser can no longer be driven, so the
            # next command spawns a fresh daemon instead of reusing a dead one. This is a
            # SHARED-context decision, not a per-session one: a command on a page-less tab
            # must not be read as "browser dead" and tear down every other session's tabs.
            alive = self.browser._context_is_alive()
            self._had_browser = self._had_browser or alive
            #   - a launch that never produced a context (Chrome aborted at startup) — a
            #     daemon that can't open a browser must not linger as a socket-holding zombie;
            #   - a context that was alive and has since closed/crashed.
            if self.browser._launch_failed() or (self._had_browser and not alive):
                break

    def _bind(self):
        """Bind the socket, yielding to any daemon that already owns it.

        The whole probe-and-bind sequence runs under an exclusive flock on
        <sock>.lock, held for the daemon's LIFETIME and released by the kernel on
        any exit (SIGKILL included). Two daemons cold-starting together — two
        terminals' first commands — otherwise both pass the stale check and the
        loser unlinks the winner's live socket (reproduced in practice). The lock
        file itself is never unlinked: removing it would let a third daemon lock a
        fresh inode while a second still holds the old one.

        A refused probe is ambiguous: the owner died leaving a stale socket, OR the
        owner is alive with a full backlog (a long `do` while clients hammer it — the
        exact situation that spawns us). Unlinking a BUSY daemon's socket forks the
        world: two daemons, two Chromes fighting over one profile, and the original
        becomes an unreachable zombie. The pid file the owner wrote at bind time
        tells the two apart.

        The lifetime lock, pid-file location, and (on Windows) the named-pipe wire live
        behind `transport` so POSIX behavior is byte-identical while Windows gets native
        named pipes with an HMAC-authenticated handshake."""
        self._bind_lock = transport.acquire_singleton_lock(transport.lock_path(self.sock_path))
        if self._bind_lock is None:
            sys.exit(0)  # another daemon is binding or already serving
        if transport.IS_WINDOWS:
            self._authkey = transport.load_or_create_authkey()  # the pipe wire's HMAC secret
            self._bind_windows()
        else:
            self._bind_posix()

    def _bind_posix(self):
        """Raw AF_UNIX bind with the original stale-vs-busy probe (unchanged)."""
        if os.path.exists(self.sock_path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(self.sock_path)
                probe.close()
                sys.exit(0)  # another daemon already serving
            except OSError:
                if _owner_alive(self.sock_path):
                    sys.exit(0)  # owner alive, backlog full — busy, not stale
                os.unlink(self.sock_path)  # stale socket
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.sock_path)
        Path(transport.pid_path(self.sock_path)).write_text(str(os.getpid()))
        self._srv.listen(8)

    def _bind_windows(self):
        """Named-pipe bind. A pipe vanishes WITH its owning process, so 'no pipe' is
        definitive death: a leftover pid file (Task-Manager kill skips _cleanup) must
        never block binding — Windows recycles pids aggressively, so a reused pid
        would otherwise read as a live owner forever."""
        try:
            probe = transport.win_connect(self.sock_path, self._authkey)
            probe.close()
            sys.exit(0)  # another daemon already serving
        except transport.AuthenticationError:
            sys.exit(0)  # a daemon is there (key mismatch) — never double-bind
        except FileNotFoundError:
            pass  # no pipe = no daemon; any pid file is a stale leftover — bind over it
        except (ConnectionError, OSError):
            if _owner_alive(self.sock_path):
                sys.exit(0)  # pipe exists and its owner is alive — busy, not stale
        try:
            self._srv = transport.win_listener(self.sock_path)
        except PermissionError:
            # First-instance pipe creation refused: another daemon owns the name after
            # all (probe raced its accept loop). Yield, exactly like the POSIX loser.
            sys.exit(0)
        Path(transport.pid_path(self.sock_path)).write_text(str(os.getpid()))

    # ---- transport seam: POSIX raw AF_UNIX socket vs Windows named-pipe Connection ----

    def _accept(self):
        """Accept one client. Windows hands back only AUTHENTICATED connections — the
        HMAC challenge runs deadline-bounded in transport.accept_authenticated (mpc's
        own accept()-time handshake blocks forever on a stalled client), and a failed
        handshake returns None instead of killing the single-threaded loop. A dead
        listener still raises out on both platforms so a dying daemon exits."""
        if transport.IS_WINDOWS:
            return transport.accept_authenticated(self._srv, self._authkey)
        conn, _ = self._srv.accept()
        return conn

    def _read_request(self, conn) -> str:
        """Read one request with EVERY blocking step bounded at 120s — waiting for the
        request, and (Windows) a partial frame from a stalled client. Returns the
        text, or None when the client stalled or vanished."""
        if transport.IS_WINDOWS:
            try:
                return transport.bounded_io(conn, conn.recv_bytes, 120).decode().strip()
            except (TimeoutError, EOFError):
                return None  # stalled mid-frame, or died before sending
        conn.settimeout(120)
        try:
            return _recv_all(conn).decode().strip()
        except socket.timeout:
            return None

    def _send_reply(self, conn, data: bytes):
        """Send one reply. POSIX inherits the 120s settimeout; the Windows pipe has no
        native send deadline, so a stalled-but-alive reader (full pipe) is bounded the
        same way — the daemon must never wedge on a client that stopped reading."""
        if transport.IS_WINDOWS:
            transport.bounded_io(conn, lambda: conn.send_bytes(data), 120)
        else:
            conn.sendall(data)

    def _cleanup(self):
        # Stop accepting FIRST: closing/unlinking the socket before anything slow
        # means a client connecting during shutdown fails immediately and spawns
        # a fresh daemon, instead of reaching a daemon that will never accept its request.
        if self._srv:
            self._srv.close()  # on Windows, mpc.Listener.close() removes the pipe itself
        # Only remove what is still OURS (pid file names this process): a successor
        # daemon may already own the path — a late-exiting zombie deleting the live
        # socket or pid file would re-arm the very bug the pid file exists to prevent.
        pid_file = Path(transport.pid_path(self.sock_path))
        if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
            if not transport.IS_WINDOWS and os.path.exists(self.sock_path):
                os.unlink(self.sock_path)  # POSIX: remove our socket file (mpc did it on Win)
            pid_file.unlink()
        # No browser.close() here: by the time atexit runs, the interpreter has
        # already shut the worker thread's executor down, so an in-process close
        # can only raise ("cannot schedule new futures after shutdown"). Chrome
        # exits with us anyway — the Playwright driver pipe closes on our death.


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
