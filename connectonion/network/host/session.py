"""
Purpose: Persistent session storage for hosted agent requests with TTL expiry
LLM-Note:
  Dependencies: imports from [pydantic.BaseModel, pathlib, json, time] | imported by [network/host/routes.py, network/host/server.py] | tested by [tests/network/test_session_storage.py]
  Data flow: save(session) appends Session to JSONL file (.co/session_results.jsonl) → get(session_id) reads file backwards → returns latest matching session if not expired → list() loads all sessions → filters expired ones → sorts by created desc
  State/Effects: writes to .co/session_results.jsonl (append-only) | creates .co/ directory | auto-expires sessions based on expires timestamp | last entry wins (duplicates overridden by latest)
  Integration: exposes Session(session_id, status, prompt, result, created, expires, duration_ms) Pydantic model | SessionStorage(path) with .save(session), .get(session_id) → Session|None, .list() → list[Session] | used by routes to persist and retrieve agent execution results
  Performance: append-only writes (fast) | linear scan on read (acceptable for thousands of sessions) | file-based (simple, no DB required) | TTL filtering prevents unbounded growth
  Errors: returns None if session not found or expired | creates parent directory if missing | no exceptions raised
Session storage for hosted agents.
"""

import json
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Session(BaseModel):
    """Session record for tracking agent requests.

    Uses Pydantic BaseModel for:
    - Native JSON serialization via .model_dump()
    - Type validation
    - API response compatibility
    """
    session_id: str
    status: str
    prompt: str
    result: Optional[str] = None
    created: Optional[float] = None
    expires: Optional[float] = None
    duration_ms: Optional[int] = None


class SessionStorage:
    """JSONL file storage. Append-only, last entry wins."""

    def __init__(self, path: str = ".co/session_results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)

    def save(self, session: Session):
        with open(self.path, "a") as f:
            f.write(session.model_dump_json() + "\n")

    def get(self, session_id: str) -> Session | None:
        if not self.path.exists():
            return None
        now = time.time()
        with open(self.path) as f:
            lines = f.readlines()
        for line in reversed(lines):
            data = json.loads(line)
            if data["session_id"] == session_id:
                session = Session(**data)
                # Return if running or not expired
                if session.status == "running" or not session.expires or session.expires > now:
                    return session
                return None  # Expired
        return None

    def list(self) -> list[Session]:
        if not self.path.exists():
            return []
        sessions = {}
        now = time.time()
        with open(self.path) as f:
            for line in f:
                data = json.loads(line)
                sessions[data["session_id"]] = Session(**data)
        # Filter out expired non-running sessions
        valid = [s for s in sessions.values()
                 if s.status == "running" or not s.expires or s.expires > now]
        # Sort by created desc (newest first)
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)
