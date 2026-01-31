"""Session management with SQLite persistence."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_db_path() -> Path:
    db_dir = Path.home() / ".co-ai"
    db_dir.mkdir(exist_ok=True)
    return db_dir / "sessions.db"


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            model TEXT,
            created_at TEXT,
            updated_at TEXT,
            messages TEXT
        )
    """)
    conn.commit()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


class SessionManager:
    def __init__(self):
        self.conn = get_connection()
        self.current_id: Optional[str] = None
    
    def create_session(self, model: str = "") -> str:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO sessions (id, title, model, created_at, updated_at, messages) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, "New Session", model, now, now, "[]")
        )
        self.conn.commit()
        self.current_id = session_id
        return session_id
    
    def save_message(self, role: str, content: str) -> None:
        if not self.current_id:
            return
        
        row = self.conn.execute(
            "SELECT messages FROM sessions WHERE id = ?", (self.current_id,)
        ).fetchone()
        
        if row:
            messages = json.loads(row["messages"])
            messages.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
            
            title = content[:50] + "..." if len(content) > 50 else content
            if len(messages) == 1:
                self.conn.execute(
                    "UPDATE sessions SET messages = ?, title = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(messages), title, datetime.now().isoformat(), self.current_id)
                )
            else:
                self.conn.execute(
                    "UPDATE sessions SET messages = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(messages), datetime.now().isoformat(), self.current_id)
                )
            self.conn.commit()
    
    def list_sessions(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, title, model, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    
    def load_session(self, session_id: str) -> Optional[list[dict]]:
        row = self.conn.execute(
            "SELECT messages FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        
        if row:
            self.current_id = session_id
            return json.loads(row["messages"])
        return None
    
    def delete_session(self, session_id: str) -> bool:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()
        if self.current_id == session_id:
            self.current_id = None
        return True


_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
