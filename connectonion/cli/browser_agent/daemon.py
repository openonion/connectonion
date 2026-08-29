"""
Purpose: Persistent concurrent browser daemon — owns one AsyncBrowserCore/event loop and dispatches authenticated CLI requests over POSIX Unix sockets or Windows named pipes.
LLM-Note:
  Dependencies: asyncio + bounded Windows transport executor + AsyncBrowserCore + browser_agent.transport; private mode lazily imports EgressGateway and its immutable launch-policy factory; BrowserAutomation remains the public help/schema source | imported by browser_agent.client and browser_commands | tested by daemon, engine, transport, and Remote Browser runtime suites
  Data flow: wire-v1 JSON {v,caller,account,tab,line,raw,engine} (legacy plain line accepted) → immutable engine check → private gateway-health check → atomic registry/claim admission → awaited async browser verb; private mode forces engine=onion before any paid session or page effect
  State/Effects: one asyncio-owned AsyncBrowserCore and persistent context | private mode starts its gateway, canonical credential file, and fixed paid launch policy before IPC bind; gateway loss rejects before browser mutation; shutdown closes browser, removes credentials, then stops gateway | independent tab tasks interleave behind per-tab locks | bounded POSIX/Windows transports and lifetime ownership sidecars preserve admission and cleanup
  Integration: launched detached via `python -m connectonion.cli.browser_agent.daemon <address> [--headless] [--engine=MODE] [--profile-dir=PATH] [--authkey-file=PATH] [--remote-egress]`; dispatch() remains the non-loop compatibility seam
  Performance: page operations on separate tabs overlap; same-tab work queues; browser/model/image blocking work never owns the event-loop thread; first browser launch remains 1-3s
  Errors: malformed/oversized/stalled clients are bounded at their own connection boundary; cancellation clears only its request lease; vanished readers are logged and cannot stop the daemon; launch failure or closed shared runtime releases the endpoint
"""

import argparse
import asyncio
import atexit
import contextlib
import inspect
import json
import os
import platform
import shlex
import signal
import socket
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore
from connectonion.useful_tools.browser_tools.browser import (
    driver_stealth_status,
    installed_browser_path,
)

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

REQUEST_TIMEOUT = 120.0
REPLY_TIMEOUT = 120.0
MAX_REQUEST_BYTES = 1024 * 1024
MAX_IN_FLIGHT = 32
WINDOWS_TRANSPORT_WORKERS = 8

# Tabs are closed by the agent that opened them. This is only a janitor for tabs
# whose opener is never coming back — a crashed process, a machine left running
# for weeks. It is deliberately far longer than any real task: reclaiming early
# would close a page someone is still using, which is exactly what owner-only
# closing exists to prevent. Three days, not three minutes.
ABANDONED_AFTER = 3 * 24 * 3600


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
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return False
    return transport.pid_alive(int(raw))


def _parse_duration(text: str) -> float:
    """'30s' '10m' '2h' or a bare number of seconds -> seconds. 0 when unparseable."""
    text = (text or "").strip().lower()
    if not text:
        return 0.0
    unit = {"s": 1, "m": 60, "h": 3600}.get(text[-1])
    number = text[:-1] if unit else text
    try:
        return float(number) * (unit or 1)
    except ValueError:
        return 0.0


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _declared_hold(meta) -> float:
    """Seconds left on the tab's declared occupancy, 0 once it has elapsed.

    An agent that says at `tab open` how long it needs the tab is stating
    something the framework cannot infer: a login handoff needs minutes, a
    long scrape needs an hour. While that window is live the tab is its own.
    Once it passes, another agent may clean up — everyone here is cooperative,
    and a declaration that has elapsed with the tab still open means the owner
    is gone, not that it is still working.
    """
    until = meta.get("needs_until") or 0
    return max(0.0, until - time.time())


def _held_by_other(meta, caller: str) -> bool:
    """True when this tab carries a live claim (within GUARD_WINDOW) by a DIFFERENT
    identity than `caller`. An anonymous request (caller="") is still held OUT of a
    named claim; two anonymous requests cannot be told apart, so they are not guarded."""
    holder = meta.get("caller") or meta.get("opened_by")
    if not holder or holder == caller:
        return False
    if _declared_hold(meta):
        return True  # inside the window its owner asked for
    return time.time() - (meta.get("claim_at") or 0) < GUARD_WINDOW


def launch_failure_advice(first_line: str) -> str:
    """What to tell someone whose browser would not start.

    Two different failures wear the same exception and the advice for one is
    nonsense for the other. A deployed agent on a Linux server was told to run
    `co browser` from a desktop Terminal, when what it needed was the browser
    installed — the executable was simply not on disk.
    """
    log = "Full log at ~/.co/browser.log."
    if "xecutable doesn't exist" in first_line:
        return ("No browser is installed for this user.\n"
                f"Install it with:  patchright install chromium\n{log}")
    if platform.system() == "Darwin":
        return ("Run `co browser` from a desktop Terminal (a logged-in window "
                f"session), not over ssh/cron/detached.\n{log}")
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if platform.system() == "Linux" and display and "has been closed" in first_line:
        # A headed launch against a display that is configured but dead fails
        # exactly this way, and the exception says nothing. Both conditions are
        # required, or this becomes the mistake the docstring above describes:
        # with DISPLAY unset the text contradicted itself ("DISPLAY='' is set"),
        # and on any other Linux failure — a profile lock, an OOM kill — it
        # blamed the display confidently and sent the reader nowhere.
        #
        # `ENV DISPLAY=:99` with no Xvfb behind it is what this looks like.
        return (f"DISPLAY={display!r} is set but no display answered, so a headed "
                "browser could not start.\n"
                "Either start the X server (Xvfb) or unset DISPLAY — with no "
                "display set, the browser runs headless by itself.\n" + log)
    return log


class BrowserDaemon:
    """Concurrent server owning one asyncio-native browser runtime."""

    def __init__(
        self,
        sock_path: str,
        headless: bool = False,
        engine_mode: str = "auto",
        *,
        profile_dir: str | Path | None = None,
        remote_egress: bool = False,
        authkey_path: str | Path | None = None,
        gateway_factory=None,
        browser_factory=AsyncBrowserCore,
    ):
        if engine_mode not in ("auto", "system", "onion"):
            raise ValueError(f"invalid browser engine mode: {engine_mode}")
        if remote_egress and engine_mode != "onion":
            raise ValueError("remote browser daemon requires engine=onion")
        self.sock_path = sock_path
        self.engine_mode = engine_mode
        self._headless = headless
        self._profile_dir = (
            Path(profile_dir).expanduser().resolve() if profile_dir is not None else None
        )
        self._remote_egress = remote_egress
        self._authkey_path = Path(authkey_path) if authkey_path is not None else None
        self._gateway_factory = gateway_factory
        self._browser_factory = browser_factory
        self._proxy_auth_path = None
        if self._remote_egress and self._profile_dir is None:
            raise ValueError("remote browser daemon requires an explicit profile")
        if not self._remote_egress and self._profile_dir is not None:
            # A profile only reaches the browser through the launch policy, which
            # exists in remote-egress mode. Accepting it here and using the
            # shared local profile anyway would give a caller its own socket,
            # lock and log while silently pooling cookies with `co browser`.
            raise ValueError("a profile directory requires --remote-egress")
        self._gateway = None
        self.browser = (
            None
            if self._remote_egress
            else self._browser_factory(headless=headless, engine_mode=engine_mode)
        )
        self._srv = None
        # Set by _cleanup before it closes the listener, so serve() can tell "we are
        # stopping" from "the socket broke while we were meant to be serving".
        self._closing = False
        self._shutdown_started = False
        self._had_browser = False
        self._defer_context_probe = False
        self.last_command = None  # {"line": str, "at": float} of the last real command
        self._next_tab = 1        # id allocator for auto-named tabs
        self._registry_lock = asyncio.Lock()
        self._health_lock = asyncio.Lock()
        self._loop = None
        self._client_tasks = set()
        self._transport_pool = None

    def _parse_envelope(self, raw: str) -> tuple:
        """Wire v1: JSON {caller,account,tab,line,raw,engine} — quote-safe by construction
        (a caller or tab name can hold any character without breaking shlex). A plain
        line (old client) is accepted as an anonymous request for the main tab."""
        if not raw.startswith("{"):
            return "", "", None, raw, False, self.engine_mode
        req = json.loads(raw)
        tab = req.get("tab")
        return (
            str(req.get("caller") or ""),
            str(req.get("account") or ""),
            (str(tab) if tab is not None else None),
            str(req.get("line") or ""),
            bool(req.get("raw", False)),
            str(req.get("engine") or "auto"),
        )

    # Verbs that neither drive nor destroy a page: never guarded, and a not-yet-registered
    # -t target is fine (you may inspect or create it). `help` never reaches the daemon —
    # the CLI answers it locally.
    READONLY = ("tab", "status", "engine_status", "use", "switch")

    def dispatch(self, raw: str) -> tuple:
        """Synchronous test/embedding bridge; production uses ``dispatch_async``.

        The daemon process calls the async method on its one owned event loop.  This
        bridge preserves the long-standing pure-dispatch test seam without creating
        a second browser worker or being callable from the runtime loop itself.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.dispatch_async(raw))
        raise RuntimeError("dispatch() cannot run inside an event loop; await dispatch_async()")

    async def dispatch_async(self, raw: str) -> tuple:
        """Run one request without blocking unrelated tabs.

        Returns ``(ok, payload)``; ok is True, False, or an integer error code
        mirrored by the client (2 usage · 3 unknown tab · 4 tab busy).
        Claim admission and active-request audit leases are atomic even though the
        browser operation itself may overlap work on independent tabs.
        """
        try:
            caller, _caller_account, tab, line, raw_result, requested_engine = self._parse_envelope(raw)
            tokens = shlex.split(line)
        except (ValueError, TypeError) as exc:  # malformed envelope/quoting is the CLIENT's error
            return 2, f"unparseable request: {exc}"
        if not tokens:
            return 2, "empty request"
        # Not `getattr(..., False)`: a missing attribute here would skip the
        # gateway-health gate entirely, which is the wrong direction to fail
        # for the check that keeps an unproven browser from serving commands.
        if self._remote_egress and (
            self._gateway is None or not self._gateway.is_running
        ):
            return False, "EGRESS_GATEWAY_UNAVAILABLE"
        if requested_engine != self.engine_mode:
            return 6, (
                f"browser daemon is pinned to engine={self.engine_mode}; this request asked "
                f"for engine={requested_engine}. Close it with `co browser close`, then retry."
            )
        verb = tokens[0]

        # -t targeting: each task drives its OWN tab. Unknown-tab is only an error for a
        # command that would DRIVE the tab — read-only/lifecycle verbs may name a tab that
        # is not registered yet (to inspect it, or `tab open` it).
        session = _key(tab)
        async with self._registry_lock:
            if session is not None and session not in self.browser._tab_meta and verb not in self.READONLY:
                return 3, await self._unknown_tab_async(session)
        self.browser._bind_session(session)

        if verb == "tab":  # tab lifecycle: open / ls / close
            return await self._tab_async(tokens[1:], caller)
        if verb == "status":  # read-only report; does not count as the last command
            return await self._status_async()
        if verb == "engine_status":  # protocol/diagnostic probe; no claim and no launch
            return await self._call_verb_async("engine_status", [])
        if verb in ("use", "switch"):  # removed: no server-side cursor, targeting is per-command
            return False, "use/switch removed — target a tab per command instead:  co browser -t <tab> <verb>"
        if verb == "newtab":  # legacy spelling of `tab open` + go_to
            if session is not None:  # it allocates its OWN tab — a -t target would be ignored
                return 2, "newtab allocates its own tab and ignores -t — use:  co browser tab open <name>, then  co browser -t <name> go_to <url>"
            return await self._newtab_async(line, tokens, caller)
        if verb == "closetab":  # legacy spelling of `tab close`
            return await self._closetab_async(tokens[1:], caller)

        # `close` with no -t is a deliberate whole-browser shutdown (unguarded). `-t X close`
        # closes ONE tab and so must pass the same ownership guard as any destructive write.
        if verb == "close" and session is None:
            return await self._call_verb_async("close", tokens[1:])

        # A command that would execute nothing must not acquire anything: reject an
        # unknown verb BEFORE the claim, or a typo would hold the tab for GUARD_WINDOW.
        if verb == "do":
            return 2, (
                "`do` runs in the CLI process so model waits do not block the shared "
                "browser daemon. Upgrade this client and retry."
            )
        if not _is_verb(self.browser, verb):
            return False, (
                f"unknown command: {verb}\n"
                f"Run 'co browser help' to list functions, or "
                f"'co browser do \"<instruction>\"' for natural language."
            )

        # Every page-driving command (and a targeted close) claims its tab: a DIFFERENT
        # agent mid-task there fails loudly (exit 4) and is taught the tab lifecycle —
        # never silent interleaving on one page.
        request_id = uuid.uuid4().hex
        async with self._registry_lock:
            meta = self._register_tab(session, caller)
            if _held_by_other(meta, caller):
                return 4, self._tab_busy(session, meta)
            self._stamp_claim(meta, caller, line)
            meta.setdefault("active_requests", {})[request_id] = {
                "caller": caller,
                "line": line,
                "started_at": time.time(),
            }
            self.last_command = {"line": line, "at": time.time()}
        try:
            return await self._call_verb_async(
                verb, tokens[1:], raw_result=raw_result
            )
        finally:
            async with self._registry_lock:
                active = meta.get("active_requests")
                if active is not None:
                    active.pop(request_id, None)
                    if not active:
                        meta.pop("active_requests", None)

    def _register_tab(self, key, caller: str) -> dict:
        """Return the tab's board entry, creating the shared main tab's on first use.

        The default who/purpose deliberately satisfies go_to's occupancy ceremony,
        which is the DIRECT-API declaration layer. Through the daemon, declaring
        happens at the tab layer instead (`tab open --who/--for`; bare main needs
        no ceremony, per docs). A named -t target was validated before this point."""
        return self.browser._tab_meta.setdefault(
            key, {"who": caller or "main",
                  # `who` is the CURRENT occupant — _stamp_claim reassigns it when a
                  # claim expires and someone else takes over. `opened_by` is who
                  # created the tab and is never reassigned: it is what "your tab"
                  # means. Anonymous callers cannot own anything, because two
                  # anonymous callers are indistinguishable.
                  "opened_by": caller or "",
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

    def _call_verb(self, verb: str, raw_args, raw_result: bool = False) -> tuple:
        """Synchronous compatibility bridge for pure dispatch tests."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._call_verb_async(verb, raw_args, raw_result))
        raise RuntimeError("await _call_verb_async() inside an event loop")

    def _launch_failed(self) -> bool:
        probe = getattr(self.browser, "_launch_failed", None)
        if callable(probe):
            return bool(probe())
        return (
            getattr(self.browser, "playwright", None) is not None
            and getattr(self.browser, "browser", None) is None
        )

    async def _call_verb_async(
        self, verb: str, raw_args, raw_result: bool = False
    ) -> tuple:
        """Match a verb to an async browser method and await its result."""
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
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:  # dispatch boundary: report to client as ERR
            if self._launch_failed():
                # Chrome aborted at startup: str(exc) is a huge patchright "Call log".
                # Keep the first line and point at the full log instead of dumping it.
                first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
                return False, (
                    f"{type(exc).__name__}: {first}\n"
                    f"Chrome failed to start. {launch_failure_advice(first)}"
                )
            # On wrong arguments, show the expected signature so an agent can self-correct.
            hint = f"\nusage: {verb}{signature_str(method)}" if isinstance(exc, TypeError) else ""
            return False, f"{type(exc).__name__}: {exc}{hint}"

        payload = _stringify(result)
        if payload.startswith("data:image/") and not raw_result:
            # A human at the shell doesn't want a base64 blob — the image is on disk.
            # The client-side NL agent asks for raw results so vision still gets the data URL.
            return True, f"Screenshot saved to: {self.browser.last_screenshot_path}"
        return True, payload

    def _status(self) -> tuple:
        """Synchronous compatibility bridge for status tests."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._status_async())
        raise RuntimeError("await _status_async() inside an event loop")

    async def _browser_is_alive(self) -> bool:
        probe = getattr(self.browser, "is_alive", None)
        if probe is None:
            probe = getattr(self.browser, "_context_is_alive", None)
        if probe is None:
            return False
        result = probe()
        return bool(await result) if inspect.isawaitable(result) else bool(result)

    async def _browser_tab_status(self) -> str:
        result = self.browser.tab_status()
        return await result if inspect.isawaitable(result) else result

    async def _status_async(self) -> tuple:
        """Report browser state, the last command, and the tab board."""
        open_state = "open" if await self._browser_is_alive() else "not open"
        headless = str(getattr(self.browser, "_headless", False)).lower()
        lines = [f"Browser: {open_state} · headless={headless} · targeting is per-command (-t <tab>; bare = main)"]
        engine_status = getattr(self.browser, "engine_status", None)
        try:
            engine = engine_status() if callable(engine_status) else {
                "requested_engine": "auto",
                "resolved_engine": None,
                "reason": "not_started",
                "artifact_id": None,
            }
            if inspect.isawaitable(engine):
                engine = await engine
        except Exception:
            # Status is the diagnostic path. A broken optional paid client must
            # be reported as unresolved, not take the whole report down.
            engine = {
                "requested_engine": getattr(self.browser, "_engine_mode", "auto"),
                "resolved_engine": None,
                "reason": "status_unavailable",
                "artifact_id": None,
            }
        lines.append(
            "Engine: "
            f"requested={engine['requested_engine']} · "
            f"resolved={engine['resolved_engine'] or 'not-started'} · "
            f"reason={engine['reason']}"
            + (f" · artifact={engine['artifact_id']}" if engine.get("artifact_id") else "")
        )
        # Surface stealth-driver health here so a misconfigured driver (webdriver leak) is
        # visible where users look for browser state, not only in `co doctor`.
        stealth, version, detail = driver_stealth_status()
        mark = {"ok": "✓", "broken": "✗", "missing": "○"}[stealth]
        lines.append(f"Stealth driver: {mark} patchright {version} — {detail}".rstrip(" —"))
        # That line is about the PACKAGE. On a deployed agent it read ✓ while
        # every page command answered "Executable doesn't exist at
        # .../chromium-1228/chrome-linux64/chrome", so the one thing that has to
        # be true before anything works was the one thing not reported.
        # A paid resolution runs the downloaded artifact, not the driver's
        # default install. Reporting the default here said "/usr/bin/google-chrome"
        # while every page was served by a Chromium under .onionwright/runtimes,
        # which is the wrong answer to the one question this line exists for.
        binary = engine.get("executable")
        if not binary:
            try:
                binary = installed_browser_path()
            except Exception:
                binary = None  # status is what you run when things are broken
        lines.append(f"Browser binary: ✓ {binary}" if binary else
                     "Browser binary: ✗ none installed — run: patchright install chromium")
        if self.last_command:
            lines.append(f'Last command: "{self.last_command["line"]}" · {_ago(time.time() - self.last_command["at"])}')
        else:
            lines.append("Last command: (none yet)")
        lines.append("")
        lines.append(await self._browser_tab_status())
        return True, "\n".join(lines)

    def _tab(self, args, caller: str = "") -> tuple:
        """Synchronous compatibility bridge for tab lifecycle tests."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._tab_async(args, caller))
        raise RuntimeError("await _tab_async() inside an event loop")

    async def _tab_async(self, args, caller: str = "") -> tuple:
        """Tab lifecycle: open/list/close with atomic registry transitions."""
        if not args:
            return 2, self._tab_usage()
        action, rest = args[0], args[1:]
        if action == "open":
            async with self._registry_lock:
                return self._tab_open(rest, caller)
        if action in ("ls", "list"):
            await self._reap_abandoned_tabs()
            if "--json" in rest:
                async with self._registry_lock:
                    board = [
                        {
                            "tab": _tab_label(k),
                            **{
                                field: m.get(field)
                                for field in ("who", "purpose", "last_line", "last_at")
                            },
                            "active_requests": [
                                {"request_id": request_id, **request}
                                for request_id, request in m.get(
                                    "active_requests", {}
                                ).items()
                            ],
                        }
                        for k, m in self.browser._tab_meta.items()
                    ]
                return True, json.dumps(board)
            return await self._status_async()
        if action == "close":
            return await self._closetab_async(rest, caller)
        return 2, self._tab_usage()

    def _tab_open(self, rest, caller: str = "") -> tuple:
        """Register a named tab (page is created lazily on its first command). Prints ONLY the name."""
        name, who, purpose, needs = "", "", "", ""
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in ("--who", "--for", "--needs") and i + 1 < len(rest):
                i += 1
                if tok == "--who":
                    who = rest[i]
                elif tok == "--needs":
                    needs = rest[i]
                else:
                    purpose = rest[i]
            elif tok.startswith("--who="):
                who = tok.split("=", 1)[1]
            elif tok.startswith("--for="):
                purpose = tok.split("=", 1)[1]
            elif tok.startswith("--needs="):
                needs = tok.split("=", 1)[1]
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
                                caller=caller, claim_at=time.time() if caller else 0,
                                needs_until=time.time() + _parse_duration(needs) if needs else 0)
                return True, name
            # A DIFFERENT agent is mid-task under this name: sharing would collide.
            return 4, self._tab_busy(name, existing) + "\n\nor pick a different name for your own tab."
        self.browser._tab_meta[name] = {
            "who": who or caller or name, "purpose": purpose or name,
            "opened_by": caller or "",
            "opened_at": datetime.now(), "caller": caller, "claim_at": time.time() if caller else 0,
            # How long the opener says it needs the tab. Other agents leave it
            # alone until then, and may clean it up afterwards.
            "needs_until": time.time() + _parse_duration(needs) if needs else 0,
        }
        return True, name

    def _tab_usage(self) -> str:
        return (
            "usage: co browser tab open [NAME] [--who <agent>] [--for \"<purpose>\"] [--needs 10m]\n"
            "       co browser tab ls [--json]                                        # who runs where\n"
            "       co browser tab close <NAME>                                       # release when done\n"
            "then target your tab on EVERY command, including do:\n"
            "       co browser -t <NAME> <verb> [args]\n\n"
            "--needs is your estimate of how long you will hold the tab (30s / 10m / 2h).\n"
            "Other agents leave it alone until then, and may close it afterwards — an\n"
            "estimate that ran out with the tab still open reads as 'crashed', not 'busy'.\n"
            "Without it, 120s of silence is enough for another agent to take the tab."
        )

    def _tab_busy(self, key, meta) -> str:
        """Error-as-documentation: another agent owns this tab right now — get your own."""
        who = meta.get("who") or meta.get("caller") or "someone"
        last = (meta.get("last_line") or "")[:60]
        ago = _ago(time.time() - (meta.get("claim_at") or meta.get("last_at") or time.time()))
        left = _declared_hold(meta)
        window = (f" · declared for {_fmt_duration(left)} more" if left
                  else "")
        return (
            f"tab '{_tab_label(key)}' is in use by {who} — last: \"{last}\" · {ago}{window}\n\n"
            f"You are a second agent on this browser. Two agents cannot share one tab.\n"
            f"Run your task in your own tab — three commands:\n"
            f"  1. co browser tab open <name> --who <your-name> --for \"<what you are doing>\"\n"
            f"  2. co browser -t <name> <verb> [args]      # add -t <name> to EVERY command, including do\n"
            f"  3. co browser tab close <name>             # when your task is done\n\n"
            f"see who owns what:  co browser tab ls"
        )

    async def _reap_abandoned_tabs(self) -> None:
        """Close tabs whose opener never came back. Runs before tab listings.

        Owner-only closing means a crashed agent's tab would otherwise live as
        long as the daemon. This is the only path that closes someone else's
        tab, so it is deliberately hard to trigger: no live claim, and untouched
        for ABANDONED_AFTER (3 days). Every reclamation is logged, so the first
        person surprised by one can find out why.
        """
        async with self._registry_lock:
            now = time.time()
            for key, meta in list(self.browser._tab_meta.items()):
                if key is None:  # main is shared and never reaped
                    continue
                if _held_by_other(meta, ""):  # someone is actively driving it
                    continue
                last = meta.get("last_at") or meta.get("claim_at")
                if not last or now - last < ABANDONED_AFTER:
                    continue
                owner = meta.get("opened_by") or meta.get("who") or "unknown"
                result = self.browser.close_tab(_tab_label(key))
                if inspect.isawaitable(result):
                    await result
                print(
                    f"[reap] closed tab '{_tab_label(key)}' opened by {owner} — "
                    f"idle {_ago(now - last)}",
                    file=sys.stderr,
                    flush=True,
                )

    def _tab_not_yours(self, key, owner: str) -> str:
        """Error-as-documentation: you may close your own tabs, not other agents'."""
        return (
            f"tab '{_tab_label(key)}' was opened by {owner}, not you — only its "
            f"opener closes it.\n\n"
            f"This does not expire. An idle tab is not an abandoned one: the agent "
            f"that opened it may be waiting on a login, a long page, or a human.\n"
            f"Close your own tabs when your task ends; leave other agents' alone.\n\n"
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

    async def _unknown_tab_async(self, name: str) -> str:
        board = await self._browser_tab_status()
        return (
            f"no tab named '{name}'\n\n"
            f"{board}\n\n"
            f"create it first:  co browser tab open {name} --who <your-name> --for \"<one-line purpose>\"\n"
            f"then target it on every command, including do:\n"
            f"                  co browser -t {name} <verb> [args]\n"
            f"when finished:    co browser tab close {name}"
        )

    def _newtab(self, line, tokens, caller: str = "") -> tuple:
        """Synchronous compatibility bridge for the legacy newtab tests."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._newtab_async(line, tokens, caller))
        raise RuntimeError("await _newtab_async() inside an event loop")

    async def _newtab_async(self, line, tokens, caller: str = "") -> tuple:
        """Register and occupy a fresh tab without changing bare targeting."""
        # A numeric id can collide with a NAME someone registered via `tab open` —
        # skip taken keys or this would occupy another agent's live tab.
        async with self._registry_lock:
            while str(self._next_tab) in self.browser._tab_meta:
                self._next_tab += 1
            key = str(self._next_tab)
            self._next_tab += 1
            self.browser._bind_session(key)
            self.last_command = {"line": line, "at": time.time()}
            ok, payload = await self._call_verb_async("newtab", tokens[1:])
            if not ok:
                return False, payload
            meta = self.browser._tab_meta.get(key)
            if meta is not None and caller:
                meta["caller"], meta["claim_at"] = caller, time.time()
            return True, f"[tab {key}] {payload}"

    def _closetab(self, args, caller: str = "") -> tuple:
        """Synchronous compatibility bridge for close-tab tests."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._closetab_async(args, caller))
        raise RuntimeError("await _closetab_async() inside an event loop")

    async def _closetab_async(self, args, caller: str = "") -> tuple:
        """Close one tab atomically with respect to claim admission."""
        if not args:
            return 2, "usage: co browser tab close <tab>   (a name from `co browser tab ls`)"
        target = args[0]
        key = _key(target)
        async with self._registry_lock:
            meta = self.browser._tab_meta.get(key)
            if key not in self.browser._pages and meta is None:
                if key is None:  # main always exists conceptually; nothing to release is fine
                    return True, "main is already free — nothing to close."
                return 3, await self._unknown_tab_async(target)
            # Closing someone else's tab is fine once the time they asked for has
            # passed — every agent here is cooperative, and a declaration that
            # elapsed with the tab still open means its owner is gone, not busy.
            # Before that, refuse: 120s of silence is not evidence a task ended.
            if meta and _held_by_other(meta, caller):
                return 4, self._tab_busy(key, meta)
            self.last_command = {"line": "closetab " + target, "at": time.time()}
            # close_tab releases the page, registration/claim, and remembered URL.
            result = self.browser.close_tab(_tab_label(key))
            message = await result if inspect.isawaitable(result) else result
            return True, f"Closed tab {_tab_label(key)}. {message}"

    def serve(self):
        """Own one event loop for the daemon's complete lifetime."""
        asyncio.run(self.serve_async())

    async def serve_async(self):
        self._loop = asyncio.get_running_loop()
        try:
            await self._prepare_runtime()
            self._bind()
            atexit.register(self._cleanup)
            if threading.current_thread() is threading.main_thread():
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    self._loop.add_signal_handler(signal.SIGTERM, self._begin_shutdown)
            if transport.IS_WINDOWS:
                self._transport_pool = ThreadPoolExecutor(
                    max_workers=WINDOWS_TRANSPORT_WORKERS,
                    thread_name_prefix="browser-transport",
                )
                await self._serve_windows()
            else:
                raw_listener = self._srv
                self._srv = await asyncio.start_unix_server(
                    self._accept_posix_client,
                    sock=raw_listener,
                    limit=MAX_REQUEST_BYTES + 1,
                    backlog=MAX_IN_FLIGHT,
                )
                await self._srv.serve_forever()
        except asyncio.CancelledError:
            if not self._closing:
                raise
        except OSError:
            if not self._closing:
                raise
        finally:
            await self._shutdown_async()

    async def _prepare_runtime(self) -> None:
        """Start private network authority before exposing the daemon endpoint."""
        if not self._remote_egress:
            return
        if self._gateway is not None or self.browser is not None:
            if (
                self._gateway is not None
                and self.browser is not None
                and self._gateway.is_running
            ):
                return
            raise RuntimeError("private browser runtime is only prepared once")
        from connectonion.network.host.egress_gateway import EgressGateway
        from connectonion.network.host.private_browser_runtime import (
            proxy_auth_path_for_profile,
            remote_browser_launch_policy,
            remove_proxy_auth_file,
            write_proxy_auth_file,
        )

        gateway = (
            self._gateway_factory()
            if self._gateway_factory is not None
            else EgressGateway()
        )
        endpoint = await gateway.start()
        proxy_auth_path = proxy_auth_path_for_profile(self._profile_dir)
        try:
            write_proxy_auth_file(proxy_auth_path, endpoint)
            policy = remote_browser_launch_policy(
                self._profile_dir,
                endpoint,
                proxy_auth_path,
            )
            browser = self._browser_factory(
                headless=self._headless,
                engine_mode=self.engine_mode,
                launch_policy=policy,
                egress_gateway=gateway,
            )
        except BaseException:
            remove_proxy_auth_file(proxy_auth_path)
            await gateway.stop()
            raise
        self._gateway = gateway
        self._proxy_auth_path = proxy_auth_path
        self.browser = browser

    def _accept_posix_client(self, reader, writer) -> None:
        """Admit at most ``MAX_IN_FLIGHT`` clients; shed excess immediately."""
        if self._closing or len(self._client_tasks) >= MAX_IN_FLIGHT:
            writer.transport.abort()
            return
        task = asyncio.create_task(self._handle_posix_client(reader, writer))
        self._track_client(task)

    def _track_client(self, task: asyncio.Task) -> None:
        self._client_tasks.add(task)
        task.add_done_callback(self._client_done)

    def _client_done(self, task: asyncio.Task) -> None:
        self._client_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            print(f"browser client task failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    async def _read_posix_request(self, reader) -> str:
        deadline = asyncio.get_running_loop().time() + REQUEST_TIMEOUT
        chunks = []
        size = 0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("request timed out")
            try:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("request timed out") from exc
            if not chunk:
                return b"".join(chunks).decode().strip()
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                raise ValueError(
                    f"request exceeds the {MAX_REQUEST_BYTES}-byte limit"
                )
            chunks.append(chunk)

    async def _handle_posix_client(self, reader, writer) -> None:
        request = ""
        try:
            request = await self._read_posix_request(reader)
            ok, payload = await self._dispatch_boundary(request)
            writer.write(self._reply_bytes(ok, payload))
            await asyncio.wait_for(writer.drain(), timeout=REPLY_TIMEOUT)
            if await self._should_stop(ok, payload):
                self._begin_shutdown()
        except (
            BrokenPipeError,
            ConnectionResetError,
            TimeoutError,
            asyncio.TimeoutError,
        ):
            print(f"client vanished before reply: {request[:80]!r}", file=sys.stderr)
        except ValueError as exc:
            with contextlib.suppress(
                BrokenPipeError,
                ConnectionResetError,
                TimeoutError,
                asyncio.TimeoutError,
            ):
                writer.write(self._reply_bytes(2, str(exc)))
                await asyncio.wait_for(writer.drain(), timeout=REPLY_TIMEOUT)
        finally:
            writer.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await writer.wait_closed()

    async def _serve_windows(self) -> None:
        slots = asyncio.Semaphore(MAX_IN_FLIGHT)
        while not self._closing:
            await slots.acquire()
            try:
                conn = await self._transport_call(self._accept)
            except OSError:
                slots.release()
                if self._closing:
                    return
                raise
            if conn is None:
                slots.release()
                continue
            # Listener.close() does not interrupt an already-blocked Windows
            # named-pipe accept. Shutdown authenticates one internal connection
            # to wake it; discard that sentinel instead of starting a request
            # reader that would keep the transport pool alive for 120 seconds.
            if self._closing:
                conn.close()
                slots.release()
                return
            task = asyncio.create_task(self._handle_windows_client(conn, slots))
            self._track_client(task)

    async def _transport_call(self, fn):
        return await asyncio.get_running_loop().run_in_executor(
            self._transport_pool, fn
        )

    async def _handle_windows_client(self, conn, slots) -> None:
        request = ""
        try:
            request = await self._transport_call(lambda: self._read_request(conn))
            if request is None:
                return
            if len(request.encode()) > MAX_REQUEST_BYTES:
                ok, payload = 2, f"request exceeds the {MAX_REQUEST_BYTES}-byte limit"
            else:
                ok, payload = await self._dispatch_boundary(request)
            await self._transport_call(
                lambda: self._send_reply(conn, self._reply_bytes(ok, payload))
            )
            if await self._should_stop(ok, payload):
                self._begin_shutdown()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, EOFError):
            print(f"client vanished before reply: {request[:80]!r}", file=sys.stderr)
        except ValueError as exc:
            message = str(exc)
            with contextlib.suppress(
                BrokenPipeError, ConnectionResetError, TimeoutError, EOFError
            ):
                await self._transport_call(
                    lambda: self._send_reply(conn, self._reply_bytes(2, message))
                )
        finally:
            try:
                conn.close()
            finally:
                slots.release()

    async def _dispatch_boundary(self, request: str) -> tuple:
        try:
            return await self.dispatch_async(request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _reply_bytes(ok, payload: str) -> bytes:
        header = "OK" if ok is True else ("ERR" if ok is False else f"ERR {ok}")
        return (header + "\n" + payload).encode()

    async def _should_stop(self, ok, payload: str) -> bool:
        """Serialize shared runtime health transitions after concurrent replies."""
        async with self._health_lock:
            if ok is False and payload.startswith("TimeoutError:"):
                self._had_browser = True
                self._defer_context_probe = True
                return False
            closed = payload.startswith("Browser closed") or (
                ok is False
                and (
                    payload.startswith("TargetClosedError:")
                    or "context or browser has been closed" in payload
                )
            )
            if self._defer_context_probe:
                if self._launch_failed() or closed:
                    return True
                if ok is True and payload.startswith("Navigated to "):
                    self._defer_context_probe = False
                else:
                    return False
            if closed:
                return True
            if getattr(self.browser, "_closing", False):
                # A concurrent bare close owns teardown and will stop the server
                # after its reply. Do not race that teardown with a health probe.
                return False
            alive = await self._browser_is_alive()
            self._had_browser = self._had_browser or alive
            return self._launch_failed() or closed or (self._had_browser and not alive)

    def _begin_shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._closing = True
        if (
            transport.IS_WINDOWS
            and self._srv
            and self._loop is not None
            and self._transport_pool is not None
        ):
            # multiprocessing.connection.Listener.close() does not wake a
            # ConnectNamedPipe already blocked in another thread. Connect with
            # our own key before closing the listener; _serve_windows discards
            # this sentinel and can then enter deterministic shutdown.
            self._loop.run_in_executor(
                self._transport_pool, self._wake_windows_accept
            )
        elif self._srv:
            self._srv.close()

    def _wake_windows_accept(self) -> None:
        """Authenticate one no-payload client so a blocked pipe accept returns."""
        try:
            conn = transport.win_connect(self.sock_path, self._authkey)
        except (
            transport.AuthenticationError,
            EOFError,
            FileNotFoundError,
            ConnectionError,
            OSError,
        ):
            return
        conn.close()

    async def _shutdown_async(self) -> None:
        self._closing = True
        if self._srv:
            self._srv.close()
            wait_closed = getattr(self._srv, "wait_closed", None)
            if wait_closed is not None:
                await wait_closed()
        current = asyncio.current_task()
        pending = [task for task in self._client_tasks if task is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._client_tasks.clear()
        close = getattr(self.browser, "close", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                print(
                    f"browser cleanup failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
        from connectonion.network.host.private_browser_runtime import (
            remove_proxy_auth_file,
        )

        remove_proxy_auth_file(self._proxy_auth_path)
        self._proxy_auth_path = None
        if self._gateway is not None:
            try:
                await self._gateway.stop()
            except Exception as exc:
                print(
                    f"egress gateway cleanup failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
            self._gateway = None
        if self._transport_pool is not None:
            self._transport_pool.shutdown(wait=True, cancel_futures=True)
            self._transport_pool = None
        self._remove_endpoint()

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
        owner is alive with a full bounded backlog (many clients arriving together — the
        exact situation that spawns us). Unlinking a BUSY daemon's socket forks the
        world: two daemons, two Chromes fighting over one profile, and the original
        becomes an unreachable zombie. The pid file the owner wrote at bind time
        tells the two apart.

        The lifetime lock, pid-file location, and (on Windows) the named-pipe wire live
        behind `transport` so POSIX behavior is byte-identical while Windows gets native
        named pipes with an HMAC-authenticated handshake."""
        transport.ensure_endpoint_parent(self.sock_path)
        self._bind_lock = transport.acquire_singleton_lock(transport.lock_path(self.sock_path))
        if self._bind_lock is None:
            sys.exit(0)  # another daemon is binding or already serving
        if transport.IS_WINDOWS:
            self._authkey = transport.load_or_create_authkey(
                self._authkey_path
            )  # the pipe wire's HMAC secret
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
        Path(transport.pid_path(self.sock_path)).write_text(str(os.getpid()), encoding="utf-8")
        self._srv.listen(MAX_IN_FLIGHT)

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
        Path(transport.pid_path(self.sock_path)).write_text(str(os.getpid()), encoding="utf-8")

    # ---- transport seam: POSIX raw AF_UNIX socket vs Windows named-pipe Connection ----

    def _accept(self):
        """Accept one client. Windows hands back only AUTHENTICATED connections — the
        HMAC challenge runs deadline-bounded in transport.accept_authenticated (mpc's
        own accept()-time handshake blocks forever on a stalled client), and a failed
        handshake returns None instead of killing the asyncio accept loop. A dead
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
                return transport.bounded_io(
                    conn,
                    lambda: conn.recv_bytes(MAX_REQUEST_BYTES + 1),
                    REQUEST_TIMEOUT,
                ).decode().strip()
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
            transport.bounded_io(
                conn, lambda: conn.send_bytes(data), REPLY_TIMEOUT
            )
        else:
            conn.sendall(data)

    def _cleanup(self):
        """Thread-safe shutdown hook used by signals, tests, and ``atexit``."""
        self._closing = True
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._begin_shutdown)
            return
        if self._srv:
            self._srv.close()
        self._remove_endpoint()

    def _remove_endpoint(self) -> None:
        """Remove only endpoint state still owned by this process."""
        pid_file = Path(transport.pid_path(self.sock_path))
        try:
            owner = pid_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return
        if owner == str(os.getpid()):
            if not transport.IS_WINDOWS and os.path.exists(self.sock_path):
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(self.sock_path)  # POSIX: remove our socket file (mpc did it on Win)
            with contextlib.suppress(FileNotFoundError):
                pid_file.unlink()


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
    # The daemon's stdout/stderr are redirected to ~/.co/browser.log; on Windows
    # they default to a legacy codepage (cp1252), so logging a page title or error
    # containing any non-Latin-1 character would crash the daemon. Same fix as the
    # CLI entry point in cli/main.py.
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("sock_path", nargs="?", default=default_sock_path())
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--profile-dir")
    parser.add_argument("--authkey-file")
    parser.add_argument("--remote-egress", action="store_true")
    parser.add_argument("--engine", choices=("auto", "system", "onion"), default="auto")
    args = parser.parse_args()
    BrowserDaemon(
        args.sock_path,
        headless=args.headless,
        engine_mode=args.engine,
        profile_dir=args.profile_dir,
        authkey_path=args.authkey_file,
        remote_egress=args.remote_egress,
    ).serve()


if __name__ == "__main__":
    main()
