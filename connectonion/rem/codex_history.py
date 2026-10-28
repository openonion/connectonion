"""Archive only this notebook's old internal Codex traces through native RPC."""

import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path

from .codex_schedule import codex_home
from .files import state_path, write_json

INTERNAL_ORIGIN = """(originator = 'connectonion' OR
    (originator = 'Codex Desktop' AND first_user_message LIKE
     'Follow these instructions exactly. They are the skill `rem-%'))"""


def internal_threads(root: Path, *, home=None) -> list[dict]:
    """Read metadata only; human chats, pins and recent work are not candidates."""
    database = Path(home or codex_home()) / "state_5.sqlite"
    if not database.is_file():
        return []
    workspace = root.resolve() / ".state" / "tasks"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"SELECT id, cwd FROM threads WHERE archived = 0 AND {INTERNAL_ORIGIN} "
            "AND is_pinned = 0 AND updated_at < ?", (int(time.time()) - 3600,)).fetchall()
    return [dict(row) for row in rows if Path(row["cwd"]).resolve().is_relative_to(workspace)]


def _eligible_family(row: dict, workspace: Path, home: Path) -> list[str]:
    with closing(sqlite3.connect((home / "state_5.sqlite").as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        family = connection.execute(
            "WITH RECURSIVE family(id) AS (SELECT ? UNION SELECT child_thread_id "
            "FROM thread_spawn_edges JOIN family ON parent_thread_id = family.id) "
            f"SELECT t.id, cwd, archived, ({INTERNAL_ORIGIN} AND is_pinned = 0 "
            "AND updated_at < ?) AS eligible FROM family LEFT JOIN threads t ON t.id = family.id",
            (row["id"], int(time.time()) - 3600)).fetchall()
    parent = next((item for item in family if item["id"] == row["id"]), None)
    if parent is None or parent["archived"] != 0:
        return []
    # Native archive also archives descendants. An unverified child protects
    # the whole family, even when the selected parent itself is eligible.
    if not all(item["archived"] == 1 or (item["eligible"] and Path(item["cwd"]).resolve().is_relative_to(workspace))
               for item in family):
        return []
    return [item["id"] for item in family if item["archived"] == 0]


def _already_archived(thread_id: str, workspace: Path, home: Path) -> bool:
    with closing(sqlite3.connect((home / "state_5.sqlite").as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            f"SELECT cwd FROM threads WHERE id = ? AND archived = 1 AND {INTERNAL_ORIGIN}",
            (thread_id,)).fetchone()
    return bool(row and Path(row[0]).resolve().is_relative_to(workspace))


def _archive_thread(client, row: dict, workspace: Path, home: Path) -> tuple[str, str]:
    family = _eligible_family(row, workspace, home)
    if not family:
        return row["id"], "kept"
    for thread_id in family:
        thread = client.request("thread/read", {"threadId": thread_id, "includeTurns": False}, timeout=60)["thread"]
        if (thread["id"] != thread_id or thread.get("isPinned")
                or (thread.get("status") or {}).get("type") not in ("notLoaded", "idle")
                or not isinstance(thread.get("updatedAt"), int)
                or thread["updatedAt"] >= int(time.time()) - 3600
                or not Path(thread["cwd"]).resolve().is_relative_to(workspace)):
            return row["id"], "kept"
    if set(_eligible_family(row, workspace, home)) != set(family):
        return row["id"], "kept"
    client.request("thread/archive", {"threadId": row["id"]}, timeout=60)
    return row["id"], "archived"


def _archive_batch(pool, client, rows: list[dict], workspace: Path, home: Path, receipt: dict) -> None:
    futures = {pool.submit(_archive_thread, client, row, workspace, home): row["id"] for row in rows}
    failures = []
    for future in as_completed(futures):
        error = future.exception()
        if error is not None:
            record = {"id": futures[future], "error": type(error).__name__}
            receipt["failed"].append(record)
            failures.append((record, error))
        else:
            thread_id, outcome = future.result()
            receipt[outcome].append(thread_id)
    # Collect every completed outcome before a reconciliation read can fail.
    failure = None
    for record, error in failures:
        if _already_archived(record["id"], workspace, home):
            receipt["failed"].remove(record)
            receipt["archived"].append(record["id"])
            receipt.setdefault("reconciled", []).append(record["id"])
        else:
            failure = failure or error
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
