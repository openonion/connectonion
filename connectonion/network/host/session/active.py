"""
Purpose: In-memory registry preserving running agents across WebSocket reconnections
LLM-Note:
  Dependencies: imports from [time, threading, dataclasses] | imported by [server.py, websocket.py, __init__.py]
  Data flow: websocket.py calls register(session_id, io, thread) → stores ActiveSession(status='running') → agent finishes → mark_session_connected() → cleanup_expired() removes after 10min idle
  State/Effects: in-memory dict with threading.Lock | no persistence | CleanupJob thread runs every 60s, started/stopped by the app lifespan

Lifecycle:
    NEW: register() → status='running'
    AGENT DONE: mark_session_connected() → status='connected' (session alive, ready for next INPUT)
    RECONNECT: get() → returns same session, update_ping() resets idle timer
    EXPIRED: cleanup_expired() removes 'connected' after 10min idle
    NOTE: 'running' sessions are NEVER cleaned up at the 10min mark (agent still working);
          a 1h cap exists only as a stuck-agent safety net.

WebSocket disconnect does NOT change session.status. The IO queues survive
the WS, so a reconnecting client just re-subscribes — no separate
'disconnected' state to track.
"""

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ActiveSession:
    """Session that clients can reconnect to."""
    session_id: str
    io: object                   # WebSocketIO with queues
    thread: threading.Thread     # Agent execution thread
    created: float
    last_ping: float
    status: str                  # 'running' | 'connected'
    owner: object = None         # address that started it; None = nobody (#696)


class ActiveSessionRegistry:
    """Thread-safe registry: session_id → ActiveSession."""

    def __init__(self):
        self._sessions: Dict[str, ActiveSession] = {}
        self._lock = threading.Lock()

    def register(self, session_id: str, io, thread, owner=None) -> None:
        """Register a new execution.

        `owner` is the signature-verified address that started it. Without it,
        a second identity naming this session id attached to the turn in
        progress and had its output streamed to them (#696).
        """
        with self._lock:
            self._sessions[session_id] = ActiveSession(
                session_id=session_id,
                io=io,
                thread=thread,
                created=time.time(),
                last_ping=time.time(),
                status='running',
                owner=owner,
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

    def mark_session_connected(self, session_id: str) -> None:
        """Mark as connected (execution finished, session alive for next INPUT)."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = 'connected'

    def mark_session_running(self, session_id: str, io, thread) -> None:
        """Start a new execution on an existing session."""
        with self._lock:
            if session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.io = io
                sess.thread = thread
                sess.status = 'running'
                sess.last_ping = time.time()

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        to_remove = []

        with self._lock:
            for sid, sess in self._sessions.items():
                idle = now - sess.last_ping
                if sess.status == 'connected' and idle > 600:
                    to_remove.append(sid)
                elif sess.status == 'running' and idle > 3600:
                    to_remove.append(sid)

            for sid in to_remove:
                del self._sessions[sid]

        return len(to_remove)

    def list_active(self) -> list[str]:
        """List session IDs of running sessions."""
        with self._lock:
            return [sid for sid, sess in self._sessions.items()
                    if sess.status == 'running']

    def count(self) -> int:
        """Total sessions in registry."""
        with self._lock:
            return len(self._sessions)


class CleanupJob(threading.Thread):
    """Background thread that expires idle sessions until told to stop.

    It used to be a bare `while True: time.sleep(60)` daemon thread with no
    handle, so every `create_app()` leaked one for the life of the process.
    In the test suite that meant dozens of them by the time a test patched
    `time.sleep` to a no-op — at which point they all spun flat out, starved
    the main thread, and the run died on the 300s timeout (#1246). Waiting on
    an Event instead of sleeping means `stop()` takes effect immediately and
    a patched `time.sleep` cannot turn the wait into a busy loop.
    """

    def __init__(self, registry: ActiveSessionRegistry, interval: float = 60.0):
        super().__init__(daemon=True, name="registry-cleanup")
        self._registry = registry
        self._interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            removed = self._registry.cleanup_expired()
            if removed > 0:
                print(f"[Registry] Cleaned up {removed} expired sessions")

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the loop to exit and wait for it. Safe to call twice."""
        self._stop.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout)


def start_cleanup_job(registry: ActiveSessionRegistry, interval: float = 60.0) -> CleanupJob:
    """Start the background cleanup thread. Call `.stop()` on the result to end it."""
    job = CleanupJob(registry, interval)
    job.start()
    return job
