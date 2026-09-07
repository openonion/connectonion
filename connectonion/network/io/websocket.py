"""
Purpose: WebSocket IO bridging async WebSocket transport to sync agent code via thread-safe message channels
LLM-Note:
  Dependencies: imports from [network/io/base.IO, asyncio, threading, time, uuid] | imported by [network/host/ws_router/agent_io.py] | tested by [tests/unit/test_io.py, tests/unit/test_io_image_support.py]
  Data flow: agent calls io.send(event) → auto-stamps id (UUID) and ts if missing → enqueues for async forwarder | Agent._record_trace() calls internal _send_persisted_trace(event) → queues a private dict subtype as Host-local provenance | client message → enqueued for agent | read_msgs_from_agent() async-iterates outgoing for forwarding to client | send_to_agent() pushes incoming messages to agent
  State/Effects: maintains incoming + outgoing channels (async-safe) | finished flag prevents sends after close | unblocks agent's blocking receive on close
  Integration: exposes WebSocketIO() implementing IO interface | send/receive for agent-side, internal persisted-trace provenance queried by Host forwarder, read_msgs_from_agent/send_to_agent for transport-side, push_runtime_input/pop_runtime_inputs/finish_runtime_inputs for lossless mid-execution interjection, rewind_to(last_msg_id) for replay on reconnect, mark_agent_done() to terminate
  Performance: queue-based coordination between sync agent thread and async transport | blocking receive() is intended for agent thread | _wait_for_msgs_from_agent waits at most ~1s so idle-session forwarders don't pin executor-pool threads
  Errors: closed IO unblocks pending receive() so agent thread doesn't hang | no exceptions raised — channel coordination handled internally
"""

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from .base import IO


class _PersistedTraceEvent(dict):
    """Cooperative Host-local provenance; never an extra wire field or sandbox."""


@dataclass(frozen=True)
class ProviderInterruptResult:
    """Host decision for one correlated provider Stop request.

    The boolean behavior intentionally preserves the old duck-typed internal
    API while exposing the revision an acknowledged browser must retain across
    reconnect/replay.
    """

    accepted: bool
    state_revision: int | None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.accepted


@dataclass(frozen=True)
class ProviderInputResult:
    """Host decision for one direct native-provider message."""

    accepted: bool
    state_revision: int | None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.accepted


class WebSocketIO(IO):
    """Bridge async WebSocket to sync IO interface.

    Two independent channels:
    - Agent messages (agent→client): append-only log, cursor-based, replayable on reconnect
    - Client messages (client→agent): mailbox, selective receive, consumed on read
    """

    def __init__(self):
        # ── Agent messages (agent→client) ──
        self._msgs_from_agent: list[Dict[str, Any]] = []
        self._agent_condition = threading.Condition()
        # Provider invocation IDs are public correlation values, not authority.
        # The Host still owns the live lease, but it can reject a stale Stop
        # immediately instead of leaving the browser with a permanently pending
        # local button state.
        self._live_provider_invocations: dict[str, int | None] = {}
        self._live_provider_names: dict[str, str] = {}
        # Retain the latest semantic revision even after a terminal event. A
        # tool's durable trace can replay earlier lifecycle entries after its
        # live lane has already published the terminal state.
        self._latest_provider_revisions: dict[str, int] = {}
        self._provider_condition = threading.Condition()
        self._finished = False
        self._cursor = 0

        # ── Client messages (client→agent) ──
        self._msgs_from_client: list[Dict[str, Any]] = []
        self._client_condition = threading.Condition()

        # ── Runtime input (client→agent, separate from receive()) ──
        self._runtime_inputs: list[Dict[str, Any]] = []
        self._runtime_input_lock = threading.Lock()
        # Runtime input is opt-in. The plugin opens this at each turn boundary;
        # without it, the host must reject rather than ACK a queue nobody drains.
        self._accepting_runtime_inputs = False

        self._closed = False
        self._pending_permission: Dict[str, Any] | None = None
        self._interrupt_requested = False

    # ═══════════════════════════════════════════════════════
    # Agent side (sync)
    # ═══════════════════════════════════════════════════════

    def send(self, message: Dict[str, Any]) -> None:
        """Append message to outgoing log.

        Auto-generates 'id' (UUID) and 'ts' (timestamp) if not present.
        """
        self._append_agent_message(message)

    def _send_persisted_trace(self, message: Dict[str, Any]) -> None:
        """Queue one canonical trace event with cooperative Host provenance."""
        self._append_agent_message(_PersistedTraceEvent(message))

    @staticmethod
    def is_persisted_trace_event(message: Dict[str, Any]) -> bool:
        """Return whether this exact queued event came from Agent._record_trace."""
        return isinstance(message, _PersistedTraceEvent)

    def _append_agent_message(self, message: Dict[str, Any]) -> None:
        """Stamp and append one agent event to the replayable outgoing log."""
        if not self._closed:
            if 'id' not in message:
                message['id'] = str(uuid.uuid4())
            if 'ts' not in message:
                message['ts'] = time.time()
            self._track_provider_invocation(message)
            with self._agent_condition:
                self._msgs_from_agent.append(message)
                self._agent_condition.notify_all()

    def _track_provider_invocation(self, message: Dict[str, Any]) -> None:
        """Keep the transport-side index aligned with typed provider lifecycle frames."""
        if message.get("type") != "provider_invocation":
            return
        invocation_id = message.get("invocationId")
        if not isinstance(invocation_id, str) or not invocation_id:
            return
        state_revision = message.get("stateRevision")
        if (
            isinstance(state_revision, bool)
            or not isinstance(state_revision, int)
            or state_revision < 1
        ):
            state_revision = None
        with self._provider_condition:
            known_revision = self._latest_provider_revisions.get(invocation_id)
            if known_revision is not None:
                # A versioned state must never regress. Once this Host has seen
                # a version, an unversioned compatibility replay is also too
                # weak to reactivate the invocation.
                if state_revision is None or state_revision <= known_revision:
                    return
            if state_revision is not None:
                self._latest_provider_revisions[invocation_id] = state_revision
            if message.get("status") in {"completed", "failed", "cancelled"}:
                self._live_provider_invocations.pop(invocation_id, None)
                self._live_provider_names.pop(invocation_id, None)
            else:
                self._live_provider_invocations[invocation_id] = state_revision
                provider = message.get("provider")
                if provider in {"codex", "claude_code"}:
                    self._live_provider_names[invocation_id] = provider

    def receive(self) -> Dict[str, Any]:
        """Block until client message arrives."""
        with self._client_condition:
            while not self._msgs_from_client:
                self._client_condition.wait()
            return self._msgs_from_client.pop(0)

    def receive_interruptibly(self, cancel_event) -> Dict[str, Any]:
        """Receive one message without letting a cancelled caller steal later input."""
        with self._client_condition:
            while not self._msgs_from_client and not cancel_event.is_set():
                self._client_condition.wait(timeout=0.05)
            if cancel_event.is_set():
                return {"type": "INTERRUPT"}
            return self._msgs_from_client.pop(0)

    def receive_all_interruptibly(self, cancel_event, msg_type: str = None):
        """Atomically refuse mailbox access after an invocation is cancelled."""
        with self._client_condition:
            if cancel_event.is_set():
                return None
            if msg_type is None:
                interrupts = [
                    message for message in self._msgs_from_client
                    if message.get("type") == "INTERRUPT"
                ]
                if interrupts:
                    # Signal cancellation without consuming unrelated frames.
                    self._msgs_from_client[:] = [
                        message for message in self._msgs_from_client
                        if message.get("type") != "INTERRUPT"
                    ]
                    return interrupts
                messages = self._msgs_from_client[:]
                self._msgs_from_client.clear()
                return messages
            matched = [m for m in self._msgs_from_client if m.get("type") == msg_type]
            self._msgs_from_client[:] = [
                m for m in self._msgs_from_client if m.get("type") != msg_type
            ]
            return matched

    def take_interrupt(self, on_interrupt=None) -> bool:
        """Drain one interrupt and revoke its worker lease under the same lock."""
        with self._client_condition:
            for index, message in enumerate(self._msgs_from_client):
                if message.get("type") == "INTERRUPT":
                    self._msgs_from_client.pop(index)
                    if on_interrupt:
                        on_interrupt()
                    self._client_condition.notify_all()
                    return True
            return False

    def take_provider_interrupt(self, invocation_id: str) -> bool:
        """Consume one Stop addressed to the exact live provider invocation."""
        if not isinstance(invocation_id, str) or not invocation_id:
            return False
        with self._client_condition:
            for index, message in enumerate(self._msgs_from_client):
                if (
                    message.get("type") == "PROVIDER_INTERRUPT"
                    and message.get("invocationId") == invocation_id
                ):
                    self._msgs_from_client.pop(index)
                    self._client_condition.notify_all()
                    return True
            return False

    def request_provider_interrupt(
        self,
        invocation_id: str,
        state_revision: int | None = None,
    ) -> ProviderInterruptResult:
        """Accept a Stop only for the exact live provider state the Host owns."""
        if not isinstance(invocation_id, str) or not invocation_id:
            return ProviderInterruptResult(False, None, "not_active")
        if (
            state_revision is not None
            and (
                isinstance(state_revision, bool)
                or not isinstance(state_revision, int)
                or state_revision < 1
            )
        ):
            return ProviderInterruptResult(False, None, "invalid_revision")
        with self._provider_condition:
            if invocation_id not in self._live_provider_invocations:
                return ProviderInterruptResult(False, None, "not_active")
            current_revision = self._live_provider_invocations[invocation_id]
            if state_revision is not None:
                if current_revision is None:
                    return ProviderInterruptResult(
                        False, None, "state_unconfirmed"
                    )
                if current_revision != state_revision:
                    return ProviderInterruptResult(
                        False, current_revision, "state_changed"
                    )
        frame = {"type": "PROVIDER_INTERRUPT", "invocationId": invocation_id}
        if state_revision is not None:
            frame["stateRevision"] = state_revision
        self.send_to_agent(frame)
        return ProviderInterruptResult(True, current_revision)

    def request_provider_input(
        self,
        invocation_id: str,
        state_revision: int | None,
        text: str,
        request_id: str,
    ) -> ProviderInputResult:
        """Queue an exact direct message only for a live steerable Codex run.

        A true result means the Host mailbox accepted the request, not that
        Codex accepted it.  The native adapter sends ``PROVIDER_INPUT_ACK``
        only after its matching ``turn/steer`` succeeds.
        """
        if (
            not isinstance(invocation_id, str)
            or not invocation_id
            or not isinstance(request_id, str)
            or not request_id
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 12_000
        ):
            return ProviderInputResult(False, None, "invalid_request")
        if (
            state_revision is not None
            and (
                isinstance(state_revision, bool)
                or not isinstance(state_revision, int)
                or state_revision < 1
            )
        ):
            return ProviderInputResult(False, None, "invalid_revision")
        with self._provider_condition:
            if invocation_id not in self._live_provider_invocations:
                return ProviderInputResult(False, None, "not_active")
            if self._live_provider_names.get(invocation_id) != "codex":
                return ProviderInputResult(False, None, "unsupported_provider")
            current_revision = self._live_provider_invocations[invocation_id]
            if state_revision is not None:
                if current_revision is None:
                    return ProviderInputResult(False, None, "state_unconfirmed")
                if current_revision != state_revision:
                    return ProviderInputResult(False, current_revision, "state_changed")
        self.send_to_agent({
            "type": "PROVIDER_INPUT",
            "invocationId": invocation_id,
            "stateRevision": state_revision,
            "text": text.strip(),
            "requestId": request_id,
        })
        return ProviderInputResult(True, current_revision)

    def receive_all(self, msg_type: str = None) -> list[Dict[str, Any]]:
        """Take matching client messages, leave others (non-blocking)."""
        with self._client_condition:
            if msg_type is None:
                result = list(self._msgs_from_client)
                self._msgs_from_client.clear()
                return result
            matched = []
            remaining = []
            for msg in self._msgs_from_client:
                if msg.get('type') == msg_type:
                    matched.append(msg)
                else:
                    remaining.append(msg)
            self._msgs_from_client[:] = remaining
            return matched

    def mark_agent_done(self):
        """Signal that agent is done producing messages."""
        with self._provider_condition:
            self._live_provider_invocations.clear()
            self._live_provider_names.clear()
            self._latest_provider_revisions.clear()
        with self._agent_condition:
            self._finished = True
            self._agent_condition.notify_all()

    def close(self):
        """Mark IO as closed (prevents further sends)."""
        self._closed = True
        with self._provider_condition:
            self._live_provider_invocations.clear()
            self._live_provider_names.clear()
            self._latest_provider_revisions.clear()

    # ═══════════════════════════════════════════════════════
    # Transport side (async)
    # ═══════════════════════════════════════════════════════

    def send_to_agent(self, msg: Dict[str, Any]) -> None:
        """Deliver client message to agent mailbox."""
        with self._client_condition:
            self._msgs_from_client.append(msg)
            self._client_condition.notify_all()

    def request_interrupt(self) -> bool:
        """Deliver at most one interrupt for this turn's IO generation."""

        with self._client_condition:
            if self._interrupt_requested:
                return False
            self._interrupt_requested = True
            self._msgs_from_client.append({"type": "INTERRUPT"})
            self._client_condition.notify_all()
            return True

    def register_permission_request(
        self,
        event: Dict[str, Any],
        session_id: str,
    ) -> bool:
        """Bind one replayable approval event to this session's live mailbox."""

        request_id = event.get("id")
        if not isinstance(request_id, str) or not request_id:
            return False
        pending = {
            "request_id": request_id,
            "session_id": session_id,
            "tool_call_id": event.get("tool_call_id"),
        }
        with self._client_condition:
            if self._pending_permission is None:
                self._pending_permission = pending
                return True
            return self._pending_permission == pending

    def resolve_legacy_permission(self, response: Dict[str, Any]) -> bool:
        """Bind a rolling-upgrade legacy answer to the one pending request."""

        with self._client_condition:
            if self._pending_permission is None:
                return False
            self._pending_permission = None
            self._msgs_from_client.append(
                self._normalized_legacy_permission(response)
            )
            self._client_condition.notify_all()
            return True

    @staticmethod
    def _normalized_legacy_permission(response: Dict[str, Any]) -> Dict[str, Any]:
        """Accept only the legacy choices the policy gate actually implements."""

        rejected = {
            "approved": False,
            "scope": "once",
            "mode": "reject_hard",
        }
        approved = response.get("approved")
        if not isinstance(approved, bool):
            return rejected
        scope = response.get("scope", "once")
        if scope not in {"once", "session"}:
            return rejected
        if approved:
            return {"approved": True, "scope": scope}
        mode = response.get("mode", "reject_hard")
        if mode not in {"reject_soft", "reject_hard", "reject_explain"}:
            return rejected
        result = {"approved": False, "scope": "once", "mode": mode}
        feedback = response.get("feedback")
        if isinstance(feedback, str) and feedback:
            result["feedback"] = feedback
        return result

    def push_runtime_input(self, msg: Dict[str, Any]) -> bool:
        """Queue mid-execution input only while the current turn can consume it."""
        with self._runtime_input_lock:
            if not self._accepting_runtime_inputs:
                return False
            self._runtime_inputs.append(msg)
            return True

    def pop_runtime_inputs(self) -> list[Dict[str, Any]]:
        """Drain queued runtime inputs (agent calls at iteration start)."""
        with self._runtime_input_lock:
            result = list(self._runtime_inputs)
            self._runtime_inputs.clear()
            return result

    def finish_runtime_inputs(self) -> list[Dict[str, Any]]:
        """Atomically drain pending input or seal a turn that has none left.

        A non-empty result keeps acceptance open because the agent will run
        another iteration. An empty result seals the window, so transport code
        rejects rather than falsely acknowledges a too-late message.
        """
        with self._runtime_input_lock:
            result = list(self._runtime_inputs)
            self._runtime_inputs.clear()
            if not result:
                self._accepting_runtime_inputs = False
            return result

    def open_runtime_inputs(self) -> None:
        """Open a fresh turn's runtime-input window on a reused IO instance."""
        with self._runtime_input_lock:
            self._accepting_runtime_inputs = True

    def rewind_to(self, last_msg_id=None):
        """Rewind cursor for replay on reconnect. None or unknown id → replay all."""
        with self._agent_condition:
            if last_msg_id is None:
                self._cursor = 0
                return
            for i, msg in enumerate(self._msgs_from_agent):
                if msg.get('id') == last_msg_id:
                    self._cursor = i + 1
                    return
            self._cursor = 0

    def _wait_for_msgs_from_agent(self, cursor, stop_event=None):
        """Wait up to ~1s for new agent messages. Returns (messages, done).

        Must return promptly even with no news: this runs on the event loop's
        shared default executor, and a forwarder for an idle session (agent
        blocked in receive()) would otherwise pin a pool thread forever —
        enough idle sessions exhaust the pool and starve every new connection.
        """
        with self._agent_condition:
            if len(self._msgs_from_agent) <= cursor and not self._finished:
                self._agent_condition.wait(timeout=1.0)
            if stop_event and stop_event.is_set():
                return [], True
            return list(self._msgs_from_agent[cursor:]), self._finished

    async def read_msgs_from_agent(self, stop_event=None):
        """Async iterator over agent messages. Resumes from last cursor position."""
        loop = asyncio.get_event_loop()
        cursor = self._cursor
        while True:
            new_messages, done = await loop.run_in_executor(
                None, self._wait_for_msgs_from_agent, cursor, stop_event
            )
            if done and not new_messages:
                return
            for msg in new_messages:
                yield msg
                cursor += 1
            # Batch-publish cursor under the lock so a concurrent rewind_to()
            # (taking the same lock) can't be silently overwritten by an
            # in-flight reader still finishing its yield loop.
            with self._agent_condition:
                self._cursor = cursor
            if done:
                return

    @property
    def message_count(self):
        with self._agent_condition:
            return len(self._msgs_from_agent)
