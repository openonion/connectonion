"""
Purpose: Python client for remote ConnectOnion agents — signed transport, acknowledged Host modes, streaming UI events, and onboarding.
LLM-Note:
  Dependencies: imports from [asyncio, copy, json, time, uuid, dataclasses, typing, httpx, websockets (lazy), ..address (sign)] | imported by [network/__init__.py, connectonion/__init__.py]
  Data flow: input() sends signed CONNECT/INPUT and consumes stream/OUTPUT | set_session_mode() validates Host state, sends signed OIP mode_change, and waits for mode_changed
  State/Effects: mutates current session/modes/UI/status only from authenticated carrier responses; opens outbound sockets; signs deep-detached command payloads; endpoint resolution may query relay and candidate /info endpoints
  Integration: exposes connect(), RemoteAgent, Response, ExecResult, PermissionModeError, TurnTimeoutError, TurnLostError, ApprovalPendingError; RemoteAgent provides input/respond_to_approval/stop/call/set_session_mode sync+async actions and read-only state
  Performance: endpoint resolution attempted once per RemoteAgent (cached in _endpoint_resolved/_resolved_endpoint) | input() timeout is one deadline for the whole call (default 60s; CONNECTED also bounded at 30s) | a socket closed mid-turn is reopened on the same session up to 3 times | sync .input() rejected inside running event loop (use input_async)
  Errors: raises ConnectionError on transport/auth failure, PermissionModeError on owned policy refusal, TurnTimeoutError (TimeoutError) at the deadline, ApprovalPendingError when an approval is pending without on_approval, TurnLostError (ConnectionError) when a dropped turn cannot be picked up, RuntimeError for sync calls in async contexts, ValueError for invalid choices
Protocol: CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
See docs/network/websocket-protocol.md for full specification.

Lifecycle:
  1. connect(address) creates RemoteAgent instance
  2. agent.input(prompt) opens WebSocket, sends CONNECT to authenticate
  3. Server responds with CONNECTED { session_id, status }
  4. Client sends INPUT { prompt }
  5. Receives streaming events: tool_call, tool_result, thinking, assistant
  6. Answers PING, approval_needed (on_approval) and ask_user (on_ask) with
     request_id = the event's id; without a callback, stops and surfaces them
  7. Receives final OUTPUT; returns Response(text, done)
  A socket that closes after INPUT is reopened with CONNECT {session_id,
  last_msg_id}; if CONNECTED is not "running" the turn is gone: TurnLostError.
"""

from .transport_limits import MAX_WEBSOCKET_MESSAGE_BYTES

import asyncio
import copy
import inspect
import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx

from .. import address as addr
from ..core.mode import FULL_ACCESS, mode_id, set_mode


def _validated_remote_mode_state(mode: Any, turns_left: Any) -> tuple[str, int | None]:
    """Validate an authoritative Host state before mirroring it locally."""

    canonical = mode_id(mode)
    if canonical == FULL_ACCESS:
        if (
            isinstance(turns_left, bool)
            or not isinstance(turns_left, int)
            or turns_left <= 0
        ):
            raise ValueError("full-access acknowledgement requires turns_left")
        return canonical, turns_left
    if turns_left is not None:
        raise ValueError("turns_left is valid only for full-access")
    return canonical, None


def _tool_ui_status(status: Any, *, terminal: bool = False) -> str:
    if status in {"pending", "running", "in_progress"}:
        return "running"
    if status is None and not terminal:
        return "running"
    if status in {"success", "done", "completed"}:
        return "done"
    return "error"


def _this_callers_identity():
    """The keys a client signs with: this project's, else this machine's.

    `connect()` took `keys=None` and passed it straight through, so the
    documented one-liner -- `connect(addr).input(...)` -- sent unsigned frames
    and a `careful` agent refused them:

        ConnectionError: Auth error: unauthorized: signed request required

    `careful` is what `co init` writes, so that was the default server. What
    `careful` adds over `strict` is a way *in* for a signed stranger, not
    permission to stay anonymous.

    `co call` never hit this because it loaded the keys itself, in a second copy
    of this logic that resolved `.co` against the bare cwd. The host side had
    already settled the question -- resolve_agent_identity: the project's key
    when it has one, the machine's ~/.co when it does not -- so a client gets
    the same answer, with the walk-up #661 gave the project half.

    Never generates. An agent must have an address; a caller without one is a
    caller the remote is entitled to refuse.
    """
    from pathlib import Path

    from .. import address
    from ..project import project_co_dir

    return address.load(project_co_dir()) or address.load(Path.home() / ".co")


def _sort_endpoints(endpoints: List[str]) -> List[str]:
    """Closest first, and among equally close ones, the encrypted one.

    Closeness was the only key, so an agent announcing both schemes on one host
    was reached over whichever the relay listed first — and it lists plaintext
    first. The connection then went in the clear to an agent that had offered TLS.

    What travels on it is authenticated protocol traffic. #649 measured the old
    protocol's impact: a captured CONNECT opened a connection whose unsigned EXEC
    frames could name any whitelisted tool. CONNECT replay protection and v2
    per-command signatures now close both halves; TLS still prevents disclosure
    of prompts, results, and metadata that signatures do not encrypt.

    Closeness still decides first. A plaintext loopback connection has no network
    to be observed on, and reaching an agent on this machine is the case direct
    resolution exists for. This only chooses between endpoints that are equally
    close.

    An agent that offers no TLS still must not carry private protocol traffic
    across a network in plaintext, regardless of authentication strength.
    """
    def priority(url: str) -> tuple:
        if "localhost" in url or "127.0.0.1" in url:
            closeness = 0
        elif "192.168." in url or "10." in url or "172.16." in url:
            closeness = 1
        else:
            closeness = 2
        encrypted = 0 if url.startswith(("https://", "wss://")) else 1
        return (closeness, encrypted)
    return sorted(endpoints, key=priority)


LOOPBACK = ("localhost", "127.0.0.1", "::1", "[::1]")


def endpoint_is_safe(url: str) -> bool:
    """May a signed frame go to this endpoint?

    TLS anywhere, or plaintext to loopback only.

    Before #643 `resolve_endpoint` never resolved anything, so every client went
    through the relay over `wss://` and TLS covered this. Direct connections
    then became the normal path, and a self-hosted agent announces plain
    `ws://`:

        "endpoints": ["http://10.5.27.133:8797", "ws://10.5.27.133:8797/ws", …]

    A CONNECT is signed, and on a LAN anyone who can observe that traffic can
    capture one. Within the freshness window a captured CONNECT is the whole
    whitelisted tool surface (#649). Loopback has no network to observe, and a
    deployed agent is served over https (1.5.3), so both of the cases direct
    resolution exists for stay fast; the rest falls back to the relay.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme in ("https", "wss"):
        return True
    return (parsed.hostname or "") in LOOPBACK


async def resolve_endpoint(
    agent_address: str,
    relay_url: str,
    timeout: float = 3.0
) -> Optional[str]:
    """
    Resolve the best WebSocket endpoint for an agent address.

    Steps:
    1. Query relay server for agent endpoints
    2. Sort by priority (localhost → local network → public)
    3. Verify each HTTP endpoint by checking /info
    4. Return first working ws:// endpoint where address matches

    Returns:
        WebSocket URL (ws://...) or None if resolution fails
    """
    # Only try resolution for valid addresses (0x + 64 hex = 66 chars)
    if not agent_address.startswith("0x") or len(agent_address) != 66:
        return None

    # Convert wss://relay to https://relay for API call
    https_relay = relay_url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Step 1: Query relay for agent info
        try:
            response = await client.get(f"{https_relay}/api/agents/{agent_address}")
            if response.status_code != 200:
                return None
            agent_info = response.json()
        except Exception:
            return None

        # `online` is advisory, not required. The relay does not send it —
        # measured against production, the reply is endpoints / relay /
        # last_seen / profile — so requiring it meant this function returned
        # None for every agent that has ever existed, and every call went over
        # the relay even to an agent on the same machine. _sort_endpoints and
        # its localhost-first ordering had never run.
        #
        # An explicit False is still honoured: the relay knowing the agent is
        # gone is worth more than rediscovering it at one timeout per endpoint.
        # Absent means no opinion.
        #
        # Liveness was never what this flag established anyway. Each candidate
        # below is fetched and its /info address must match the agent being
        # looked for, which is both stronger and current.
        if agent_info.get("online") is False or not agent_info.get("endpoints"):
            return None

        # Step 2: Sort endpoints (localhost first)
        sorted_endpoints = _sort_endpoints(agent_info["endpoints"])

        # Step 3: Try each HTTP endpoint
        # Plaintext public endpoints are candidates too: _open_best_connection
        # seals the socket end to end before any signed frame goes onto it,
        # and drops it if the host cannot seal (see _seal_direct).
        http_endpoints = [ep for ep in sorted_endpoints
                          if ep.startswith("http://") or ep.startswith("https://")]

        for http_url in http_endpoints:
            try:
                info_response = await client.get(f"{http_url}/info")
                if info_response.status_code != 200:
                    continue

                info = info_response.json()

                # Step 4: Verify address matches
                if info.get("address") == agent_address:
                    # Build WebSocket URL from HTTP URL
                    ws_url = http_url.replace("https://", "wss://").replace("http://", "ws://")
                    if not ws_url.endswith("/ws"):
                        ws_url = ws_url.rstrip("/") + "/ws"
                    return ws_url
            except Exception:
                continue

    return None


async def probe_endpoints(agent_address: str, relay_url: str, timeout: float = 3.0) -> dict:
    """What resolve_endpoint saw, kept: every listed endpoint and how it answered.

    resolve_endpoint walks this list and throws each failure away, which is
    right for connecting and useless for diagnosing. A share reported only
    "the host is not reachable directly"; finding that the host announced
    `http://34.129.161.131:8001` behind a firewall allowing 22/80/443 took a
    manual relay query and a curl (#1387). This returns the same walk with the
    answers in it.
    """
    https_relay = relay_url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(f"{https_relay}/api/agents/{agent_address}")
        except httpx.HTTPError as exc:
            return {"listed": [], "probes": [], "relay_error": _probe_failure(exc)}
        if response.status_code != 200:
            return {"listed": [], "probes": [], "relay_error": f"relay answered HTTP {response.status_code}"}
        listed = response.json().get("endpoints") or []
        probes = []
        for url in _sort_endpoints(listed):
            if not url.startswith(("http://", "https://")):
                continue
            try:
                info = await client.get(f"{url}/info")
            except httpx.HTTPError as exc:
                probes.append({"endpoint": url, "result": _probe_failure(exc)})
                continue
            if info.status_code != 200:
                result = f"answered HTTP {info.status_code}"
            elif info.json().get("address") != agent_address:
                result = "answered /info, but for a different address"
            else:
                result = "ok"
            probes.append({"endpoint": url, "result": result})
    return {"listed": listed, "probes": probes}


def _probe_failure(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect timeout"
    if isinstance(exc, httpx.ConnectError):
        return "refused or unreachable"
    if isinstance(exc, httpx.TimeoutException):
        return "connected, then no answer"
    return f"{type(exc).__name__}: {exc}"


@dataclass
class Response:
    """Response from remote agent."""
    text: str       # Agent's response or question
    done: bool      # True = complete, False = needs more input (agent asked a question)


@dataclass
class ExecResult:
    """Result of a direct tool execution (RemoteAgent.call) — no LLM involved."""
    text: str                     # Raw tool output (may contain base64 image data)
    status: str                   # "success" | "error"
    duration_ms: int = 0
    error: Optional[str] = None   # Error message when status == "error"

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def images(self) -> List[str]:
        """Base64 data-URL images embedded in the output (e.g. screenshots)."""
        import re
        return re.findall(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', self.text)


class PermissionModeError(ConnectionError):
    """An acknowledged Host session-mode policy rejection."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class TurnTimeoutError(TimeoutError):
    """input() reached its deadline; the turn may still be running on the Host."""

    def __init__(self, message: str, session_id: Optional[str] = None):
        super().__init__(message)
        self.session_id = session_id


class TurnLostError(ConnectionError):
    """The socket closed mid-turn and the Host no longer has the turn to pick up."""

    def __init__(self, message: str, session_id: Optional[str] = None):
        super().__init__(message)
        self.session_id = session_id


class ApprovalPendingError(RuntimeError):
    """The agent is waiting on an approval and no on_approval was given to answer it."""

    def __init__(self, message: str, session_id: Optional[str], request: Dict[str, Any]):
        super().__init__(message)
        self.session_id = session_id
        self.request = request


# Pauses before each attempt to reopen a session whose socket closed mid-turn.
# Enough to ride out a network blip or a relay reconnect; a Host that stays
# down longer ends the call with TurnLostError rather than a silent wait.
_RECONNECT_DELAYS = (0.5, 1.0, 2.0)


class _AgentAway(Exception):
    """The relay answered a reattach with "Agent not connected".

    Mid-turn that is not an authentication failure: the Host's process is gone
    or has not reconnected to the relay yet -- a restart looks exactly like
    this. It is retried like a closed socket, and ends in TurnLostError.
    """


class _ApprovalTimedOut(Exception):
    """on_approval had not decided when the call's deadline came."""

    def __init__(self, request: Dict[str, Any]):
        super().__init__(request.get("id"))
        self.request = request


class _Turn:
    """What one call is doing: the prompt or answer it sends, and by when."""

    def __init__(self, prompt, images, files, on_onboard, on_approval, on_ask,
                 *, deadline: float, timeout: float):
        self.prompt = prompt
        self.images = images
        self.files = files
        self.on_onboard = on_onboard
        self.on_approval = on_approval
        self.on_ask = on_ask
        self.deadline = deadline
        self.timeout = timeout
        self.started = False     # the Host has this turn: never send INPUT again
        self.answer = None       # a response frame still to send on reattach
        self.answered = set()    # request ids answered, so a replay is not re-answered
        self.closed = None       # why the first socket closed, for the error
        self.declined = None     # the tool whose approval the deadline declined

    def resume_with(self, answer: Dict[str, Any], request: Dict[str, Any]) -> None:
        """Continue a turn the Host holds, opening with the answer to `request`."""
        if request.get("id") is not None:
            answer["request_id"] = request["id"]
            self.answered.add(request["id"])
        self.answer = answer
        self.started = True

    def remaining(self) -> float:
        left = self.deadline - asyncio.get_running_loop().time()
        if left <= 0:
            raise asyncio.TimeoutError
        return left


async def _recv_before(ws, deadline: float) -> str:
    """One frame, or TimeoutError at `deadline`.

    A deadline, not a per-recv timeout: that reset on every frame, so a turn
    that streamed or was merely kept alive by PINGs never timed out (519 s
    against timeout=60, waiting on an approval nobody could see).
    """
    left = deadline - asyncio.get_running_loop().time()
    if left <= 0:
        raise asyncio.TimeoutError
    return await asyncio.wait_for(ws.recv(), timeout=left)


async def _maybe_await(value):
    """Callbacks may be plain functions or coroutines."""
    return await value if inspect.isawaitable(value) else value


def _call_off_the_loop(fn, *args) -> "asyncio.Future":
    """fn(*args) on a daemon thread, as a future of this loop.

    Not asyncio.to_thread: asyncio.run() joins the default executor on the way
    out, so a sync input() whose callback overran the deadline still waited for
    the callback to return before raising. A daemon thread is abandoned
    instead, and its late result is dropped.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def settle(result, error):
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def run():
        try:
            outcome = (fn(*args), None)
        except Exception as error:
            outcome = (None, error)
        try:
            loop.call_soon_threadsafe(settle, *outcome)
        except RuntimeError:
            # The loop is closed: the call gave up on this answer at its deadline.
            return

    threading.Thread(target=run, daemon=True, name="on_approval").start()
    return future


def _ask_text(event: Dict[str, Any]) -> str:
    # `question` is the field the tool sends. This once read `text`, which no
    # producer has ever sent -- useful_tools/ask_user.py and diff_writer.py
    # both send `question`. `text` stays accepted for the old shape.
    return event.get("question") or event.get("text") or ""


class RemoteAgent:
    """
    Interface to a remote agent with real-time UI updates.

    Supports:
    - WebSocket streaming for real-time events
    - Session state synced from server
    - UI events transformed for rendering
    - Multi-turn conversations

    Usage:
        agent = connect("0x...")
        response = agent.input("Book a flight")
        print(response.text)   # "Which date?"
        print(response.done)   # False (agent asked a question)
        print(agent.ui)        # All events for rendering
    """

    def __init__(
        self,
        agent_address: str,
        *,
        keys: Optional[Dict[str, Any]] = None,
        relay_url: Optional[str] = None,
    ):
        self.address = agent_address
        # None means "I did not choose" -- find the caller's identity, because
        # an unsigned client cannot talk to a default agent. False means "no
        # keys, deliberately", which trust: open accepts and people use in dev.
        self._keys = _this_callers_identity() if keys is None else (keys or None)
        # Looked for an identity and found none (a fresh HOME, no `co init`),
        # as opposed to keys=False. Only the first can be told how to get one.
        self._found_no_identity = keys is None and self._keys is None
        if relay_url is None:
            from ..backend import backend_ws_url
            relay_url = backend_ws_url()
        self._relay_url = relay_url.rstrip("/")
        self._status = "idle"
        self._current_session: Optional[Dict[str, Any]] = None
        self._ui_events: List[Dict[str, Any]] = []
        self._available_modes: List[Dict[str, Any]] = []
        self._resolved_endpoint: Optional[str] = None
        self._endpoint_resolved = False
        # The session CONNECTED named, kept even when no OUTPUT arrives, so a
        # timed-out or dropped turn can be stopped or picked up again.
        self._session_id: Optional[str] = None
        self._last_event_id: Optional[str] = None
        # An approval_needed or ask_user the running turn is blocked on.
        self._pending_request: Optional[Dict[str, Any]] = None
        # (loop, socket, is_direct) of the turn in flight, for stop().
        self._live = None

    @property
    def status(self) -> str:
        """Current status: 'idle' | 'working' | 'waiting' | 'unknown'

        'unknown' follows a TurnTimeoutError: this client stopped waiting at
        its deadline, and the turn may still be running on the Host. It said
        'idle' there, which a caller reasonably read as "safe to start the next
        turn". stop() ends such a turn, and the next input() or stop() learns
        the truth from the Host.
        """
        return self._status

    @property
    def current_session(self) -> Optional[Dict[str, Any]]:
        """Session state synced from server (read-only)."""
        return self._current_session

    @property
    def ui(self) -> List[Dict[str, Any]]:
        """UI events for rendering. One type = one component.

        Server events are transformed:
        - tool_call + tool_result merged into single UI item
        - user_input → type: 'user'
        - assistant → type: 'agent'
        """
        return self._ui_events

    @property
    def available_modes(self) -> List[Dict[str, Any]]:
        """Server-authorized public modes from the latest connection."""
        return copy.deepcopy(self._available_modes)

    def set_session_mode(self, mode: str, timeout: float = 30.0) -> None:
        """Persist a Host mode after its owned acknowledgement."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "set_session_mode() cannot be used inside async context. "
                "Use 'await agent.set_session_mode_async()' instead."
            )
        except RuntimeError as exc:
            if "set_session_mode() cannot be used" in str(exc):
                raise
        asyncio.run(self.set_session_mode_async(mode, timeout=timeout))

    async def set_session_mode_async(
        self, mode: str, timeout: float = 30.0
    ) -> None:
        """Commit one exact mode, or time out with outcome unknown."""
        canonical = mode_id(mode)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise ValueError("timeout must be a positive number")
        try:
            await asyncio.wait_for(
                self._set_session_mode_transaction(canonical), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Permission mode change timed out after {timeout}s"
            ) from None

    async def _set_session_mode_transaction(self, canonical: str) -> None:
        """Run negotiation and response handling under the caller's deadline."""
        import websockets

        await self._try_resolve_endpoint()
        connection, is_direct = await self._open_best_connection(websockets)
        async with connection as ws:
            await ws.send(json.dumps(self._build_connect_message(is_direct)))
            state = await self._wait_for_mode_connected(ws)
            if not any(
                item.get("id") == canonical
                for item in state["availableModes"]
            ):
                raise ValueError(
                    f"Permission mode is not available: {canonical}"
                )
            request = {"type": "mode_change", "mode": canonical}
            await ws.send(json.dumps(
                self._build_command_message(request, is_direct)
            ))
            await self._wait_for_mode_response(
                ws, canonical
            )

    def input(
        self,
        prompt: str,
        timeout: float = 60.0,
        on_onboard: Optional[Callable[[List[str], Optional[float]], Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        *,
        on_approval: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_ask: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Response:
        """
        Send prompt to remote agent and get response.

        Returns Response(text, done) where:
        - done=True: Task complete
        - done=False: Agent asked a question; the next input() is sent as its answer

        Args:
            prompt: Task/prompt to send
            timeout: Seconds the whole call may take (default 60). A deadline,
                     not a per-message timeout: frames and keepalives do not
                     extend it. On expiry TurnTimeoutError names the session;
                     the turn may still be running there, and stop() ends it.
            on_onboard: Callback when agent requires onboarding (invite code or payment).
                        Called with (methods: list[str], payment_amount: float | None).
                        Should return {"invite_code": "..."} or {"payment": amount}.
                        If None, prompts in the terminal, or raises
                        ConnectionError saying so when stdin is not a terminal.
            images: Optional list of base64 data URLs for multimodal input
            files: Optional list of file dicts with name and base64 data
            on_approval: Called with the approval_needed event when the agent
                         asks to run a gated tool. Return True/False, or
                         {"approved": bool, "scope": "once" | "session"}.
                         It runs on its own thread and counts against
                         `timeout`: not answered by the deadline, the approval
                         is declined and TurnTimeoutError raised.
                         Without it, input() raises ApprovalPendingError at
                         once; answer with respond_to_approval() or stop().
            on_ask: Called with the ask_user event; return the answer text.
                    Without it, input() returns done=False with the question.

        Returns:
            Response with text and done flag

        Raises:
            TurnTimeoutError: the deadline passed (a TimeoutError).
            ApprovalPendingError: an approval is pending and on_approval is None.
            TurnLostError: the socket closed mid-turn and the Host no longer has
                the turn (a ConnectionError). A socket that closes while the
                Host still runs the turn is reopened and the turn picked up.

        Example:
            >>> response = agent.input("Book a flight to Tokyo")
            >>> if not response.done:
            ...     response = agent.input("March 15")  # Answer the question

        Onboard example:
            >>> def handle_onboard(methods, payment_amount):
            ...     if "invite_code" in methods:
            ...         return {"invite_code": input("Enter invite code: ")}
            >>> response = agent.input("Hello", on_onboard=handle_onboard)
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "input() cannot be used inside async context. "
                "Use 'await agent.input_async()' instead."
            )
        except RuntimeError as e:
            if "input() cannot be used" in str(e):
                raise
        return asyncio.run(self._stream_input(
            prompt, timeout, on_onboard, images, files,
            on_approval=on_approval, on_ask=on_ask,
        ))

    async def input_async(
        self,
        prompt: str,
        timeout: float = 60.0,
        on_onboard: Optional[Callable[[List[str], Optional[float]], Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        *,
        on_approval: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_ask: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Response:
        """Async version of input()."""
        return await self._stream_input(
            prompt, timeout, on_onboard, images, files,
            on_approval=on_approval, on_ask=on_ask,
        )

    def call(self, tool: str, timeout: float = 60.0, **args) -> ExecResult:
        """Run one of the remote agent's tools directly — no LLM, no thinking.

        The terminal-style fast path: name a tool, pass its arguments, get the
        raw output straight back. Like typing a command and reading stdout — the
        result can be text or a base64 screenshot (see ExecResult.images).

        The tool is gated by the host's .co/host.yaml permission whitelist — the
        same list its LLM approval flow uses. A tool that isn't whitelisted comes
        back as an error ExecResult.

        Args:
            tool: Name of the remote tool to run (e.g. "bash", "take_screenshot")
            timeout: Seconds to wait for the result
            **args: Keyword arguments passed to the tool

        Returns:
            ExecResult(text, status, duration_ms, error) — .ok True on success,
            .images extracts any base64 screenshots from the output.

        Example:
            >>> agent = connect("0x...", keys=keys)
            >>> print(agent.call("bash", command="uptime").text)
            >>> shot = agent.call("take_screenshot")
            >>> if shot.images: save(shot.images[0])
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "call() cannot be used inside async context. "
                "Use 'await agent.call_async()' instead."
            )
        except RuntimeError as e:
            if "call() cannot be used" in str(e):
                raise
        return asyncio.run(self.call_async(tool, timeout=timeout, **args))

    async def call_async(self, tool: str, timeout: float = 60.0, **args) -> ExecResult:
        """Async version of call()."""
        import websockets

        await self._try_resolve_endpoint()

        exec_id = str(uuid.uuid4())

        connection, is_direct = await self._open_best_connection(websockets)
        connect_msg = self._build_connect_message(is_direct)
        exec_msg = self._build_command_message(
            {"type": "EXEC", "exec_id": exec_id, "tool": tool, "args": args},
            is_direct,
        )

        try:
            async with connection as ws:
                await ws.send(json.dumps(connect_msg))
                connect_error = await self._wait_for_direct_command_connected(ws)
                if connect_error:
                    return ExecResult(text="", status="error", error=connect_error)

                await ws.send(json.dumps(exec_msg))

                # Wait for our EXEC_RESULT; answer keepalive PINGs, skip other frames.
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    event = json.loads(raw)
                    etype = event.get("type")
                    if etype == "EXEC_RESULT" and event.get("exec_id") == exec_id:
                        return ExecResult(
                            text=event.get("result", ""),
                            status=event.get("status", "error"),
                            duration_ms=event.get("duration_ms", 0),
                            error=event.get("error"),
                        )
                    if etype == "PING":
                        await ws.send(json.dumps({"type": "PONG"}))
                    elif etype == "ERROR":
                        return ExecResult(text="", status="error",
                                          error=event.get("message", "exec failed"))
        except asyncio.TimeoutError:
            return ExecResult(text="", status="error", error=f"exec timed out after {timeout}s")

    def remote_browser(
        self,
        command: str,
        *,
        session_id: str | None = None,
        timeout: float = 60.0,
        **args,
    ) -> Dict[str, Any]:
        """Run one typed, owner-bound Remote Browser lifecycle command."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "remote_browser() cannot be used inside async context. "
                "Use 'await agent.remote_browser_async()' instead."
            )
        except RuntimeError as exc:
            if "remote_browser() cannot be used" in str(exc):
                raise
        return asyncio.run(
            self.remote_browser_async(
                command,
                session_id=session_id,
                timeout=timeout,
                **args,
            )
        )

    async def remote_browser_async(
        self,
        command: str,
        *,
        session_id: str | None = None,
        timeout: float = 60.0,
        **args,
    ) -> Dict[str, Any]:
        """Async Remote Browser lifecycle request over authenticated OIP."""
        import websockets

        await self._try_resolve_endpoint()
        request_id = str(uuid.uuid4())
        request = {
            "type": "REMOTE_BROWSER",
            "request_id": request_id,
            "command": command,
            "args": args,
        }
        if session_id is not None:
            request["session_id"] = session_id

        try:
            connection, is_direct = await self._open_best_connection(websockets)
            async with connection as ws:
                await ws.send(json.dumps(self._build_connect_message(is_direct)))
                connect_error = await self._wait_for_direct_command_connected(ws)
                if connect_error:
                    return self._remote_browser_client_error(
                        request_id, command, "CONNECTION_FAILED", connect_error
                    )
                await ws.send(json.dumps(
                    self._build_command_message(request, is_direct)
                ))
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    event = json.loads(raw)
                    event_type = event.get("type")
                    if (
                        event_type == "REMOTE_BROWSER_RESULT"
                        and event.get("request_id") == request_id
                    ):
                        event.pop("type", None)
                        return event
                    if event_type == "PING":
                        await ws.send(json.dumps({"type": "PONG"}))
                    elif event_type == "ERROR":
                        return self._remote_browser_client_error(
                            request_id,
                            command,
                            "CONNECTION_FAILED",
                            event.get("message", "remote browser request failed"),
                        )
        except asyncio.TimeoutError:
            return self._remote_browser_client_error(
                request_id,
                command,
                "TIMEOUT",
                f"remote browser request timed out after {timeout}s",
                retryable=True,
            )
        except OSError as exc:
            return self._remote_browser_client_error(
                request_id,
                command,
                "CONNECTION_FAILED",
                str(exc),
                retryable=True,
            )

    async def _wait_for_direct_command_connected(self, ws) -> str | None:
        """Complete CONNECT/onboarding for non-LLM command APIs."""
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            event = json.loads(raw)
            event_type = event.get("type")
            if event_type == "CONNECTED":
                return None
            if event_type == "ONBOARD_REQUIRED":
                methods = event.get("methods", [])
                if not sys.stdin.isatty():
                    offered = ", ".join(methods) or "no methods offered"
                    return (
                        f"agent requires onboarding ({offered}) — run this from "
                        "a terminal to enter an invite code"
                    )
                try:
                    credentials = self._prompt_onboard(
                        methods, event.get("payment_amount")
                    )
                except ValueError as declined:
                    return f"onboarding not completed: {declined}"
                await ws.send(json.dumps(self._build_onboard_submit(credentials)))
                continue
            if event_type == "ERROR":
                return event.get("message", "connect failed")

    @staticmethod
    def _remote_browser_client_error(
        request_id: str,
        command: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> Dict[str, Any]:
        return {
            "schema_version": "1",
            "ok": False,
            "command": f"remote-browser.{command}",
            "request_id": request_id,
            "code": code,
            "message": message,
            "retryable": retryable,
            "retry_after_seconds": None,
            "state": {},
            "tips": [],
            "warnings": [],
            "next_actions": [],
        }

    def reset(self) -> None:
        """Clear conversation and start fresh."""
        self._current_session = None
        self._ui_events = []
        self._status = "idle"
        self._session_id = None
        self._last_event_id = None
        self._pending_request = None

    def _ways_to_reach(self) -> list:
        """Where to try, best first: the agent itself, then the relay behind it.

        #643 made direct resolution work, and a resolved endpoint is cached for
        the life of this object. That is a good trade until the endpoint stops
        answering -- the agent restarts on another port, or the caller moves off
        that network -- and then every later call fails over a path that worked
        before #643, when resolution never succeeded and everything went through
        the relay.

        The relay is still there and still reaches the agent. One refused
        connection is a cheaper thing to pay than the conversation.
        """
        relay = (f"{self._relay_url}/ws/input", False)
        if self._resolved_endpoint:
            return [(self._resolved_endpoint, True), relay]
        return [relay]

    async def _open_best_connection(self, websockets):
        """Open the first way that answers, and remember if the direct one did not.

        Only the connection attempt is retried. Once a socket is open, an error
        on it is the agent's answer and belongs to the caller -- retrying a
        refused tool call somewhere else would run it twice.
        """
        for ws_url, is_direct in self._ways_to_reach():
            try:
                ws = await websockets.connect(ws_url, max_size=MAX_WEBSOCKET_MESSAGE_BYTES)
            except OSError:
                if not is_direct:
                    raise          # the relay is the last resort; there is no next
                self._forget_direct_endpoint()
                continue
            if not is_direct:
                if not self._keys:
                    return ws, False       # nothing signed will go onto it
                sealed = await self._offer_seal(ws)
                if sealed is not None:
                    return sealed, False
                # A 1.8.0 host answers SEAL with "unknown message type" and
                # has already consumed that socket's first frame. The relay
                # link is TLS to the relay, which is every client's old
                # footing; keep it, on a fresh socket.
                await ws.close()
                return await websockets.connect(ws_url, max_size=MAX_WEBSOCKET_MESSAGE_BYTES), False
            sealed = await self._offer_seal(ws)
            if sealed is not None:
                return sealed, True
            if endpoint_is_safe(ws_url) or not self._keys:
                # TLS or loopback: the link itself is private. No keys: nothing
                # signed will go onto it, so there is nothing to capture.
                return ws, True
            # Plaintext to a host that cannot seal: a signed frame on that link
            # is a captured CONNECT waiting to happen (#649). Not this way.
            await ws.close()
            self._forget_direct_endpoint()
        raise OSError("no way to reach the agent")

    async def _offer_seal(self, ws):
        """Seal a socket end to end; None if the host does not seal.

        Every socket, direct or relayed, is offered a SEAL first. A host that
        understands it answers SEALED_OK and every later frame is encrypted
        with one-time keys signed by both identities; a plaintext public
        endpoint is then as private as TLS, and a relayed session is opaque
        to the relay. An older host answers something else or nothing, and
        the caller decides whether the bare link is acceptable.
        """
        from . import sealed

        if not self._keys:
            return None
        hello, ephemeral = sealed.client_hello(self._keys, self.address)
        await ws.send(json.dumps(hello))
        try:
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=sealed.HANDSHAKE_TIMEOUT))
            channel = sealed.client_finish(reply, hello, ephemeral)
        except (asyncio.TimeoutError, sealed.SealRefused, ValueError):
            return None
        return sealed.SealedSocket(ws, channel)

    def _forget_direct_endpoint(self) -> None:
        """Stop trying a corpse on every turn; resolve again when next asked."""
        self._resolved_endpoint = None
        self._endpoint_resolved = False

    async def _try_resolve_endpoint(self) -> None:
        """Try to resolve endpoint for the agent address. Only attempts once."""
        if self._endpoint_resolved:
            return
        self._endpoint_resolved = True
        self._resolved_endpoint = await resolve_endpoint(self.address, self._relay_url)

    async def _stream_input(
        self,
        prompt: str,
        timeout: float,
        on_onboard: Optional[Callable[[List[str], Optional[float]], Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        on_approval: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_ask: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Response:
        """Send prompt via WebSocket and stream events until the turn ends."""
        pending = self._pending_request
        if pending is not None and pending.get("type") == "approval_needed":
            # A new INPUT would reach the Host as runtime input to a turn that
            # is blocked on this approval, and nothing would ever answer it.
            raise self._approval_pending(pending)
        self._status = "working"
        await self._try_resolve_endpoint()
        self._add_ui_event({"type": "user", "content": prompt})
        turn = _Turn(
            prompt, images, files, on_onboard, on_approval, on_ask,
            deadline=asyncio.get_running_loop().time() + timeout, timeout=timeout,
        )
        if pending is not None:
            # The agent is still inside the turn that asked, blocked on
            # ask_user. Sent as a new INPUT this started a fresh session and
            # left that turn waiting for ever; it is the answer.
            turn.resume_with({"type": "ASK_USER_RESPONSE", "answer": prompt}, pending)
        return await self._drive(turn)

    def respond_to_approval(
        self,
        approved: bool = True,
        scope: str = "once",
        timeout: float = 60.0,
        on_approval: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_ask: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Response:
        """Answer the approval an earlier input() raised ApprovalPendingError for.

        Reopens the session, sends the answer naming its request, and streams
        the rest of that turn: the Response input() would have returned.
        """
        self._refuse_inside_event_loop("respond_to_approval")
        return asyncio.run(self.respond_to_approval_async(
            approved, scope, timeout, on_approval=on_approval, on_ask=on_ask,
        ))

    async def respond_to_approval_async(
        self,
        approved: bool = True,
        scope: str = "once",
        timeout: float = 60.0,
        on_approval: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_ask: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Response:
        """Async version of respond_to_approval()."""
        pending = self._pending_request
        if pending is None or pending.get("type") != "approval_needed":
            raise RuntimeError("There is no approval pending to answer.")
        self._status = "working"
        await self._try_resolve_endpoint()
        turn = _Turn(
            None, None, None, None, on_approval, on_ask,
            deadline=asyncio.get_running_loop().time() + timeout, timeout=timeout,
        )
        turn.resume_with(
            {"type": "APPROVAL_RESPONSE", "approved": bool(approved), "scope": scope},
            pending,
        )
        return await self._drive(turn)

    def stop(self, timeout: float = 30.0) -> bool:
        """Interrupt the turn this agent is running; False if none is running.

        Reaches a turn in flight on this object (from another thread or task),
        and one an earlier call left running on the Host -- after a
        TimeoutError, or an ApprovalPendingError nobody is going to answer.
        """
        self._refuse_inside_event_loop("stop")
        return asyncio.run(self.stop_async(timeout))

    async def stop_async(self, timeout: float = 30.0) -> bool:
        """Async version of stop()."""
        live = self._live
        if live is not None:
            loop, ws, is_direct = live
            frame = json.dumps(self._build_command_message({"type": "INTERRUPT"}, is_direct))
            if loop is asyncio.get_running_loop():
                await ws.send(frame)
            else:
                # input() is running on its own loop in another thread, and the
                # socket belongs to that loop, so the send has to happen there.
                sent = asyncio.run_coroutine_threadsafe(ws.send(frame), loop)
                await asyncio.wait_for(asyncio.wrap_future(sent), timeout)
            # That call returns the OUTPUT the interrupted turn ends with.
            return True
        if not self._known_session_id():
            return False
        try:
            return await asyncio.wait_for(self._interrupt_by_reattaching(), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"stop() got no answer within {timeout}s; the turn in session "
                f"{self._known_session_id()} may still be running"
            ) from None

    async def _interrupt_by_reattaching(self) -> bool:
        """Open the session, INTERRUPT its running turn, wait for that turn's OUTPUT."""
        import websockets

        await self._try_resolve_endpoint()
        connection, is_direct = await self._open_best_connection(websockets)
        async with connection as ws:
            await ws.send(json.dumps(
                self._build_connect_message(is_direct, last_msg_id=self._last_event_id)
            ))
            event = await self._next_frame(ws, until="CONNECTED")
            if event.get("status") != "running":
                self._status = "idle"   # the Host says nothing runs: no longer unknown
                return False
            await ws.send(json.dumps(self._build_command_message({"type": "INTERRUPT"}, is_direct)))
            # True means the turn ended, not merely that a frame went out.
            event = await self._next_frame(ws, until="OUTPUT")
        self._current_session = event.get("session") or self._current_session
        self._pending_request = None
        self._status = "idle"
        return True

    async def _next_frame(self, ws, until: str) -> Dict[str, Any]:
        """Read to the next `until` frame, answering PINGs; an ERROR is raised."""
        while True:
            event = json.loads(await ws.recv())
            if event.get("type") == until:
                return event
            if event.get("type") == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
            elif event.get("type") == "ERROR":
                raise ConnectionError(f"stop refused: {event.get('message', event.get('error'))}")

    async def _drive(self, turn: "_Turn") -> Response:
        """Run one turn to its end, reopening the session if the socket closes.

        Once the Host has the turn, a closed socket is reopened on the same
        session and the stream picked up where it stopped. The prompt is never
        sent again: running it twice could repeat its tool calls.
        """
        import websockets

        failures = 0
        try:
            while True:
                try:
                    connection, is_direct = await asyncio.wait_for(
                        self._open_best_connection(websockets), turn.remaining()
                    )
                except OSError as refused:
                    if not turn.started:
                        raise
                    failure = f"could not reconnect: {refused}"
                else:
                    try:
                        return await self._run_on_socket(connection, is_direct, turn)
                    except _AgentAway as away:
                        failure = f"the relay says the agent is not connected ({away})"
                        if failures >= len(_RECONNECT_DELAYS) or (
                            turn.deadline - asyncio.get_running_loop().time()
                            <= _RECONNECT_DELAYS[failures]
                        ):
                            # Out of retries or out of time. Either way the
                            # Host is away, and TurnLostError says so; a
                            # TurnTimeoutError would suggest it still ran.
                            raise self._turn_lost(turn, failure)
                    except websockets.exceptions.ConnectionClosed as closed:
                        if not turn.started:
                            raise ConnectionError(
                                f"The connection to the agent closed before the prompt "
                                f"was sent ({closed}). Nothing ran; it is safe to retry."
                            ) from closed
                        turn.closed = turn.closed or str(closed)
                        failure = "the connection closed again"
                if failures >= len(_RECONNECT_DELAYS):
                    raise self._turn_lost(turn, failure)
                await asyncio.sleep(min(_RECONNECT_DELAYS[failures], turn.remaining()))
                failures += 1
        except asyncio.TimeoutError:
            # Not "idle": the Host may still be running the turn.
            self._status = "unknown"
            sid = self._known_session_id()
            declined = (
                f" on_approval had not answered for {turn.declined!r} by then, so "
                f"that approval was declined." if turn.declined else ""
            )
            raise TurnTimeoutError(
                f"No result within {turn.timeout}s (a deadline for the whole call, "
                f"not per message). The turn may still be running on the host in "
                f"session {sid}: agent.stop() interrupts it.{declined}",
                session_id=sid,
            ) from None
        finally:
            self._live = None

    async def _run_on_socket(self, connection, is_direct: bool, turn: "_Turn") -> Response:
        """CONNECT, send the prompt or the answer, then stream until the turn ends."""
        async with connection as ws:
            await ws.send(json.dumps(self._build_connect_message(
                is_direct, last_msg_id=self._last_event_id if turn.started else None,
            )))
            status = await self._wait_for_connected(ws, turn)
            if turn.started and status != "running":
                self._pending_request = None
                raise self._turn_lost(
                    turn, "the host no longer has it running (it restarted, or the "
                    "turn ended while this client was away)",
                )
            self._live = (asyncio.get_running_loop(), ws, is_direct)
            if not turn.started:
                await ws.send(json.dumps(self._build_input_message(
                    turn.prompt, str(uuid.uuid4()), is_direct, turn.images, turn.files,
                )))
                turn.started = True
            elif turn.answer is not None:
                await ws.send(json.dumps(self._build_command_message(turn.answer, is_direct)))
                turn.answer = None
                self._pending_request = None
            return await self._stream_events(ws, is_direct, turn)

    async def _wait_for_connected(self, ws, turn: "_Turn") -> Optional[str]:
        """Authenticate (onboarding if asked) and return CONNECTED's status."""
        while True:
            # CONNECTED keeps its own 30 s bound inside the call's deadline.
            limit = min(turn.deadline, asyncio.get_running_loop().time() + 30)
            event = json.loads(await _recv_before(ws, limit))
            event_type = event.get("type")
            if event_type == "CONNECTED":
                self._consume_connected_mode_state(event)
                self._session_id = event.get("session_id") or self._session_id
                return event.get("status")
            if event_type == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
            elif event_type == "ERROR":
                detail = str(event.get("message", event.get("error")) or "")
                if turn.started and "agent not connected" in detail.lower():
                    # Reattaching through the relay to a Host that restarted
                    # mid-turn. This raised "Auth error: Agent not connected"
                    # with no session id, instead of TurnLostError.
                    raise _AgentAway(detail)
                self._status = "idle"
                raise self._auth_error(event)
            elif event_type == "ONBOARD_REQUIRED":
                await ws.send(json.dumps(self._build_onboard_submit(
                    self._onboard_credentials(event, turn.on_onboard)
                )))
                # Continue waiting for CONNECTED or ONBOARD_SUCCESS

    def _onboard_credentials(self, event: Dict[str, Any], on_onboard) -> Dict[str, Any]:
        """Credentials from the callback, or asked for in the terminal."""
        methods = event.get("methods", [])
        payment_amount = event.get("payment_amount")
        self._add_ui_event({"type": "onboard_required", "methods": methods, "payment_amount": payment_amount})
        if on_onboard:
            return on_onboard(methods, payment_amount)
        if not (sys.stdin and sys.stdin.isatty()):
            # A script, a pipe, CI: there is nobody to type a code, and input()
            # ended the call in a bare EOFError after printing a prompt no one
            # would see. Say what the agent wants and how to give it.
            self._status = "idle"
            raise ConnectionError(
                f"This agent admits strangers only after onboarding "
                f"(methods: {', '.join(methods) or 'none offered'}), and there is "
                f"no terminal here to ask for it. Pass it to input(): "
                f"on_onboard=lambda methods, amount: {{\"invite_code\": \"...\"}}"
                + (f" or {{\"payment\": {payment_amount}}}" if payment_amount else "")
                + ". Or ask the agent's operator to add your address as a contact "
                f"(co trust add {self._keys['address'] if self._keys else '<your address>'})."
            )
        return self._prompt_onboard(methods, payment_amount)

    async def _stream_events(self, ws, is_direct: bool, turn: "_Turn") -> Response:
        """Consume the turn's events until OUTPUT, or a request nobody here can answer."""
        import websockets

        while True:
            event = json.loads(await _recv_before(ws, turn.deadline))
            event_type = event.get("type")
            if isinstance(event.get("id"), str):
                # Where to pick the stream up if this socket closes.
                self._last_event_id = event["id"]

            if event_type == "PING":
                # Unanswered, a keepalive is the Host's evidence this client is gone.
                await ws.send(json.dumps({"type": "PONG"}))

            elif event_type == "OUTPUT":
                result_text = event.get("result", "")
                self._current_session = event.get("session")
                self._session_id = event.get("session_id") or self._session_id
                self._pending_request = None
                self._status = "idle"
                self._add_ui_event({"type": "agent", "content": result_text})
                return Response(text=result_text, done=True)

            elif event_type == "ERROR":
                self._status = "idle"
                raise ConnectionError(f"Agent error: {event.get('message', event.get('error'))}")

            elif event_type == "ONBOARD_REQUIRED":
                await ws.send(json.dumps(self._build_onboard_submit(
                    self._onboard_credentials(event, turn.on_onboard)
                )))

            elif event_type == "ONBOARD_SUCCESS":
                self._add_ui_event({
                    "type": "onboard_success",
                    "level": event.get("level", "contact"),
                    "message": event.get("message", "Onboard successful")
                })
                # Retry the original prompt
                await ws.send(json.dumps(self._build_input_message(
                    turn.prompt, str(uuid.uuid4()), is_direct,
                )))

            elif event_type in ("approval_needed", "ask_user"):
                if event.get("id") is not None and event.get("id") in turn.answered:
                    continue  # replayed on reattach; already answered
                try:
                    answer = await self._answer_request(event, turn)
                except _ApprovalTimedOut:
                    turn.declined = event.get("tool")
                    await self._decline_at_deadline(ws, is_direct, event)
                    raise asyncio.TimeoutError from None
                if answer is None:
                    # Nobody here can answer it. The turn waits on the Host,
                    # and waiting here as well was the 519-second hang.
                    self._pending_request = event
                    self._status = "waiting"
                    if event_type == "approval_needed":
                        raise self._approval_pending(event)
                    return Response(text=_ask_text(event), done=False)
                turn.answered.add(event.get("id"))
                try:
                    await ws.send(json.dumps(self._build_command_message(answer, is_direct)))
                except websockets.exceptions.ConnectionClosed:
                    # The socket died while the caller decided. The answer is
                    # still the caller's: send it first on the reattached socket
                    # rather than drop it and leave the Host waiting forever.
                    turn.resume_with(answer, event)
                    raise

            else:
                # Stream event (tool_call, tool_result, thinking, etc.)
                self._handle_stream_event(event)

    async def _answer_request(self, event: Dict[str, Any], turn: "_Turn") -> Optional[Dict[str, Any]]:
        """The caller's answer as a response frame; None when there is no callback."""
        if event.get("type") == "approval_needed":
            self._add_ui_event({
                "type": "approval_needed",
                "tool": event.get("tool"),
                "arguments": event.get("arguments"),
            })
            if turn.on_approval is None:
                return None
            decision = await self._decide_within_deadline(event, turn)
            if isinstance(decision, dict):
                frame = {
                    "type": "APPROVAL_RESPONSE",
                    "approved": decision.get("approved") is True,
                    "scope": decision.get("scope", "once"),
                }
            else:
                frame = {"type": "APPROVAL_RESPONSE", "approved": bool(decision), "scope": "once"}
        else:
            # multi_select and fields were dropped once: a client could not
            # tell one answer from many, and a form could not be rendered.
            asked = {
                "type": "ask_user",
                "text": _ask_text(event),
                "options": event.get("options"),
                "multi_select": event.get("multi_select"),
            }
            if event.get("fields") is not None:
                asked["fields"] = event["fields"]
            self._add_ui_event(asked)
            if turn.on_ask is None:
                return None
            frame = {"type": "ASK_USER_RESPONSE", "answer": await _maybe_await(turn.on_ask(event))}
        if event.get("id") is not None:
            # A Host from #1692 on delivers an answer only to the request it names.
            frame["request_id"] = event["id"]
        return frame

    async def _decline_at_deadline(self, ws, is_direct: bool, event: Dict[str, Any]) -> None:
        """Tell the Host no, so it is not left waiting on an answer nobody will send."""
        import websockets

        frame = {"type": "APPROVAL_RESPONSE", "approved": False, "scope": "once"}
        if event.get("id") is not None:
            frame["request_id"] = event["id"]
        try:
            await ws.send(json.dumps(self._build_command_message(frame, is_direct)))
        except websockets.exceptions.ConnectionClosed:
            # Nothing left to tell it on. The TurnTimeoutError that follows
            # names the session, and stop() still ends the turn.
            self._pending_request = event
            return
        self._pending_request = None

    async def _decide_within_deadline(self, event: Dict[str, Any], turn: "_Turn") -> Any:
        """on_approval's decision, if it comes before the call's deadline.

        A callback slower than the time left used to block the event loop, its
        True went out (if at all) after the call had already given up, and the
        Host was left waiting on the approval forever. Now it runs off the loop
        and against the deadline. What happens at the deadline is a choice,
        made here: the approval is declined. The caller has abandoned the turn
        by then, and a gated tool must not run on an answer that arrived after
        its caller stopped listening; declining lets the Host move on instead
        of waiting. A late answer from the callback is discarded.
        """
        try:
            decision = await asyncio.wait_for(
                _call_off_the_loop(turn.on_approval, event), turn.remaining()
            )
            # A coroutine callback is created in the thread and awaited here,
            # under the same deadline.
            return await asyncio.wait_for(_maybe_await(decision), turn.remaining())
        except asyncio.TimeoutError:
            raise _ApprovalTimedOut(event) from None

    def _approval_pending(self, event: Dict[str, Any]) -> "ApprovalPendingError":
        sid = self._known_session_id()
        return ApprovalPendingError(
            f"The agent is waiting for approval to run {event.get('tool')!r} with "
            f"{json.dumps(event.get('arguments'), default=str)[:200]} in session {sid}. "
            f"Answer it with agent.respond_to_approval(True) or (False), pass "
            f"on_approval= to input() to answer such requests as they come, or "
            f"call agent.stop() to end the turn.",
            session_id=sid,
            request=event,
        )

    def _turn_lost(self, turn: "_Turn", why: str) -> "TurnLostError":
        sid = self._known_session_id()
        self._status = "idle"
        return TurnLostError(
            f"The connection to the agent closed mid-turn ({turn.closed or 'no reason given'}) "
            f"and the turn could not be picked up again: {why}. Session {sid}. The "
            f"prompt was not sent again, because running it twice could repeat its "
            f"tool calls; input() continues the session.",
            session_id=sid,
        )

    def _known_session_id(self) -> Optional[str]:
        if isinstance(self._current_session, dict) and self._current_session.get("session_id"):
            return self._current_session["session_id"]
        return self._session_id

    @staticmethod
    def _refuse_inside_event_loop(name: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError(
            f"{name}() cannot be used inside async context. "
            f"Use 'await agent.{name}_async()' instead."
        )

    async def _wait_for_mode_connected(self, ws) -> Dict[str, Any]:
        while True:
            event = json.loads(await ws.recv())
            event_type = event.get("type")
            if event_type == "CONNECTED":
                state = self._consume_connected_mode_state(event)
                if state is None:
                    raise ConnectionError(
                        "Host does not support acknowledged OIP modes"
                    )
                return state
            if event_type == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
            elif event_type == "ERROR":
                raise self._auth_error(event)

    def _auth_error(self, event: dict) -> ConnectionError:
        """The host's refusal, plus the way out when the refusal is our missing identity.

        From a HOME with no ~/.co, 1.8.8b9 raised only "Auth error:
        unauthorized: signed request required" -- true, and no help to someone
        who never ran `co init` and does not know a client needs keys at all.
        """
        detail = event.get('message', event.get('error'))
        message = f"Auth error: {detail}"
        if self._found_no_identity and "signed request required" in str(detail):
            message += (
                ". This agent answers only signed requests, and there is no identity "
                "here to sign with: no .co/keys in this project and none in ~/.co. "
                "Run `co init` once to create one, or pass keys= to connect()."
            )
        return ConnectionError(message)

    async def _wait_for_mode_response(
        self, ws, expected_mode: str,
    ) -> None:
        while True:
            event = json.loads(await ws.recv())
            event_type = event.get("type")
            if event_type == "PING":
                await ws.send(json.dumps({"type": "PONG"}))
                continue
            if event_type == "ERROR":
                raise ConnectionError(
                    event.get("message", "Session mode change failed")
                )
            if event_type != "mode_changed":
                self._handle_stream_event(event)
                continue
            try:
                acknowledged, turns_left = _validated_remote_mode_state(
                    event.get("mode"), event.get("turns_left")
                )
            except ValueError:
                raise PermissionModeError(
                    -32602, "Host acknowledged an invalid mode"
                ) from None
            if acknowledged != expected_mode:
                raise PermissionModeError(-32602, "Host acknowledged another mode")
            set_mode(
                self._current_session,
                acknowledged,
                turns_left=turns_left,
            )
            return

    def _consume_connected_mode_state(
        self, event: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        sid = event.get("session_id")
        if sid and not self._current_session:
            self._current_session = {"session_id": sid}
        elif sid and self._current_session:
            self._current_session["session_id"] = sid
        state = event.get("session_modes")
        if not isinstance(state, dict):
            state = None
        if state is None:
            self._available_modes = []
            return None
        available = state.get("availableModes")
        if not isinstance(available, list):
            raise PermissionModeError(-32602, "Host advertised invalid modes")
        try:
            available_ids = [mode_id(item.get("id")) for item in available]
            current, turns_left = _validated_remote_mode_state(
                state.get("currentModeId"), state.get("turnsLeft")
            )
        except (AttributeError, ValueError):
            raise PermissionModeError(-32602, "Host advertised invalid mode state") from None
        if len(available_ids) != len(set(available_ids)) or current not in available_ids:
            raise PermissionModeError(-32602, "Host advertised inconsistent modes")
        self._available_modes = copy.deepcopy(available)
        if self._current_session is not None:
            set_mode(self._current_session, current, turns_left=turns_left)
        return state

    def _build_connect_message(
        self, is_direct: bool = False, last_msg_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build CONNECT message with signing.

        `last_msg_id` reattaches to a running turn from just after the last
        event this client saw, so nothing it already handled is replayed.
        """
        connect_msg: Dict[str, Any] = {
            "type": "CONNECT",
            "timestamp": int(time.time())
        }

        if not is_direct:
            connect_msg["to"] = self.address

        # CONNECTED's id counts too: a turn that has not produced an OUTPUT
        # yet is still in that session, and reopening it needs the id.
        if self._known_session_id():
            connect_msg["session_id"] = self._known_session_id()
        if last_msg_id:
            connect_msg["last_msg_id"] = last_msg_id

        # Send conversation history with CONNECT
        if self._current_session:
            connect_msg["session"] = self._current_session

        if self._keys:
            payload: Dict[str, Any] = {
                "to": self.address,
                "timestamp": connect_msg["timestamp"],
                "signed_commands": 1,
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            signature = addr.sign(self._keys, canonical.encode())
            connect_msg["payload"] = payload
            connect_msg["from"] = self._keys["address"]
            connect_msg["signature"] = signature.hex()

        return connect_msg

    def _build_input_message(
        self,
        prompt: str,
        input_id: str,
        is_direct: bool = False,
        images: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build INPUT message with optional signing."""
        input_msg: Dict[str, Any] = {
            "type": "INPUT",
            "input_id": input_id,
            "prompt": prompt,
        }

        # Only include 'to' for relay mode (not needed for direct connection)
        if not is_direct:
            input_msg["to"] = self.address

        # Session goes with CONNECT, not INPUT

        # Add multimodal attachments
        if images:
            input_msg["images"] = images
        if files:
            input_msg["files"] = files

        return self._build_command_message(input_msg, is_direct)

    def _build_command_message(
        self, message: Dict[str, Any], is_direct: bool = False
    ) -> Dict[str, Any]:
        """Sign one complete application command for protocol-v2 hosts.

        Fields remain duplicated at the top level so pre-v2 hosts can consume
        the frame. A v2 host discards those copies and executes this payload.
        """
        command = copy.deepcopy(message)
        command["timestamp"] = int(time.time())
        command["nonce"] = str(uuid.uuid4())
        # Recipient stays in the signature even on a direct socket. Only the
        # relay needs it for routing, but the host needs it to prevent a frame
        # captured for one agent from being delivered to another.
        command["to"] = self.address

        frame = copy.deepcopy(command)
        if self._keys:
            canonical = json.dumps(command, sort_keys=True, separators=(',', ':'))
            frame["payload"] = command
            frame["from"] = self._keys["address"]
            frame["signature"] = addr.sign(self._keys, canonical.encode()).hex()
        return frame

    def _build_onboard_submit(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Build ONBOARD_SUBMIT message with optional signing."""
        payload = {
            "timestamp": int(time.time()),
            **credentials
        }

        submit_msg: Dict[str, Any] = {
            "type": "ONBOARD_SUBMIT",
            "payload": payload
        }

        # Sign if keys provided
        if self._keys:
            canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            signature = addr.sign(self._keys, canonical.encode())
            submit_msg["from"] = self._keys["address"]
            submit_msg["signature"] = signature.hex()

        return submit_msg

    def _prompt_onboard(self, methods: List[str], payment_amount: Optional[float]) -> Dict[str, Any]:
        """Prompt user interactively for onboard credentials."""
        print("\n🔐 Access verification required")
        print(f"   Available methods: {', '.join(methods)}")

        if "invite_code" in methods:
            code = input("   Enter invite code: ").strip()
            if code:
                return {"invite_code": code}

        if "payment" in methods and payment_amount:
            print(f"   Payment required: ${payment_amount}")
            confirm = input("   Pay now? [y/N]: ").strip().lower()
            if confirm == 'y':
                return {"payment": payment_amount}

        raise ValueError("No valid onboard credentials provided")

    def _handle_stream_event(self, event: Dict[str, Any]) -> None:
        """Handle streaming event and update UI."""
        event_type = event.get("type")

        if event_type == "tool_call":
            tool_id = event.get("tool_id") or event.get("id")
            existing = next((
                item for item in self._ui_events
                if item.get("type") == "tool_call"
                and (item.get("tool_id") or item.get("id")) == tool_id
            ), None)
            tool_item = {
                "type": "tool_call",
                "id": event.get("id"),
                # The LLM's call id, which the result carries too. `id` is this
                # event's own and differs between the call and its result.
                "tool_id": tool_id,
                "name": event.get("name"),
                "args": event.get("args"),
                "status": _tool_ui_status(event.get("status")),
            }
            if isinstance(event.get("summary"), str) and event["summary"]:
                tool_item["summary"] = event["summary"]
            if existing is None:
                self._add_ui_event(tool_item)
            else:
                existing.update(tool_item)

        elif event_type == "tool_call_update":
            tool_id = event.get("tool_id") or event.get("id")
            existing = next((
                item for item in self._ui_events
                if item.get("type") == "tool_call"
                and (item.get("tool_id") or item.get("id")) == tool_id
            ), None)
            if existing is not None:
                if event.get("status") is not None:
                    existing["status"] = _tool_ui_status(event["status"])
                for field in ("name", "args", "summary", "result", "timing_ms"):
                    if field in event:
                        existing[field] = event[field]

        elif event_type == "tool_result":
            # Correlate on tool_id -- the LLM's call id, which both frames
            # share. This read `id`, which is per-event and differs between the
            # call and its result, so the match never succeeded and every tool
            # stayed "running" for the rest of the session however it finished.
            # The replayed path (session/ui.py) has always keyed on tool_id.
            # `id` remains the fallback for a frame that carries no tool_id.
            key = event.get("tool_id") or event.get("id")
            for ui_event in self._ui_events:
                if ui_event.get("type") == "tool_call" and (
                    ui_event.get("tool_id") or ui_event.get("id")
                ) == key:
                    ui_event["status"] = _tool_ui_status(
                        event.get("status"), terminal=True
                    )
                    ui_event["result"] = event.get("result")
                    break

        elif event_type == "thinking":
            self._add_ui_event({"type": "thinking"})

        elif event_type == "user_input":
            # Already added when input() called, skip
            pass

        elif event_type == "assistant":
            self._add_ui_event({
                "type": "agent",
                "content": event.get("content")
            })

        elif event_type == "mode_changed":
            if not isinstance(self._current_session, dict):
                return
            current_session_id = self._current_session.get("session_id")
            event_session_id = event.get("session_id")
            if (
                event_session_id is not None
                and event_session_id != current_session_id
            ):
                return
            try:
                mode, turns_left = _validated_remote_mode_state(
                    event.get("mode"), event.get("turns_left")
                )
            except ValueError:
                return
            set_mode(self._current_session, mode, turns_left=turns_left)

        elif event_type == "llm_call":
            # Internal event, add thinking indicator if not already present
            if not any(e.get("type") == "thinking" for e in self._ui_events[-3:]):
                self._add_ui_event({"type": "thinking"})

    def _add_ui_event(self, event: Dict[str, Any]) -> None:
        """Add event to UI with auto-generated id."""
        if "id" not in event:
            event["id"] = str(len(self._ui_events) + 1)
        self._ui_events.append(event)

    def __repr__(self):
        short = self.address[:12] + "..." if len(self.address) > 12 else self.address
        return f"RemoteAgent({short})"


def connect(
    address: str,
    *,
    keys: Optional[Dict[str, Any]] = None,
    relay_url: Optional[str] = None,
) -> RemoteAgent:
    """
    Connect to a remote agent.

    Args:
        address: Agent's public key address (0x...)
        keys: Signing keys. Omit them and this project's identity is used
              (then this machine's ~/.co). Every trust level above `open`
              refuses an unsigned request, `careful` included. Pass
              keys=False to connect anonymously to a `trust: open` agent.
        relay_url: Relay server base URL (default: the configured backend)

    Returns:
        RemoteAgent interface with real-time UI updates

    Example:
        >>> from connectonion import connect
        >>>
        >>> agent = connect("0x3d4017c3...")
        >>> response = agent.input("Book a flight")
        >>> print(response.text)   # "Which date?"
        >>> print(response.done)   # False
        >>> print(agent.ui)        # All events for rendering
        >>> print(agent.status)    # 'waiting'
        >>>
        >>> response = agent.input("March 15")
        >>> print(response.text)   # "Booked! Confirmation #ABC123"
        >>> print(response.done)   # True
    """
    return RemoteAgent(address, keys=keys, relay_url=relay_url)
