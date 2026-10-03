"""co rem's index of its map and raw material, in one SQLite file beside the pages (#2067).

The pages are the product and the JSON stays authoritative; `.state/rem.db` is
derived from them (store_build.py, store_messages.py) and can be deleted at any
time. One writer -- `refresh`, under the maintenance lock map and sync already
hold -- and any number of read-only readers through the functions below, which
are what the reader's People table (#2064), the chat view (#2066) and the fact
cards (#2068) call instead of SQL. docs/cli/rem-store.md has the schema.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .files import RemError, state_path
from .store_build import GROUPS, SCHEMA, SCHEMA_VERSION, build_pages, columns, fingerprints, inputs
from .store_messages import body, build_mail, build_runs, build_sessions

BUILDERS = {"pages": build_pages, "mail": build_mail, "sessions": build_sessions, "runs": build_runs}
TABLES = ("people", "orgs", "projects", "messages", "edges", "runs")
UNREADABLE = "The co rem index cannot be read; `co rem sync` builds it again"


def db_path(root: Path) -> Path:
    return state_path(root, "rem.db")


# ---- the one writer ------------------------------------------------------------------------------------

def _connect(file: Path) -> sqlite3.Connection:
    if not file.exists():
        # Created owner-only before SQLite touches it; SQLite gives -wal and -shm the same mode.
        os.close(os.open(file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600))
    file.chmod(0o600)
    db = sqlite3.connect(file, isolation_level=None, timeout=10)
    db.execute("pragma journal_mode=wal")
    return db


def _remove(file: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(file) + suffix).unlink(missing_ok=True)


def _open_for_build(file: Path):
    """(connection, fresh): an index this code wrote, or a new empty one in its place."""
    try:
        db = _connect(file)
        found = db.execute("select value from meta where key = 'schema_version'").fetchone()
        if found and found[0] == SCHEMA_VERSION:
            return db, False
        db.close()
    except sqlite3.DatabaseError:
        pass   # not a database, or no meta table: it holds nothing the files do not
    _remove(file)
    db = _connect(file)
    db.executescript(SCHEMA)
    db.execute("insert into meta values ('schema_version', ?)", (SCHEMA_VERSION,))
    return db, True


def _rebuild(db, root: Path, group: str, found: dict) -> None:
    db.execute("begin immediate")
    try:
        BUILDERS[group](db, root)
        db.execute("delete from sources where grp = ?", (group,))
        db.executemany("insert into sources values (?, ?, ?, ?)", [(path, *value) for path, value in found.items()])
        db.execute("commit")
    except BaseException:
        db.execute("rollback")
        raise


def refresh(root: Path) -> dict:
    """Bring the index up to date with the files; only groups whose inputs changed are rebuilt.

    Call it holding the maintenance lock. Returns what was rebuilt, the rows
    per table and how long it took.
    """
    started, file = time.monotonic(), db_path(root)
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db, fresh = _open_for_build(file)
    try:
        known = {} if fresh else {path: (mtime, size, group) for path, mtime, size, group
                                  in db.execute("select path, mtime_ns, size, grp from sources")}
        rebuilt = []
        for group, paths in inputs(root).items():
            found = fingerprints(root, group, paths)
            if fresh or found != {path: value for path, value in known.items() if value[2] == group}:
                _rebuild(db, root, group, found)
                rebuilt.append(group)
        if rebuilt:
            db.execute("insert or replace into meta values ('built_at', ?)",
                       (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        rows = {table: db.execute(f"select count(*) from {table}").fetchone()[0] for table in TABLES}
    finally:
        db.close()
    return {"rebuilt": [group for group in GROUPS if group in rebuilt], "rows": rows,
            "seconds": round(time.monotonic() - started, 3)}


def refresh_safely(root: Path) -> dict:
    """`refresh`, after a map or a sync: an index that cannot be built is reported, not fatal."""
    try:
        return refresh(root)
    except (sqlite3.Error, OSError, RemError, ValueError, KeyError) as error:
        reason = f"{type(error).__name__}: {error}"
        print(f"co rem: store skipped: {reason}", file=sys.stderr)
        return {"skipped": reason}


# ---- readers -------------------------------------------------------------------------------------------

JSON_COLUMNS = ("emails", "facts", "domains", "paths", "recipients")
FLAGS = ("written", "listed", "held", "service")
SORTS = ("name", "company", "role", "first_contact", "last_contact", "mails", "open_threads")


def _rows(root: Path, sql: str, parameters=()) -> list:
    """Read-only rows as dicts, JSON decoded; [] when no index has been built yet."""
    file = db_path(root)
    if not file.is_file():
        return []
    try:
        db = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
        try:
            version = db.execute("select value from meta where key = 'schema_version'").fetchone()
            if not version or version[0] != SCHEMA_VERSION:
                raise RemError(UNREADABLE)
            cursor = db.execute(sql, parameters)
            names = [column[0] for column in cursor.description]
            found = [dict(zip(names, values)) for values in cursor.fetchall()]
        finally:
            db.close()
    except sqlite3.DatabaseError as error:
        raise RemError(UNREADABLE) from error
    for row in found:
        for column in JSON_COLUMNS:
            if isinstance(row.get(column), str):
                row[column] = json.loads(row[column])
        if "first_contact" in row and isinstance(row.get("facts"), dict):
            # Older indexes filled this from the earliest mapped mail. A page's
            # explicit fact is the only source for an actual first contact.
            row["first_contact"] = columns(row["facts"])["first_contact"]
        for column in FLAGS:
            if column in row:
                row[column] = bool(row[column])
    return found


def people_table(root: Path, *, company: str = "", query: str = "", open_only: bool = False,
                 recent_days: int = 0, sort: str = "last_contact", descending: bool = True,
                 include_unlisted: bool = False, today: str | None = None) -> list[dict]:
    """One row per person, the CRM columns (#2064). Listed people only, as the census counts them."""
    if sort not in SORTS:
        raise RemError(f"Sort by one of: {', '.join(SORTS)}")
    where, parameters = [] if include_unlisted else ["listed"], []
    if company:
        where.append("company like ?")
        parameters.append(f"%{company}%")
    if query:
        where.append("(name like ? or emails like ? or company like ? or role like ? or record like ?)")
        parameters += [f"%{query}%"] * 5
    if open_only:
        where.append("open_threads > 0")
    if recent_days:
        since = date.fromisoformat(today or date.today().isoformat()) - timedelta(days=recent_days)
        where.append("last_contact >= ?")
        parameters.append(since.isoformat())
    order = f"({sort} is null or {sort} = ''), {sort} {'desc' if descending else 'asc'}, name, record"
    rows = _rows(root, f"select * from people {'where ' + ' and '.join(where) if where else ''} order by {order}",
                 parameters)
    if sort == "first_contact":
        rows.sort(key=lambda row: (not row["first_contact"],
                                   (-1 if descending else 1) * int((row["first_contact"] or "0").replace("-", "")),
                                   row["name"], row["record"]))
    return rows


def edges(root: Path, record: str) -> list[dict]:
    """Every edge touching a person, an organisation or a project, strongest first."""
    return _rows(root, "select * from edges where person = ? or other = ? order by kind, count desc, other, person",
                 (record, record))


def person(root: Path, record: str) -> dict | None:
    found = _rows(root, "select * from people where record = ?", (record,))
    return {**found[0], "edges": edges(root, record)} if found else None


def thread(root: Path, thread_id: str, *, bodies: bool = False) -> list[dict]:
    """A conversation's messages in time order; with `bodies`, each one's text read from its file."""
    messages = _rows(root, "select * from messages where thread = ? order by time, id", (thread_id,))
    for message in messages if bodies else ():
        message["body"] = body(root, message)
    return messages


def threads(root: Path, record: str) -> list[dict]:
    """The conversations a person is in (by address) or a project's sessions, newest first."""
    found = person(root, record)
    if found:
        clauses = " or ".join(["sender = ? or recipients like ?"] * len(found["emails"])) or "0"
        parameters = [value for address in found["emails"] for value in (address, f'%"{address}"%')]
    else:
        clauses, parameters = "thread like 'session:%' and subject = ?", [record]
    return _rows(root, "select thread, min(subject) as subject, count(*) as messages, min(time) as first, "
                       f"max(time) as last from messages where {clauses} group by thread order by last desc",
                 parameters)
