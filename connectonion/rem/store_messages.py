"""The raw material in co rem's index (#2067): mail, typed session messages and runs, by id.

Bodies stay where they are -- one JSON per archived mail, one JSONL per
project -- and a row says where: `body_path`, and `body_line` for a JSONL. The
index is for finding and ordering; reading a body is the thread view's job.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from .files import read_json, state_path
from .store_build import dumps, insert, map_state, thread_key, utc

PREFIX = re.compile(r"^\s*(?:re|fw|fwd|aw|sv|回复|答复|转发)\s*[:：]\s*", re.I)


def has_message_index(file: Path, *, required=frozenset({
    'id', 'thread', 'source', 'time', 'sender', 'subject', 'body_path', 'body_line', 'recipients',
})) -> bool:
    """A legacy notebook can have a database without the archived-message schema."""
    if not file.is_file():
        return False
    with closing(sqlite3.connect(file.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        columns = {row[1] for row in db.execute('pragma table_info(messages)')}
    return required <= columns


def subject_key(subject: str) -> str:
    """A subject without its Re:/Fwd: prefixes, casefolded: what a reply shares with its original."""
    previous, text = None, subject or ""
    while previous != text:
        previous, text = text, PREFIX.sub("", text)
    return " ".join(text.split()).casefold()


def owner_addresses(root: Path) -> set:
    state = map_state(root)
    archive = read_json(state_path(root, "mail/archive.json"), {})
    return {a.casefold() for a in [*(state.get("owner") or {}).get("addresses", []),
                                   *archive.get("owner_addresses", [])]}


def _mail_row(root: Path, row: dict, owner: set) -> dict:
    from .mail import _address, _addresses
    from .mail_archive import message_path, observed_message_path
    provider, message_id = row["source"], row["id"]
    sender, to, cc = _address(row.get("from", "")), _addresses(row.get("to")), _addresses(row.get("cc"))
    # Who the conversation is with: From and To, never the owner, never Cc.
    counterparts = sorted(({sender, *to} - owner) - {""})
    path = message_path(root, provider, message_id)
    if not path.is_file():
        path = observed_message_path(root, provider, message_id)
    # The provider's thread when the inventory recorded it; before that, subject and counterparts.
    thread = (f"mail:{provider}:{row['thread']}" if row.get("thread") else
              "mail:" + thread_key(provider, subject_key(row.get("subject", "")), ",".join(counterparts)))
    return {"id": f"{provider}:{message_id}", "source": provider, "thread": thread,
            "sender": sender, "recipients": dumps(to + cc), "time": utc(row.get("date", "")),
            "subject": row.get("subject", ""), "body_line": None,
            "body_path": path.relative_to(root / ".state").as_posix() if path.is_file() else None}


def build_mail(db, root: Path) -> None:
    from .mail_archive import mail_metadata
    owner = owner_addresses(root)
    db.execute("delete from messages where thread like 'mail:%'")
    insert(db, "messages", [_mail_row(root, row, owner) for row in mail_metadata(root)])


def build_sessions(db, root: Path) -> None:
    """What the owner typed into a coding tool, one thread per session (`kind:session`)."""
    owner = (map_state(root).get("owner") or {}).get("record") or "owner"
    rows = []
    for path in sorted(state_path(root, "projects").glob("*/messages.jsonl")):
        record = read_json(path.parent / "state.json", {}).get("record", "")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            message = json.loads(line) if line.strip() else {}
            if not message.get("source"):
                continue
            rows.append({"id": message["source"], "source": message.get("tool", ""),
                         "thread": "session:" + message["source"].rsplit(":", 1)[0], "sender": owner,
                         "recipients": dumps([message.get("tool", "")]), "time": utc(message.get("timestamp", "")),
                         "subject": record, "body_path": path.relative_to(root / ".state").as_posix(), "body_line": number})
    db.execute("delete from messages where thread like 'session:%'")
    insert(db, "messages", rows)


def build_runs(db, root: Path) -> None:
    rows = []
    for path in sorted(state_path(root, "runs").glob("*.json")):
        run = read_json(path, {})
        usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
        rows.append({"id": run.get("id") or path.stem, "record": run.get("record", ""), "stage": run.get("stage", ""),
                     "outcome": run.get("outcome", ""), "model": run.get("model", ""),
                     "started_at": run.get("started_at", ""), "finished_at": run.get("finished_at", ""),
                     "seconds": run.get("seconds"), "input_tokens": usage.get("input_tokens") or 0,
                     "cached_input_tokens": usage.get("cached_input_tokens") or 0,
                     "output_tokens": usage.get("output_tokens") or 0})
    db.execute("delete from runs")
    insert(db, "runs", rows)


def archived_message(root: Path, row: dict):
    """The saved source record, including its input limits; None if not archived."""
    if not row.get("body_path"):
        return None
    path = state_path(root, row["body_path"])
    if not path.is_file():
        return None
    if row.get("body_line"):
        stat = path.stat()
        lines = _jsonl_lines(path, stat.st_mtime_ns, stat.st_size)
        number = row["body_line"]
        saved = json.loads(lines[number - 1]) if 0 < number <= len(lines) else None
        return saved if saved and saved.get("source") == row.get("id") else None
    saved = read_json(path, {})
    provider = row.get("source")
    if provider in ("gmail", "outlook") and (
            saved.get("provider") != provider or f"{provider}:{saved.get('id')}" != row.get("id")):
        return None
    return saved


@lru_cache(maxsize=8)
def _jsonl_lines(path: Path, mtime_ns: int, size: int) -> tuple[str, ...]:
    """One read per project JSONL while it is unchanged: the reader cites thousands of its lines."""
    return tuple(path.read_text(encoding="utf-8").splitlines())


def body(root: Path, row: dict):
    """The text of one message, read from its file; None when it was never archived."""
    saved = archived_message(root, row)
    return saved.get("text" if row.get("body_line") else "body") if saved else None


# ---- extracted text caches ---------------------------------------------------------------------------

def _cache_inventory(db, root: Path, kind: str) -> tuple[dict, dict]:
    """Reuse directory listings; stat known files to notice in-place edits as well as renames."""
    import stat

    saved = db.execute("select value from meta where key = ?", (f"cache:{kind}",)).fetchone()
    previous = json.loads(saved[0]) if saved else {"directories": {}, "files": {}}
    directories, files = {}, {}
    base = state_path(root, kind)
    pending = [(base, base.lstat())] if base.exists() else []
    while pending:
        path, status = pending.pop()
        if not stat.S_ISDIR(status.st_mode):
            continue
        relative = path.relative_to(base).as_posix()
        old = previous["directories"].get(relative)
        children = old[1] if old and old[0] == status.st_mtime_ns else sorted(p.name for p in path.iterdir())
        directories[relative] = [status.st_mtime_ns, children]
        for name in children:
            child = path / name
            info = child.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append((child, info))
            elif stat.S_ISREG(info.st_mode) and not name.startswith("."):
                files[child.relative_to(base).as_posix()] = [info.st_mtime_ns, info.st_size]
    return previous, {"directories": directories, "files": files}


def _attachment_row(root: Path, relative: str, stamp: list) -> dict | None:
    import mimetypes
    from .attachments import extract_structured_text

    parts = Path(relative).parts
    if len(parts) != 3:
        return None
    provider, message, filename = parts
    path = state_path(root, f"attachments/{relative}")
    return {"source": f"{provider}:{message}:{filename}", "provider": provider, "message_id": message,
            "filename": filename, "rel_path": path.relative_to(root).as_posix(),
            "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "size": stamp[1], "mtime_ns": stamp[0], "extracted_text": extract_structured_text(path, limit=20_000)}


def _translation_row(root: Path, relative: str, stamp: list) -> dict | None:
    from .config import LANGUAGE
    from .translate import cached

    language, _, record = relative.partition("/")
    if not LANGUAGE.fullmatch(language) or not record.endswith(".md") or not (root / record).is_file():
        return None
    text = cached(root, record, language)
    if text is None:
        return None
    return {"record": record, "lang": language, "mtime_ns": stamp[0], "text": text}


def _research_row(root: Path, relative: str, stamp: list) -> dict | None:
    from .store_build import PRIVATE

    if len(Path(relative).parts) != 2 or not relative.endswith(".json"):
        return None
    path = state_path(root, f"research/{relative}")
    item = read_json(path, {})
    if not item.get("source") or not isinstance(item.get("text"), str):
        return None
    return {"source": item["source"], "capture_file": path.relative_to(root).as_posix(),
            "timestamp": item.get("timestamp", ""), "title": item.get("title", ""),
            "mtime_ns": stamp[0], "is_private": int(bool(PRIVATE.search(item["text"]))), "text": item["text"]}


def _delete_cached_file(db, kind: str, relative: str) -> None:
    if kind == "translations":
        language, _, record = relative.partition("/")
        db.execute("delete from translations_cache where record = ? and lang = ?", (record, language))
    elif kind == "attachments":
        db.execute("delete from attachments where rel_path = ?", (f".state/attachments/{relative}",))
    else:
        db.execute("delete from research_cache where capture_file = ?", (f".state/research/{relative}",))


def _translation_pages(root: Path, files: dict) -> dict:
    from .files import CATEGORIES, Notebook
    book, pages = Notebook(root), {}
    for record in {path.partition("/")[2] for path in files}:
        if not record.endswith(".md") or record.split("/", 1)[0] not in CATEGORIES:
            continue
        original = book.path(record)
        info = original.stat() if original.is_file() else None
        pages[record] = [info.st_mtime_ns, info.st_size] if info else None
    return pages


def cache_current(db, root: Path, kind: str) -> bool:
    """Read-only check whether `table` already reflects the files on disk."""
    saved = db.execute("select value from meta where key = ?", (f"cache:{kind}",)).fetchone()
    if not saved:
        return False
    previous, current = _cache_inventory(db, root, kind)
    if kind == "translations":
        current["pages"] = _translation_pages(root, current["files"])
    return current == previous


def _sync_cache(db, root: Path, kind: str, table: str, builder) -> bool:
    previous, current = _cache_inventory(db, root, kind)
    before, found = previous["files"], current["files"]
    changed = {path for path, stamp in found.items() if before.get(path) != stamp}
    if kind == "translations":
        current["pages"] = _translation_pages(root, found)
        changed.update(path for path in found if previous.get("pages", {}).get(path.partition("/")[2])
                       != current["pages"].get(path.partition("/")[2]))
    if current == previous:
        return False
    with db:
        db.execute("begin immediate")
        for relative in (before.keys() - found.keys()) | changed:
            _delete_cached_file(db, kind, relative)
        for relative in sorted(changed):
            row = builder(root, relative, found[relative])
            if row is not None:
                insert(db, table, [row])
        db.execute("insert or replace into meta values (?, ?)", (f"cache:{kind}", dumps(current)))
    return True


def sync_caches(db, root: Path) -> list[str]:
    """Extract only new/changed files; vanished or invalidated originals lose their cache row."""
    caches = (("attachments", "attachments", _attachment_row),
              ("translations", "translations_cache", _translation_row),
              ("research", "research_cache", _research_row))
    return [kind for kind, table, builder in caches if _sync_cache(db, root, kind, table, builder)]
