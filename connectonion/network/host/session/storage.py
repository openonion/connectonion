"""
Purpose: Persistent session storage for hosted agent requests with TTL expiry
LLM-Note:
  Dependencies: imports from [pydantic, pathlib, json, time] | imported by [routes.py, server.py, __init__.py] | tested by [tests/network/test_session_storage.py]
  Data flow: save(session) appends to JSONL → get(session_id) reads backwards, returns latest if not expired → list() loads all, filters expired
  State/Effects: writes to .co/session_results.jsonl (append-only) | creates .co/ directory if missing
  Integration: exposes Session (Pydantic model), SessionStorage class with save/get/list | used by routes.py input_handler, websocket.py
  Performance: append-only writes O(1) | linear scan on read O(n) - acceptable for thousands of sessions
  Errors: returns None if session not found or expired | creates parent directory if missing
"""

import json
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Session(BaseModel):
    """Session record for agent requests."""
    session_id: str
    status: str
    prompt: str
    result: Optional[str] = None
    session: Optional[dict] = None  # Full context: messages, trace, iteration, updated
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
        valid = [s for s in sessions.values()
                 if s.status == "running" or not s.expires or s.expires > now]
        return sorted(valid, key=lambda s: s.created or 0, reverse=True)

    def checkpoint(self, session: dict) -> None:
        """Save session checkpoint before blocking operation (approval, ask_user)."""
        session_id = session.get('session_id')
        if not session_id:
            return
        record = Session(
            session_id=session_id,
            status="waiting_approval",
            prompt="",
            session=session,
            created=time.time(),
            expires=time.time() + 86400,
        )
        self.save(record)
