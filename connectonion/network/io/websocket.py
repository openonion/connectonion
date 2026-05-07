"""
Purpose: WebSocket IO bridging async WebSocket transport to sync agent code via thread-safe message channels
LLM-Note:
  Dependencies: imports from [network/io/base.IO, asyncio, threading, time, uuid] | imported by [network/host/ws_router.py] | tested by [tests/unit/test_io.py, tests/unit/test_io_image_support.py]
  Data flow: agent calls io.send(event) → auto-stamps id (UUID) and ts if missing → enqueues for async forwarder | client message → enqueued for agent | read_agent_messages() async-iterates outgoing for forwarding to client | send_to_agent() pushes incoming messages to agent
  State/Effects: maintains incoming + outgoing channels (async-safe) | finished flag prevents sends after close | unblocks agent's blocking receive on close
  Integration: exposes WebSocketIO() implementing IO interface | send/receive for agent-side, read_agent_messages/send_to_agent for transport-side, finish() to terminate
  Performance: queue-based coordination between sync agent thread and async transport | blocking receive() is intended for agent thread
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

    def __init__(self):
        # ── Agent messages (agent→client) ──
        self._agent_messages: list[Dict[str, Any]] = []
        self._agent_condition = threading.Condition()
        self._finished = False
        self._cursor = 0

        # ── Client messages (client→agent) ──
        self._client_messages: list[Dict[str, Any]] = []
        self._client_condition = threading.Condition()

        # ── Interjections (client→agent, separate from receive()) ──
        self._interjections: list[Dict[str, Any]] = []
        self._interjection_lock = threading.Lock()

        self._closed = False

    # ═══════════════════════════════════════════════════════
    # Agent side (sync)
    # ═══════════════════════════════════════════════════════

    def send(self, message: Dict[str, Any]) -> None:
        """Append message to outgoing log.

        Auto-generates 'id' (UUID) and 'ts' (timestamp) if not present.
        """
        if not self._closed:
            if 'id' not in message:
                message['id'] = str(uuid.uuid4())
            if 'ts' not in message:
                message['ts'] = time.time()
            with self._agent_condition:
                self._agent_messages.append(message)
                self._agent_condition.notify_all()

    def receive(self) -> Dict[str, Any]:
        """Block until client message arrives."""
        with self._client_condition:
            while not self._client_messages:
                self._client_condition.wait()
            return self._client_messages.pop(0)

    def receive_all(self, msg_type: str = None) -> list[Dict[str, Any]]:
        """Take matching client messages, leave others (non-blocking)."""
        with self._client_condition:
            if msg_type is None:
                result = list(self._client_messages)
                self._client_messages.clear()
                return result
            matched = []
            remaining = []
            for msg in self._client_messages:
                if msg.get('type') == msg_type:
                    matched.append(msg)
                else:
                    remaining.append(msg)
            self._client_messages[:] = remaining
            return matched

    def finish(self):
        """Signal that agent is done producing messages."""
        with self._agent_condition:
            self._finished = True
            self._agent_condition.notify_all()

    def close(self):
        """Mark IO as closed (prevents further sends)."""
        self._closed = True

    # ═══════════════════════════════════════════════════════
    # Transport side (async)
    # ═══════════════════════════════════════════════════════

    def send_to_agent(self, msg: Dict[str, Any]) -> None:
        """Deliver client message to agent mailbox."""
        with self._client_condition:
            self._client_messages.append(msg)
            self._client_condition.notify_all()

    def push_interjection(self, msg: Dict[str, Any]) -> None:
        """Queue a mid-execution user message; agent drains at next iteration."""
        with self._interjection_lock:
            self._interjections.append(msg)

    def pop_interjections(self) -> list[Dict[str, Any]]:
        """Drain queued interjections (agent calls at iteration start)."""
        with self._interjection_lock:
            result = list(self._interjections)
            self._interjections.clear()
            return result

    def rewind_to(self, last_msg_id=None):
        """Rewind cursor for replay on reconnect. None or unknown id → replay all."""
        with self._agent_condition:
            if last_msg_id is None:
                self._cursor = 0
                return
            for i, msg in enumerate(self._agent_messages):
                if msg.get('id') == last_msg_id:
                    self._cursor = i + 1
                    return
            self._cursor = 0

    def _wait_for_agent_messages(self, cursor, stop_event=None):
        """Block until new agent messages available or finished. Returns (messages, done)."""
        with self._agent_condition:
            while len(self._agent_messages) <= cursor and not self._finished:
                if stop_event and stop_event.is_set():
                    return [], True
                self._agent_condition.wait(timeout=1.0)
            if stop_event and stop_event.is_set():
                return [], True
            return list(self._agent_messages[cursor:]), self._finished

    async def read_agent_messages(self, stop_event=None):
        """Async iterator over agent messages. Resumes from last cursor position."""
        loop = asyncio.get_event_loop()
        cursor = self._cursor
        while True:
            new_messages, done = await loop.run_in_executor(
                None, self._wait_for_agent_messages, cursor, stop_event
            )
            if done and not new_messages:
                return
            for msg in new_messages:
                yield msg
                cursor += 1
                self._cursor = cursor
            if done:
                return

    @property
    def message_count(self):
        with self._agent_condition:
            return len(self._agent_messages)
