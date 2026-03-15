"""
Purpose: In-memory registry preserving running agents across WebSocket reconnections
LLM-Note:
  Dependencies: imports from [time, threading, dataclasses] | imported by [server.py, websocket.py, __init__.py] | tested by [tests/network/test_active_sessions.py]
  Data flow: websocket.py calls register(session_id, io, thread) → stores ActiveSession → client disconnects → mark_suspended() → client reconnects → get(session_id) returns same IO queue → agent finishes → mark_completed() → cleanup_expired() removes after 10min idle
  State/Effects: in-memory dict with threading.Lock | no persistence | background cleanup thread runs every 60s
  Integration: exposes ActiveSession dataclass, ActiveSessionRegistry class, start_cleanup_job() | used by websocket.py for reconnection, server.py creates instance
  Performance: O(1) lookup/insert | lock contention minimal (short critical sections) | cleanup runs in daemon thread
  Errors: none raised, returns None for missing sessions

Lifecycle:
    NEW: register() → status='running'
    DISCONNECT: mark_suspended() → status='suspended', agent keeps running
    RECONNECT: get() → returns same IO queue
    FINISHED: mark_completed() → status='completed'
    EXPIRED: cleanup_expired() removes any non-running session after 10min idle (no client ping)
"""

import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ActiveSession:
    """Running session that clients can reconnect to."""
    session_id: str
    io: object                 # WebSocketIO with queues
    thread: threading.Thread   # Agent execution thread
    created: float
    last_ping: float
    status: str                # 'running' | 'suspended' | 'completed'


class ActiveSessionRegistry:
    """Thread-safe registry: session_id → ActiveSession."""

    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}
        self._lock = threading.Lock()

    def register(self, session_id: str, io, thread) -> None:
        """Register a running session."""
        with self._lock:
            self._sessions[session_id] = ActiveSession(
                session_id=session_id,
                io=io,
                thread=thread,
                created=time.time(),
                last_ping=time.time(),
                status='running',
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
        """Mark as suspended (client disconnected, agent still running)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = 'suspended'

    def mark_completed(self, session_id: str) -> None:
        """Mark as completed (agent finished)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = 'completed'

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        to_remove = []

        with self._lock:
            for sid, sess in self._sessions.items():
                idle = now - sess.last_ping

                # Any non-running session: clean up after 10min idle
                if sess.status != 'running' and idle > 600:
                    to_remove.append(sid)

            for sid in to_remove:
                del self._sessions[sid]

        return len(to_remove)

    def list_active(self) -> list[str]:
        """List session IDs with status 'running' or 'suspended'."""
        with self._lock:
            return [sid for sid, sess in self._sessions.items()
                    if sess.status in ('running', 'suspended')]

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
