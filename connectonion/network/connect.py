"""
Purpose: Python client for remote ConnectOnion agents — signed transport, acknowledged Host modes, streaming UI events, and onboarding.
LLM-Note:
  Dependencies: imports from [asyncio, copy, json, time, uuid, dataclasses, typing, httpx, websockets (lazy), ..address (sign)] | imported by [network/__init__.py, connectonion/__init__.py]
  Data flow: input() sends signed CONNECT/INPUT and consumes stream/OUTPUT | set_session_mode() validates Host state, sends signed OIP mode_change, and waits for mode_changed
  State/Effects: mutates current session/modes/UI/status only from authenticated carrier responses; opens outbound sockets; signs deep-detached command payloads; endpoint resolution may query relay and candidate /info endpoints
  Integration: exposes connect(), RemoteAgent, Response, ExecResult, PermissionModeError; RemoteAgent provides input/call/set_session_mode sync+async actions and read-only state
  Performance: endpoint resolution attempted once per RemoteAgent (cached in _endpoint_resolved/_resolved_endpoint) | per-recv asyncio.wait_for to avoid hangs (default timeout=60s, 30s for CONNECTED) | sync .input() rejected inside running event loop (use input_async)
  Errors: raises ConnectionError on transport/auth failure, PermissionModeError on owned policy refusal, TimeoutError on receive timeout, RuntimeError for sync calls in async contexts, ValueError for invalid choices
Protocol: CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
See docs/network/websocket-protocol.md for full specification.

Lifecycle:
  1. connect(address) creates RemoteAgent instance
  2. agent.input(prompt) opens WebSocket, sends CONNECT to authenticate
  3. Server responds with CONNECTED { session_id, status }
  4. Client sends INPUT { prompt }
  5. Receives streaming events: tool_call, tool_result, thinking, assistant
  6. Receives final OUTPUT or ask_user
  7. Returns Response(text, done)
"""

import asyncio
import copy
import json
import sys
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
        http_endpoints = [ep for ep in sorted_endpoints
                          if (ep.startswith("http://") or ep.startswith("https://"))
                          and endpoint_is_safe(ep)]

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

    @property
    def status(self) -> str:
        """Current status: 'idle' | 'working' | 'waiting'"""
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
    ) -> Response:
        """
        Send prompt to remote agent and get response.

        Returns Response(text, done) where:
        - done=True: Task complete
        - done=False: Agent asked a question, send another input to answer

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 60)
            on_onboard: Callback when agent requires onboarding (invite code or payment).
                        Called with (methods: list[str], payment_amount: float | None).
                        Should return {"invite_code": "..."} or {"payment": amount}.
                        If None, prompts interactively in terminal.
            images: Optional list of base64 data URLs for multimodal input
            files: Optional list of file dicts with name and base64 data

        Returns:
            Response with text and done flag

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
        return asyncio.run(self._stream_input(prompt, timeout, on_onboard, images, files))

    async def input_async(
        self,
        prompt: str,
        timeout: float = 60.0,
        on_onboard: Optional[Callable[[List[str], Optional[float]], Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Response:
        """Async version of input()."""
        return await self._stream_input(prompt, timeout, on_onboard, images, files)

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
                return await websockets.connect(ws_url), is_direct
            except OSError:
                if not is_direct:
                    raise          # the relay is the last resort; there is no next
                self._forget_direct_endpoint()

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
    ) -> Response:
        """Send prompt via WebSocket and stream events."""
        import websockets

        self._status = "working"

        # Try endpoint resolution (once, cached)
        await self._try_resolve_endpoint()

        # Add user event to UI
        self._add_ui_event({
            "type": "user",
            "content": prompt
        })

        # Generate input_id for routing/response matching
        input_id = str(uuid.uuid4())

        # The agent itself when it answers, the relay behind it when it does not.
        connection, is_direct = await self._open_best_connection(websockets)

        # Build the CONNECT and INPUT messages -- after opening, because both are
        # shaped by which way answered and a relay-bound frame is not a direct one.
        connect_msg = self._build_connect_message(is_direct)
        input_msg = self._build_input_message(prompt, input_id, is_direct, images, files)

        try:
            async with connection as ws:
                # Authenticate first
                await ws.send(json.dumps(connect_msg))

                # Wait for CONNECTED
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    event = json.loads(raw)
                    if event.get("type") == "CONNECTED":
                        self._consume_connected_mode_state(event)
                        break
                    elif event.get("type") == "ERROR":
                        self._status = "idle"
                        raise ConnectionError(f"Auth error: {event.get('message', event.get('error'))}")
                    elif event.get("type") == "ONBOARD_REQUIRED":
                        # Handle onboard during connect
                        methods = event.get("methods", [])
                        payment_amount = event.get("payment_amount")
                        self._add_ui_event({"type": "onboard_required", "methods": methods, "payment_amount": payment_amount})
                        if on_onboard:
                            credentials = on_onboard(methods, payment_amount)
                        else:
                            credentials = self._prompt_onboard(methods, payment_amount)
                        submit_msg = self._build_onboard_submit(credentials)
                        await ws.send(json.dumps(submit_msg))
                        # Continue waiting for CONNECTED or ONBOARD_SUCCESS

                # Now send INPUT
                await ws.send(json.dumps(input_msg))

                # Stream events until OUTPUT or timeout
                result_text = ""
                done = True

                while True:
                    # Wrap recv in timeout to prevent hanging indefinitely
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    event = json.loads(msg)
                    event_type = event.get("type")

                    if event_type == "OUTPUT":
                        # Final result
                        result_text = event.get("result", "")
                        self._current_session = event.get("session")
                        self._status = "idle"

                        # Add agent response to UI
                        self._add_ui_event({
                            "type": "agent",
                            "content": result_text
                        })
                        break

                    elif event_type == "ERROR":
                        self._status = "idle"
                        raise ConnectionError(f"Agent error: {event.get('message', event.get('error'))}")

                    elif event_type == "ONBOARD_REQUIRED":
                        # Agent requires onboarding (invite code or payment)
                        methods = event.get("methods", [])
                        payment_amount = event.get("payment_amount")

                        # Add onboard_required event to UI
                        self._add_ui_event({
                            "type": "onboard_required",
                            "methods": methods,
                            "payment_amount": payment_amount
                        })

                        # Get credentials from callback or prompt interactively
                        if on_onboard:
                            credentials = on_onboard(methods, payment_amount)
                        else:
                            credentials = self._prompt_onboard(methods, payment_amount)

                        # Send ONBOARD_SUBMIT
                        submit_msg = self._build_onboard_submit(credentials)
                        await ws.send(json.dumps(submit_msg))
                        # Continue loop to wait for ONBOARD_SUCCESS

                    elif event_type == "ONBOARD_SUCCESS":
                        # Onboard successful - add to UI
                        self._add_ui_event({
                            "type": "onboard_success",
                            "level": event.get("level", "contact"),
                            "message": event.get("message", "Onboard successful")
                        })

                        # Retry the original prompt
                        retry_input_id = str(uuid.uuid4())
                        retry_msg = self._build_input_message(prompt, retry_input_id, is_direct)
                        await ws.send(json.dumps(retry_msg))
                        # Continue loop to wait for OUTPUT

                    elif event_type == "ask_user":
                        # Agent is asking a question - return done=False so caller sends another input()
                        #
                        # `question` is the field the tool sends. This read `text`,
                        # which no producer has ever sent -- useful_tools/ask_user.py
                        # and diff_writer.py both send `question` -- so every
                        # multi-turn conversation over the network arrived with the
                        # question missing and the options intact, the one field
                        # both sides happened to spell alike. `text` stays accepted
                        # for anything built against the old shape.
                        self._status = "waiting"
                        done = False
                        result_text = event.get("question") or event.get("text") or ""

                        # multi_select and fields were dropped: a client could not
                        # tell one answer from many, and a form asked for over the
                        # network could not be rendered at all.
                        asked = {
                            "type": "ask_user",
                            "text": result_text,
                            "options": event.get("options"),
                            "multi_select": event.get("multi_select"),
                        }
                        if event.get("fields") is not None:
                            asked["fields"] = event["fields"]
                        self._add_ui_event(asked)
                        break

                    else:
                        # Stream event (tool_call, tool_result, thinking, etc.)
                        self._handle_stream_event(event)

                return Response(text=result_text, done=done)

        except asyncio.TimeoutError:
            self._status = "idle"
            raise TimeoutError(f"Request timed out after {timeout}s")

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
                raise ConnectionError(
                    f"Auth error: {event.get('message', event.get('error'))}"
                )

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

    def _build_connect_message(self, is_direct: bool = False) -> Dict[str, Any]:
        """Build CONNECT message with signing."""
        connect_msg: Dict[str, Any] = {
            "type": "CONNECT",
            "timestamp": int(time.time())
        }

        if not is_direct:
            connect_msg["to"] = self.address

        if self._current_session and self._current_session.get("session_id"):
            connect_msg["session_id"] = self._current_session["session_id"]

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
