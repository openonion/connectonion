"""co rem's index of its map and raw material, in one SQLite file beside the pages (#2067, #3453).

The pages are the product and the JSON stays authoritative; `.state/rem.db` is
derived from them (store_build.py, store_messages.py) and can be deleted at any
time. One writer -- `refresh`, under the maintenance lock map and sync already
hold -- and any number of read-only readers through the functions below, which
the CLI, loopback HTTP (`/rem/query`) and OIP (`WIKI_READ`) call directly.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .files import CATEGORIES, Notebook, RemError, state_path
from .store_build import (
    GROUPS,
    PRIVATE,
    SCHEMA,
    SCHEMA_VERSION,
    _privacy_kind,
    build_pages,
    columns,
    facts as parse_facts,
    fingerprints,
    inputs,
    redact_text,
    sync_pages,
    title as parse_title,
)
from .store_messages import body, build_mail, build_runs, build_sessions

BUILDERS = {"pages": build_pages, "mail": build_mail, "sessions": build_sessions, "runs": build_runs}
TABLES = ("people", "orgs", "projects", "records", "messages", "edges", "runs")
UNREADABLE = "The co rem index cannot be read; `co rem sync` builds it again"
PRIVACY_LEVELS = ("all", "cover", "public")


def db_path(root: Path) -> Path:
    return state_path(root, "rem.db")


# ---- the one writer ------------------------------------------------------------------------------------

def _connect(file: Path) -> sqlite3.Connection:
    if not file.exists():
        # Created owner-only before SQLite touches it; SQLite gives -wal and -shm the same mode.
        os.close(os.open(file, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600))  # no O_NOFOLLOW on Windows
    file.chmod(0o600)
    db = sqlite3.connect(file, isolation_level=None, timeout=10)
    db.execute("pragma journal_mode=wal")
    return db


def _remove(file: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(file) + suffix).unlink(missing_ok=True)


def _open_for_build(file: Path):
    """(connection, fresh): an index this code wrote, or a new empty one in its place."""
    db = None
    try:
        db = _connect(file)
        found = db.execute("select value from meta where key = 'schema_version'").fetchone()
        if found and found[0] == SCHEMA_VERSION:
            return db, False
    except sqlite3.DatabaseError:
        pass   # not a database, or no meta table: it holds nothing the files do not
    if db is not None:
        # Closed before the unlink: Windows refuses to delete an open file
        # (WinError 32), and a new notebook's first index was skipped.
        db.close()
    _remove(file)
    db = _connect(file)
    db.executescript(SCHEMA)
    db.execute("insert into meta values ('schema_version', ?)", (SCHEMA_VERSION,))
    return db, True


def _rebuild(db, root: Path, group: str, found: dict, *, known_group: dict | None = None, fresh: bool = False) -> None:
    db.execute("begin immediate")
    try:
        if group == "pages" and known_group is not None:
            sync_pages(db, root, known_group, found, fresh=fresh)
        else:
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
            known_group = {path: value for path, value in known.items() if value[2] == group}
            if fresh or found != known_group:
                _rebuild(db, root, group, found, known_group=known_group, fresh=fresh)
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

JSON_COLUMNS = ("emails", "facts", "public_facts", "tags", "domains", "paths", "recipients")
FLAGS = ("written", "listed", "held", "service")
SORTS = ("activity", "name", "company", "role", "first_contact", "last_contact", "mails", "open_threads")


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
            names = [column[0] for column in cursor.description] if cursor.description else []
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


def _validate_privacy(privacy: str) -> str:
    if privacy not in PRIVACY_LEVELS:
        raise RemError(f"Privacy must be one of: {', '.join(PRIVACY_LEVELS)}")
    return privacy


def _shape_record_item(row: dict, level: str) -> dict:
    item = dict(row)
    pub_title = item.pop("public_title", "")
    pub_summary = item.pop("public_summary", "")
    pub_facts = item.pop("public_facts", {})
    if level == "public":
        item["title"] = pub_title
        item["summary"] = pub_summary
        item["facts"] = pub_facts
    return item


def query_records(
    root: Path,
    *,
    category: str = "",
    query: str = "",
    tag: str = "",
    privacy: str = "cover",
    include_unlisted: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """Paginated record metadata across any category from SQLite (`records` table).

    Read-only: never creates or writes `.state/rem.db`.
    """
    level = _validate_privacy(privacy)
    if category and category not in CATEGORIES:
        raise RemError(f"Unknown category {category!r}; choose from {', '.join(CATEGORIES)}")
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    if not db_path(root).is_file():
        return {"total": 0, "items": [], "limit": limit, "offset": offset}

    where: list[str] = []
    params: list = []
    if not include_unlisted:
        where.append("listed = 1")
    if level == "public":
        where.append("privacy != 'private_page'")
    if category:
        where.append("category = ?")
        params.append(category)
    if tag:
        from .tags import normalise
        slug = normalise(tag)
        if slug:
            where.append("exists (select 1 from json_each(records.tags) where value = ?)")
            params.append(slug)
    if query:
        if level == "public":
            where.append("(public_title like ? or public_summary like ? or record like ? or public_facts like ?)")
        else:
            where.append("(title like ? or summary like ? or record like ? or facts like ?)")
        params.extend([f"%{query}%"] * 4)

    where_sql = f"where {' and '.join(where)}" if where else ""
    count_rows = _rows(root, f"select count(*) as total from records {where_sql}", params)
    total = int(count_rows[0]["total"]) if count_rows else 0
    rows = _rows(
        root,
        f"select * from records {where_sql} order by updated_at desc, title, record limit ? offset ?",
        [*params, limit, offset],
    )
    return {"total": total, "items": [_shape_record_item(row, level) for row in rows], "limit": limit, "offset": offset}


def get_record(root: Path, record: str, *, privacy: str = "cover") -> dict | None:
    """Read one Markdown record with server-side privacy redaction and store metadata."""
    level = _validate_privacy(privacy)
    book = Notebook(root)
    try:
        raw_text = book.read(record)
    except RemError:
        return None
    if level == "public" and _privacy_kind(record, raw_text) == "private_page":
        return None
    text = redact_text(raw_text, level)
    from .translate import cached_languages

    translations = {
        lang: redact_text(body_text, level)
        for lang, body_text in cached_languages(root, record).items()
    }
    indexed = _rows(root, "select * from records where record = ?", (record,))
    meta = dict(indexed[0]) if indexed else {}
    return {
        "record": record,
        "category": record.split("/", 1)[0],
        "title": parse_title(text, record),
        "text": text,
        "facts": parse_facts(text),
        "tags": meta.get("tags", []),
        "written": meta.get("written", True),
        "listed": meta.get("listed", True),
        "updated_at": meta.get("updated_at", ""),
        "translations": translations,
        "edges": edges(root, record),
    }


def _fts_phrase(query: str) -> str:
    tokens = [tok.replace('"', '""') for tok in re.split(r"\s+", query.strip()) if tok]
    return " AND ".join(f'"{tok}"' for tok in tokens)


def search_records(
    root: Path,
    query: str,
    *,
    category: str = "",
    privacy: str = "cover",
    include_unlisted: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Full-text search over `records_fts` with substring fallback for CJK tokens."""
    level = _validate_privacy(privacy)
    needle = query.strip()
    if not needle or not db_path(root).is_file():
        return []
    limit = max(1, min(int(limit), 200))
    fts_expr = _fts_phrase(needle)
    hits: list[dict] = []
    seen: set[str] = set()
    if fts_expr:
        where = ["records_fts match ?"]
        params: list = [fts_expr]
        if not include_unlisted:
            where.append("r.listed = 1")
        if category:
            where.append("r.category = ?")
            params.append(category)
        if level == "public":
            where.append("r.privacy != 'private_page'")
        rows = _rows(
            root,
            "select r.* from records_fts f join records r on r.rowid = f.rowid "
            f"where {' and '.join(where)} order by bm25(records_fts) limit ?",
            [*params, limit],
        )
        for row in rows:
            seen.add(row["record"])
            hits.append(_shape_record_item(row, level))
    if len(hits) < limit:
        fallback = query_records(
            root,
            category=category,
            query=needle,
            privacy=level,
            include_unlisted=include_unlisted,
            limit=limit,
        )["items"]
        for row in fallback:
            if row["record"] not in seen:
                seen.add(row["record"])
                hits.append(row)
                if len(hits) >= limit:
                    break
    return hits


def people_table(root: Path, *, company: str = "", query: str = "", open_only: bool = False,
                 recent_days: int = 0, sort: str = "activity", descending: bool = True,
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
        from .service import notebook_today
        since = (date.fromisoformat(today) if today else notebook_today(root)) - timedelta(days=recent_days)
        where.append("last_contact >= ?")
        parameters.append(since.isoformat())
    column = "last_contact" if sort == "activity" else sort
    order = f"({column} is null or {column} = ''), {column} {'desc' if descending else 'asc'}, name, record"
    rows = _rows(root, f"select * from people {'where ' + ' and '.join(where) if where else ''} order by {order}",
                 parameters)
    from .relationship_stats import relationship_stats
    stats = relationship_stats(root, rows, today=today)
    for row in rows:
        if row["record"] in stats:
            row["relationship"] = stats[row["record"]]
    if sort == "activity" and stats:
        rows.sort(key=lambda row: row.get("relationship", {}).get("last_mail", ""), reverse=descending)
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
    if not found:
        return None
    from .relationship_stats import relationship_stats
    stats = relationship_stats(root, found)
    return {**found[0], "edges": edges(root, record),
            **({"relationship": stats[record]} if record in stats else {})}


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


def dispatch_query(root: Path, params: dict, *, max_privacy: str = "all") -> dict:
    """Unified query dispatcher shared by loopback HTTP (`/rem/query`) and remote OIP (`WIKI_READ`)."""
    op = str(params.get("op") or "records")
    requested = str(params.get("privacy") or ("public" if max_privacy == "public" else "cover"))
    rank = {"public": 0, "cover": 1, "all": 2}
    if requested not in rank:
        raise RemError(f"Privacy must be one of: {', '.join(PRIVACY_LEVELS)}")
    effective = requested if rank[requested] <= rank[max_privacy] else max_privacy
    include_unlisted = str(params.get("include_unlisted") or "").lower() in ("1", "true", "yes")

    if op == "records":
        return query_records(
            root,
            category=str(params.get("category") or ""),
            query=str(params.get("query") or ""),
            tag=str(params.get("tag") or ""),
            privacy=effective,
            include_unlisted=include_unlisted,
            limit=int(params.get("limit") or 200),
            offset=int(params.get("offset") or 0),
        )
    if op == "record":
        target = str(params.get("record") or "")
        if not target:
            raise RemError("`record` parameter is required for op='record'")
        found = get_record(root, target, privacy=effective)
        if found is None:
            raise RemError(f"Record not found: {target}")
        return found
    if op == "search":
        return {"items": search_records(
            root,
            str(params.get("query") or ""),
            category=str(params.get("category") or ""),
            privacy=effective,
            include_unlisted=include_unlisted,
            limit=int(params.get("limit") or 50),
        )}
    if op == "people":
        rows = people_table(
            root,
            company=str(params.get("company") or ""),
            query=str(params.get("query") or ""),
            open_only=str(params.get("open_only") or "").lower() in ("1", "true", "yes"),
            recent_days=int(params.get("recent_days") or 0),
            sort=str(params.get("sort") or "activity"),
            descending=str(params.get("descending") or "1").lower() not in ("0", "false", "no"),
            include_unlisted=include_unlisted,
        )
        if effective == "public" and rows:
            pub_meta = {
                r["record"]: r
                for r in _rows(root, "select record, privacy, public_title, public_facts from records where category = 'people'")
            }
            public_rows = []
            for row in rows:
                meta = pub_meta.get(row["record"])
                if meta and meta["privacy"] == "private_page":
                    continue
                pub_facts = meta["public_facts"] if meta else {}
                derived = columns(pub_facts)
                cleaned = {
                    **row,
                    **derived,
                    "name": meta["public_title"] if meta else " ".join(PRIVATE.sub("", row["name"]).split()),
                    "facts": pub_facts,
                }
                public_rows.append(cleaned)
            rows = public_rows
        return {"items": rows, "total": len(rows)}
    raise RemError(f"Unknown query op {op!r}; choose from records, record, search, people")
