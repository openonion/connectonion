"""What the user told their coding agents, filed by project page. No model.

A project page is best written from the user's own words to Codex and Claude
Code in that project's folders: what they asked for, decided, saw fail and saw
pass. This reads only those words -- the same parser `sync` uses, so the
assistant, tool output and injected harness blocks never arrive -- and keeps
them per page under `.state/projects/<page>/`, private like the rest of `.state/`.

It is built for a daily round that reads only what is new: an extraction after
the first reads only session files changed since the last one, and a page
remembers the newest message it was written from (`written_through`), so an
update is handed only the messages after it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import SECRET_SHAPES, Notebook, WikiError, atomic_write, read_json, state_path, write_json
from .investigate import project_paths
from .scan import project_exclusion
from .source import KINDS, SKIPPED, UNFAMILIAR, timestamp

# The widest window a coding source may read (service.MAX_LOOKBACK_DAYS).
LOOKBACK_DAYS = 180
# A line still being written at the last extraction carries a time before it;
# re-reading an hour is free, because a message's id makes it count once.
OVERLAP = timedelta(hours=1)
# Per page, newest kept. The owner's busiest folder held 38.7 KB of typed
# messages over 180 days (2026-09-30); ten times that bounds a very busy year.
MAX_STORED_CHARS = 400_000
REDACTED = "[secret-shaped text removed by co wiki]"


def _folder(root: Path, record: str) -> Path:
    return state_path(root, f"projects/{Path(record).stem}")


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def session_messages(subscriptions: dict, *, since: datetime, wiki_root: Path | None = None) -> tuple[list[dict], dict]:
    """Every message the user typed after `since`, with the folder it was typed in.

    Returns (messages, counts). Counts say what was skipped and why, never what
    was said: excluded folders by reason, harness blocks, unfamiliar shapes.
    """
    messages, counts = [], {"files": 0, "harness": 0, "unfamiliar": 0, "excluded": {}}
    for name, sub in subscriptions.items():
        kind = sub.get("kind")
        if kind not in KINDS or sub.get("enabled") is False:
            continue
        root = Path(sub.get("root", ""))
        if not root.is_dir() or root.is_symlink():
            continue
        parse, read_meta = KINDS[kind]["message"], KINDS[kind]["meta"]
        for path in sorted(root.rglob(KINDS[kind]["glob"])):
            if path.is_symlink() or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < since:
                continue  # messages are appended with their own time: an older file holds none newer
            counts["files"] += 1
            messages += _file_messages(path, kind, parse, read_meta, since, wiki_root, counts)
    return sorted(messages, key=lambda m: (m["timestamp"], m["source"])), counts


def _file_messages(path, kind, parse, read_meta, since, wiki_root, counts) -> list[dict]:
    found = []
    with path.open("rb") as source:
        first = source.readline(1_000_000)
        try:
            meta = read_meta(json.loads(first))
        except (ValueError, UnicodeError, AttributeError, WikiError):
            return []
        if meta.get("skip"):
            return []  # the notebook's own model runs
        offset = len(first)
        for line in source:
            at, offset = offset, offset + len(line)
            if not line.endswith(b"\n") or b"message" not in line or b"role" not in line:
                continue
            try:
                row = json.loads(line)
                item = parse(row, since) if isinstance(row, dict) else None
            except (ValueError, UnicodeError, AttributeError, TypeError, WikiError):
                continue
            if item is SKIPPED or item is UNFAMILIAR:
                counts["unfamiliar" if item is UNFAMILIAR else "harness"] += 1
                continue
            if not item or item.get("role") != "user":
                continue
            cwd = item.get("cwd") or meta.get("cwd") or ""
            why = "no folder recorded" if not cwd else project_exclusion(Path(cwd))
            if not why and wiki_root and Path(cwd).resolve().is_relative_to(wiki_root.resolve()):
                why = "the notebook itself"
            if why:
                counts["excluded"][why] = counts["excluded"].get(why, 0) + 1
                continue
            session = item.get("session") or meta.get("id") or path.stem
            found.append({"source": f"{kind}:{session}:{at}", "tool": kind,
                          # One spelling, so times from both tools compare as text.
                          "timestamp": timestamp(item["timestamp"]).isoformat(),
                          "cwd": cwd, "text": SECRET_SHAPES.sub(REDACTED, item["text"])})
    return found


def page_folders(notebook: Notebook) -> dict[str, str]:
    """Each folder a project page lists under Paths, to that page."""
    folders = {}
    for record in notebook.list("projects"):
        for path in project_paths(notebook.read(record)):
            folders.setdefault(path.rstrip("/") or "/", record)
    return folders


def page_for(cwd: str, folders: dict[str, str]) -> str | None:
    """The page whose listed folder holds `cwd`, the deepest listed folder winning."""
    here = Path(cwd)
    for candidate in (here, *here.parents):
        if str(candidate) in folders:
            return folders[str(candidate)]
    return None


def render(messages: list[dict]) -> str:
    """Plain text to read: one heading per message, its date and tool, its words."""
    blocks = [f"### {m['source']} · {m['timestamp']} — user ({m['tool']}, {m['cwd']})\n\n{m['text'].rstrip()}"
              for m in messages]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def stored(root: Path, record: str) -> list[dict]:
    path = _folder(root, record) / "messages.jsonl"
    if path.is_symlink():
        raise WikiError("Refusing to read linked operational state")
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def page_state(root: Path, record: str) -> dict:
    return read_json(_folder(root, record) / "state.json", {})


def _keep_newest(messages: list[dict], cap: int) -> tuple[list[dict], int]:
    kept, used = [], 0
    for message in reversed(messages):
        used += len(message["text"])
        if used > cap and kept:
            break
        kept.append(message)
    return list(reversed(kept)), len(messages) - len(kept)


def extract(root: Path, subscriptions: dict, *, since: datetime | None = None, full: bool = False,
            days: int = LOOKBACK_DAYS, now: datetime | None = None) -> dict:
    """Refresh every project page's material; return counts, never message text.

    With no `since`, the first extraction reads `days` back and every later one
    reads from the previous extraction (less OVERLAP). `full` reads the whole
    window again. New messages are merged by id, so a re-read adds nothing twice.
    """
    now = now or datetime.now(timezone.utc)
    notebook = Notebook(root)
    base = _private_dir(state_path(root, "projects"))
    index = read_json(base / "index.json", {})
    if since is None:
        previous = index.get("extracted_at")
        since = (timestamp(previous) - OVERLAP) if previous and not full else now - timedelta(days=days)
    messages, counts = session_messages(subscriptions, since=since, wiki_root=root)
    folders = page_folders(notebook)
    by_page, unmapped = {}, {}
    for message in messages:
        record = page_for(message["cwd"], folders)
        if record:
            by_page.setdefault(record, []).append(message)
        else:
            row = unmapped.setdefault(message["cwd"], {"path": message["cwd"], "messages": 0, "last": ""})
            row["messages"] += 1
            row["last"] = max(row["last"], message["timestamp"])
    pages = []
    for record in sorted(set(folders.values())):
        pages.append(_merge(root, record, by_page.get(record, []), full=full, now=now))
    index = {"extracted_at": now.isoformat(), "since": since.isoformat(),
             "unmapped": sorted(unmapped.values(), key=lambda r: r["last"], reverse=True)}
    write_json(base / "index.json", index)
    return {"since": since.isoformat(), "files_read": counts["files"], "messages": len(messages),
            "pages": pages, "unmapped": index["unmapped"], "excluded": counts["excluded"],
            "harness_blocks_skipped": counts["harness"], "unfamiliar_skipped": counts["unfamiliar"]}


def _merge(root: Path, record: str, new: list[dict], *, full: bool, now: datetime) -> dict:
    folder = _private_dir(_folder(root, record))
    state = page_state(root, record)
    old = [] if full else stored(root, record)
    seen = {m["source"] for m in old}
    added = [m for m in new if m["source"] not in seen]
    merged = sorted(old + added, key=lambda m: (m["timestamp"], m["source"]))
    merged, dropped = _keep_newest(merged, MAX_STORED_CHARS)
    if added or full or not (folder / "messages.md").is_file():
        _write_jsonl(folder / "messages.jsonl", merged)
        atomic_write(folder / "messages.md", render(merged))
    state.update({
        "record": record, "messages": len(merged), "chars": sum(len(m["text"]) for m in merged),
        "first": merged[0]["timestamp"] if merged else state.get("first", ""),
        "last_activity": merged[-1]["timestamp"] if merged else state.get("last_activity", ""),
        "tools": sorted({m["tool"] for m in merged}),
        "sessions": len({m["source"].rsplit(":", 1)[0] for m in merged}),
        "dropped_older": state.get("dropped_older", 0) + dropped,
        "extracted_at": now.isoformat()})
    state.setdefault("written_through", "")
    write_json(folder / "state.json", state)
    return {"record": record, "added": len(added), "messages": len(merged),
            "last_activity": state["last_activity"], "written_through": state["written_through"]}


def mark_written(root: Path, record: str, through: str, *, now: datetime | None = None) -> None:
    """The page now reflects every message up to `through`; an update starts after it."""
    folder = _private_dir(_folder(root, record))
    state = page_state(root, record)
    state.update(written_through=through, written_at=(now or datetime.now(timezone.utc)).isoformat())
    write_json(folder / "state.json", state)
