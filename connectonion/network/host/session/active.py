"""
Purpose: In-memory registry preserving running agents across WebSocket reconnections
LLM-Note:
  Dependencies: imports from [time, threading, dataclasses] | imported by [server.py, websocket.py, __init__.py]
  Data flow: websocket.py calls register(session_id, io, thread) → stores ActiveSession(status='executing') → agent finishes → mark_connected() → client disconnects → mark_suspended() → cleanup_expired() removes after 10min idle
  State/Effects: in-memory dict with threading.Lock | no persistence | background cleanup thread runs every 60s

Lifecycle:
    NEW: register() → status='executing'
    AGENT DONE: mark_connected() → status='connected' (session alive, ready for next INPUT)
    DISCONNECT: mark_suspended() → status='suspended' (grace period, agent may or may not be running)
    RECONNECT: get() → returns same session, update_ping() resets idle timer
    EXPIRED: cleanup_expired() removes 'connected' and 'suspended' after 10min idle
    NOTE: 'executing' sessions are NEVER cleaned up (agent still running)
"""

import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ActiveSession:
    """Session that clients can reconnect to."""
    session_id: str
    io: object                   # WebSocketIO with queues
    thread: threading.Thread     # Agent execution thread
    agent_finished: threading.Event  # Signals when agent thread completes
    created: float
    last_ping: float
    status: str                  # 'executing' | 'connected' | 'suspended'


class ActiveSessionRegistry:
    """Thread-safe registry: session_id → ActiveSession."""

    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}
        self._lock = threading.Lock()

    def register(self, session_id: str, io, thread, agent_finished) -> None:
        """Register a new execution."""
        with self._lock:
            self._sessions[session_id] = ActiveSession(
                session_id=session_id,
                io=io,
                thread=thread,
                agent_finished=agent_finished,
                created=time.time(),
                last_ping=time.time(),
                status='executing',
            )

    def get(self, session_id: str) -> Optional[ActiveSession]:
        """Get session by ID, or None if not found."""
        with self._lock:
            return self._sessions.get(session_id)

    def update_ping(self, session_id: str) -> None:
        """Update last activity timestamp."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].last_ping = time.time()

    def mark_suspended(self, session_id: str) -> None:
        """Mark as suspended (client disconnected)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = 'suspended'

    def mark_connected(self, session_id: str) -> None:
        """Mark as connected (execution finished, session alive for next INPUT)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = 'connected'

    def mark_executing(self, session_id: str, io, thread, agent_finished) -> None:
        """Start a new execution on an existing session."""
        with self._lock:
            if session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.io = io
                sess.thread = thread
                sess.agent_finished = agent_finished
                sess.status = 'executing'
                sess.last_ping = time.time()

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        to_remove = []

        with self._lock:
            for sid, sess in self._sessions.items():
                idle = now - sess.last_ping

                # Never clean up executing sessions (agent still running)
                # Clean up connected and suspended after 10min idle
                if sess.status in ('connected', 'suspended') and idle > 600:
                    to_remove.append(sid)

            for sid in to_remove:
                del self._sessions[sid]

        return len(to_remove)

    def list_active(self) -> list[str]:
        """List session IDs with active sessions."""
        with self._lock:
            return [sid for sid, sess in self._sessions.items()
                    if sess.status in ('executing', 'suspended')]

    def count(self) -> int:
        """Total sessions in registry."""
        with self._lock:
            return len(self._sessions)


def start_cleanup_job(registry: ActiveSessionRegistry) -> threading.Thread:
    """Start background cleanup daemon (runs every 60s)."""
    def cleanup_loop():
        while True:
            time.sleep(60)
            removed = registry.cleanup_expired()
            if removed > 0:
                print(f"[Registry] Cleaned up {removed} expired sessions")

    thread = threading.Thread(target=cleanup_loop, daemon=True, name="registry-cleanup")
    thread.start()
    return thread
