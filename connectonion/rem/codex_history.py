"""Archive only this notebook's old internal Codex traces through native RPC."""

import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path

from .codex_schedule import codex_home
from .files import state_path, write_json


def internal_threads(root: Path, *, home=None) -> list[dict]:
    """Read metadata only; human chats, pins and recent work are not candidates."""
    database = Path(home or codex_home()) / "state_5.sqlite"
    if not database.is_file():
        return []
    workspace = root.resolve() / ".state" / "tasks"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, cwd FROM threads WHERE archived = 0 AND originator = 'connectonion' "
            "AND is_pinned = 0 AND updated_at < ?", (int(time.time()) - 3600,)).fetchall()
    return [dict(row) for row in rows if Path(row["cwd"]).resolve().is_relative_to(workspace)]


def _still_eligible(row: dict, workspace: Path, home: Path) -> bool:
    with closing(sqlite3.connect((home / "state_5.sqlite").as_uri() + "?mode=ro", uri=True)) as connection:
        fresh = connection.execute(
            "SELECT cwd FROM threads WHERE id = ? AND archived = 0 AND originator = 'connectonion' "
            "AND is_pinned = 0 AND updated_at < ?", (row["id"], int(time.time()) - 3600)).fetchone()
    return bool(fresh and Path(fresh[0]).resolve().is_relative_to(workspace))


def _already_archived(thread_id: str, workspace: Path, home: Path) -> bool:
    with closing(sqlite3.connect((home / "state_5.sqlite").as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT cwd FROM threads WHERE id = ? AND archived = 1 AND originator = 'connectonion'",
            (thread_id,)).fetchone()
    return bool(row and Path(row[0]).resolve().is_relative_to(workspace))


def _archive_thread(client, row: dict, workspace: Path, home: Path) -> tuple[str, str]:
    thread = client.request("thread/read", {"threadId": row["id"], "includeTurns": False}, timeout=60)["thread"]
    if (thread["id"] != row["id"] or thread.get("isPinned")
            or thread["status"]["type"] not in ("notLoaded", "idle")
            or not isinstance(thread.get("updatedAt"), int)
            or thread["updatedAt"] >= int(time.time()) - 3600
            or not Path(thread["cwd"]).resolve().is_relative_to(workspace)
            or not _still_eligible(row, workspace, home)):
        return row["id"], "kept"
    client.request("thread/archive", {"threadId": row["id"]}, timeout=60)
    return row["id"], "archived"


def _archive_batch(pool, client, rows: list[dict], workspace: Path, home: Path, receipt: dict) -> None:
    futures = {pool.submit(_archive_thread, client, row, workspace, home): row["id"] for row in rows}
    failure = None
    for future in as_completed(futures):
        error = future.exception()
        if error is not None:
            thread_id = futures[future]
            if _already_archived(thread_id, workspace, home):
                receipt["archived"].append(thread_id)
                receipt.setdefault("reconciled", []).append(thread_id)
            else:
                receipt["failed"].append({"id": thread_id, "error": type(error).__name__})
                failure = failure or error
        else:
            thread_id, outcome = future.result()
            receipt[outcome].append(thread_id)
    if failure is not None:
        raise failure


def archive_history(root: Path, *, home=None, progress=None) -> dict:
    """Keep resumable traces, remove old maintenance chats from active history."""
    from ..useful_tools.codex import CodexAppServer, _base_command

    home = Path(home or codex_home()).resolve()
    rows = internal_threads(root, home=home)
    receipt = {"requested": [row["id"] for row in rows], "archived": [], "kept": [], "failed": []}
    if not rows:
        return {"archived": 0, "kept": 0}
    client = CodexAppServer(command=_base_command(), cwd=str(root), on_event=lambda event: None,
                            env={**os.environ, "CODEX_HOME": str(home or codex_home())})
    path = state_path(root, "codex-history.json")
    write_json(path, receipt)
    try:
        client.start()
        client.initialize(timeout=60)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for start in range(0, len(rows), 100):
                _archive_batch(pool, client, rows[start:start + 100], root.resolve() / ".state/tasks", home, receipt)
                write_json(path, receipt)
                if progress:
                    progress(min(start + 100, len(rows)), len(rows))
    finally:
        try:
            write_json(path, receipt)
        finally:
            client.close()
    return {key: len(receipt[key]) for key in ("archived", "kept")}
