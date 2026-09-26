"""Session-owned task and recurring watches for a long-lived Host."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from ..watch import _database, _insert_event

logger = logging.getLogger(__name__)


class WatchStore:
    """Session registration and source state in the Host event database."""

    def __init__(self, co_dir: Path):
        self.co_dir = Path(co_dir)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    owner TEXT NOT NULL, host_pid INTEGER NOT NULL, status TEXT NOT NULL,
                    result TEXT, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watches (
                    watch_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    owner TEXT NOT NULL, kind TEXT NOT NULL,
                    config TEXT NOT NULL, cursor TEXT,
                    next_at REAL, expires_at REAL NOT NULL,
                    status TEXT NOT NULL, last_checked REAL
                );
            """)

    def _connect(self):
        return _database(self.co_dir)

    def register_task(self, task_id: str, session_id: str, owner: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?, 'running', NULL, ?)",
                (task_id, session_id, owner, os.getpid(), time.time()),
            )

    def finish_task(self, task_id: str, status: str, result: str) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid task status")
        with self._connect() as db:
            db.execute(
                "UPDATE tasks SET status=?, result=?, updated=? WHERE task_id=?",
                (status, result[-8000:], time.time(), task_id),
            )
            self._observe_finished_tasks(db)

    def watch_task(self, session_id: str, owner: str, task_id: str) -> dict:
        now = time.time()
        watch_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            task = db.execute(
                "SELECT * FROM tasks WHERE task_id=? AND session_id=? AND owner=?",
                (task_id, session_id, owner),
            ).fetchone()
            if task is None:
                raise ValueError("Task not found in this session")
            self._check_limit(db, session_id)
            db.execute(
                "INSERT INTO watches VALUES (?, ?, ?, 'task', ?, NULL, NULL, ?, 'active', NULL)",
                (watch_id, session_id, owner, json.dumps({"task_id": task_id}), now + 7 * 86400),
            )
            self._observe_finished_tasks(db)
        return {"watch_id": watch_id, "kind": "task", "task_id": task_id}

    def watch_every(self, session_id: str, owner: str, *, minutes: int,
                    probe: str, query: str = "", lifetime_hours: int = 24,
                    initial_ids: list[str] | None = None) -> dict:
        if not isinstance(minutes, int) or not 1 <= minutes <= 1440:
            raise ValueError("minutes must be between 1 and 1440")
        if not isinstance(lifetime_hours, int) or not 1 <= lifetime_hours <= 168:
            raise ValueError("lifetime_hours must be between 1 and 168")
        if probe != "gmail_search":
            raise ValueError("The available recurring probe is gmail_search")
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("query must be at most 200 characters")
        now = time.time()
        watch_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_limit(db, session_id)
            db.execute(
                "INSERT INTO watches VALUES (?, ?, ?, 'interval', ?, ?, ?, ?, 'active', NULL)",
                (watch_id, session_id, owner,
                 json.dumps({"probe": probe, "query": query, "seconds": minutes * 60}),
                 json.dumps(initial_ids or []), now + minutes * 60,
                 now + lifetime_hours * 3600),
            )
        return {"watch_id": watch_id, "kind": "interval", "probe": probe,
                "every_minutes": minutes, "expires_at": now + lifetime_hours * 3600}

    @staticmethod
    def _check_limit(db, session_id: str) -> None:
        count = db.execute(
            "SELECT COUNT(*) FROM watches WHERE session_id=? AND status='active'",
            (session_id,),
        ).fetchone()[0]
        if count >= 10:
            raise ValueError("This session already has 10 active watches")

    def list_watches(self, session_id: str, owner: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT watch_id, kind, config, next_at, expires_at, status, last_checked "
                "FROM watches WHERE session_id=? AND owner=? ORDER BY rowid",
                (session_id, owner),
            ).fetchall()
            result = []
            for row in rows:
                name = f"session-watch:{row['watch_id']}"
                pending = db.execute(
                    "SELECT COUNT(*) FROM events WHERE name=? AND status IN ('pending', 'running')",
                    (name,),
                ).fetchone()[0]
                result.append({**dict(row), "config": json.loads(row["config"]),
                               "pending_events": pending})
        return result

    def cancel(self, session_id: str, owner: str, watch_id: str) -> dict:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE watches SET status='cancelled' WHERE watch_id=? AND session_id=? "
                "AND owner=? AND status IN ('active', 'completed', 'paused')",
                (watch_id, session_id, owner),
            )
            if result.rowcount != 1:
                raise ValueError("Watch not found in this session")
            db.execute(
                "UPDATE events SET status='cancelled' WHERE name=? AND status='pending'",
                (f"session-watch:{watch_id}",),
            )
        return {"watch_id": watch_id, "status": "cancelled"}

    def _observe_finished_tasks(self, db) -> None:
        rows = db.execute("""
            SELECT w.watch_id, w.session_id, w.owner, t.task_id, t.status, t.result
            FROM watches w JOIN tasks t ON json_extract(w.config, '$.task_id')=t.task_id
            WHERE w.kind='task' AND w.status='active' AND w.expires_at>?
              AND t.status!='running'
        """, (time.time(),)).fetchall()
        for row in rows:
            payload = {"kind": "task_completed", "task_id": row["task_id"],
                       "status": row["status"], "result": row["result"]}
            self._emit_watch_event(db, row, payload)
            db.execute("UPDATE watches SET status='completed' WHERE watch_id=?",
                       (row["watch_id"],))

    def _emit_watch_event(self, db, watch, payload: dict) -> None:
        payload["summary"] = (
            "Background task " + payload.get("status", "finished")
            if payload["kind"] == "task_completed"
            else "Watch observed new data" if payload["kind"] == "probe_changed"
            else "Watch check needs attention"
        )
        _insert_event(
            db, f"session-watch:{watch['watch_id']}", payload["kind"], payload,
            uuid.uuid4().hex, time.time(), watch["session_id"], watch["owner"],
        )

    def due(self, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE watches SET status='expired' WHERE status='active' AND expires_at<=?", (now,))
            self._observe_finished_tasks(db)
            rows = db.execute(
                "SELECT * FROM watches WHERE kind='interval' AND status='active' "
                "AND next_at<=? ORDER BY next_at LIMIT 20", (now,),
            ).fetchall()
            # Claim each tick before network I/O; a stale claim is retried after 5 minutes.
            for row in rows:
                db.execute("UPDATE watches SET next_at=? WHERE watch_id=?",
                           (now + 300, row["watch_id"]))
        return [dict(row) for row in rows]

    def checked(self, watch: dict, *, seen_ids: list[str], new_items: list[dict],
                now: float | None = None) -> None:
        now = time.time() if now is None else now
        config = json.loads(watch["config"])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status FROM watches WHERE watch_id=?",
                                 (watch["watch_id"],)).fetchone()
            if current is None or current["status"] != "active":
                return
            if new_items:
                self._emit_watch_event(db, watch, {
                    "kind": "probe_changed", "probe": config["probe"],
                    "query": config["query"], "items": new_items[:20],
                    "more": len(new_items) > 20,
                })
            db.execute(
                "UPDATE watches SET cursor=?, last_checked=?, next_at=? WHERE watch_id=?",
                (json.dumps(seen_ids[:100]), now, now + config["seconds"], watch["watch_id"]),
            )

    def latest_expiry(self, session_id: str) -> float | None:
        with self._connect() as db:
            value = db.execute(
                "SELECT MAX(expires_at) FROM watches WHERE session_id=? "
                "AND status IN ('active', 'completed', 'paused')",
                (session_id,),
            ).fetchone()[0]
        return value

    def recover_tasks(self) -> None:
        """A prior Host process cannot truthfully report its task's exit code."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            tasks = db.execute("SELECT task_id, host_pid FROM tasks WHERE status='running'").fetchall()
            for task in tasks:
                try:
                    os.kill(task["host_pid"], 0)
                except ProcessLookupError:
                    db.execute(
                        "UPDATE tasks SET status='unknown', "
                        "result='Host exited before task outcome was recorded' "
                        "WHERE task_id=?", (task["task_id"],),
                    )
                except PermissionError:
                    continue  # The PID exists but belongs to another account.
            self._observe_finished_tasks(db)

    def failed_check(self, watch: dict, reason: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT status FROM watches WHERE watch_id=?",
                                 (watch["watch_id"],)).fetchone()
            if current is None or current["status"] != "active":
                return
            self._emit_watch_event(db, watch, {
                "kind": "watch_error", "reason": reason[:500],
            })
            db.execute("UPDATE watches SET status='paused' WHERE watch_id=?",
                       (watch["watch_id"],))


def gmail_probe(query: str) -> list[dict]:
    """Read a bounded set of Gmail search matches without changing the mailbox."""
    from ....useful_tools.gmail import Gmail

    mail = Gmail()
    items = mail.list_search(query, max_results=100)
    if len(items) >= 100:
        raise ValueError("Gmail search has 100 or more matches; narrow the watch query")
    return [
        {key: str(item.get(key, ""))[:500]
         for key in ("id", "from", "subject", "date", "snippet")}
        for item in items
    ]


def check_due_watches(store: WatchStore) -> None:
    for watch in store.due():
        config = json.loads(watch["config"])
        try:
            items = gmail_probe(config["query"])
        except Exception as exc:
            logger.exception("Watch probe failed for %s", watch["watch_id"])
            store.failed_check(watch, str(exc))
            continue
        seen = set(json.loads(watch["cursor"] or "[]"))
        new_items = [item for item in items if item["id"] not in seen]
        store.checked(watch, seen_ids=[item["id"] for item in items],
                      new_items=new_items)
