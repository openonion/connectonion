"""
Purpose: WebSocket IO bridging async WebSocket transport to sync agent code via thread-safe message channels
LLM-Note:
  Dependencies: imports from [network/io/base.IO, asyncio, threading, time, uuid] | imported by [network/host/ws_router/agent_io.py] | tested by [tests/unit/test_io.py, tests/unit/test_io_image_support.py]
  Data flow: agent calls io.send(event) → auto-stamps id (UUID) and ts if missing → enqueues for async forwarder | client message → enqueued for agent | read_msgs_from_agent() async-iterates outgoing for forwarding to client | send_to_agent() pushes incoming messages to agent
  State/Effects: maintains incoming + outgoing channels (async-safe) | finished flag prevents sends after close | unblocks agent's blocking receive on close
  Integration: exposes WebSocketIO() implementing IO interface | send/receive for agent-side, read_msgs_from_agent/send_to_agent for transport-side, push_runtime_input/pop_runtime_inputs for mid-execution interjection, rewind_to(last_msg_id) for replay on reconnect, mark_agent_done() to terminate
  Performance: queue-based coordination between sync agent thread and async transport | blocking receive() is intended for agent thread | _wait_for_msgs_from_agent waits at most ~1s so idle-session forwarders don't pin executor-pool threads
  Errors: closed IO unblocks pending receive() so agent thread doesn't hang | no exceptions raised — channel coordination handled internally
"""

import asyncio
import threading
import time
import uuid
from typing import Any, Dict

from .base import IO


class WebSocketIO(IO):
    """Bridge async WebSocket to sync IO interface.

    Two independent channels:
    - Agent messages (agent→client): append-only log, cursor-based, replayable on reconnect
    - Client messages (client→agent): mailbox, selective receive, consumed on read
    """

    supports_interrupts = True

    def __init__(self):
        # ── Agent messages (agent→client) ──
        self._msgs_from_agent: list[Dict[str, Any]] = []
        self._agent_condition = threading.Condition()
        self._finished = False
        self._cursor = 0

        # ── Client messages (client→agent) ──
        self._msgs_from_client: list[Dict[str, Any]] = []
        self._client_condition = threading.Condition()

        # ── Runtime input (client→agent, separate from receive()) ──
        self._runtime_inputs: list[Dict[str, Any]] = []
        self._runtime_input_lock = threading.Lock()

        self._closed = False

    # ═══════════════════════════════════════════════════════
    # Agent side (sync)
    # ═══════════════════════════════════════════════════════

    def send(self, message: Dict[str, Any]) -> None:
        """Append message to outgoing log.

        Auto-generates 'id' (UUID) and 'ts' (timestamp) if not present.
        """
        with self._agent_condition:
            if self._closed:
                return
            if 'id' not in message:
                message['id'] = str(uuid.uuid4())
            if 'ts' not in message:
                message['ts'] = time.time()
            self._msgs_from_agent.append(message)
            self._agent_condition.notify_all()

    def receive(self) -> Dict[str, Any]:
        """Block until client message arrives."""
        with self._client_condition:
            while not self._msgs_from_client and not self._closed:
                self._client_condition.wait()
            if not self._msgs_from_client:
                return {'type': 'io_closed'}
            return self._msgs_from_client.pop(0)

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

    def requeue(self, message: Dict[str, Any]) -> None:
        """Restore a selectively received message to the agent mailbox."""
        with self._client_condition:
            self._msgs_from_client.append(message)
            self._client_condition.notify_all()

    def mark_agent_done(self):
        """Signal that agent is done producing messages."""
        with self._agent_condition:
            self._finished = True
            self._agent_condition.notify_all()

    def close(self):
        """Prevent further sends and unblock agent-side receive calls."""
        with self._agent_condition:
            self._closed = True
            self._agent_condition.notify_all()
        with self._client_condition:
            self._client_condition.notify_all()

    # ═══════════════════════════════════════════════════════
    # Transport side (async)
    # ═══════════════════════════════════════════════════════

    def send_to_agent(self, msg: Dict[str, Any]) -> None:
        """Deliver client message to agent mailbox."""
        self.requeue(msg)

    def push_runtime_input(self, msg: Dict[str, Any]) -> None:
        """Queue a mid-execution user message; agent drains at next iteration."""
        with self._runtime_input_lock:
            self._runtime_inputs.append(msg)

    def pop_runtime_inputs(self) -> list[Dict[str, Any]]:
        """Drain queued runtime inputs (agent calls at iteration start)."""
        with self._runtime_input_lock:
            result = list(self._runtime_inputs)
            self._runtime_inputs.clear()
            return result

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
