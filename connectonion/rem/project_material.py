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

A message typed in a multi-repository workspace (the owner's `~/projects`: 590
of 1,359 messages, 43%, on 2026-09-30) is filed under the repository its
session worked in, judged from the paths its tool calls named. A folder with
messages and no page gets the map's page when it was active recently.
"""

from __future__ import annotations

import collections
import json
import os
import re
from bisect import bisect_right
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import (SECRET_SHAPES, Notebook, RemError, atomic_write, maintenance_lock, read_json, state_path,
                    write_json)
from .investigate import project_paths
from .scan import project_exclusion
from .source import KINDS, SKIPPED, UNFAMILIAR, timestamp

# The widest window a coding source may read (service.MAX_LOOKBACK_DAYS).
LOOKBACK_DAYS = 180
# A folder with messages and no page gets one if it was active this recently (#1943).
RECENT_DAYS = 14
# project_exclusion's word for ~/projects: a folder of repositories, not one.
CONTAINER = "multi-repository workspace container"
# A path a tool call names: absolute (or ~/), or the target of `cd`, `git -C`, `workdir`.
_STOP = r"\s'\"`;|&<>(){}\[\],:\\"
ABSOLUTE = re.compile(rf"(?<![\w.~/-])(~?/[^{_STOP}]+)")
MOVED = re.compile(rf"(?:\bcd|\bgit\s+-C|\bworkdir\\?[\"']?\s*[:=])\s*\\?[\"']?([^{_STOP}]+)")
# Claude Code tool inputs that name a path. Never `content`/`new_string`: the
# text an edit writes is not a place the session worked.
CLAUDE_PATH_KEYS = ("file_path", "path", "notebook_path", "command", "cwd", "workdir")
# Lines worth parsing for evidence; every other line is skipped unread.
# (`"function_call_output"` does not contain `_call"`: outputs never count.)
CALL_MARKERS = {"claude-code": (b'"tool_use"',), "codex": (b'_call"', b'"turn_context"')}
# A line still being written at the last extraction carries a time before it;
# re-reading an hour is free, because a message's id makes it count once.
OVERLAP = timedelta(hours=1)
# Per page, newest kept. The owner's busiest folder held 38.7 KB of typed
# messages over 180 days (2026-09-30); ten times that bounds a very busy year.
MAX_STORED_CHARS = 400_000
REDACTED = "[secret-shaped text removed by co rem]"


def _folder(root: Path, record: str) -> Path:
    return state_path(root, f"projects/{Path(record).stem}")


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def session_messages(subscriptions: dict, *, since: datetime, rem_root: Path | None = None,
                     folders: dict | None = None) -> tuple[list[dict], dict]:
    """Every message the user typed after `since`, with the folder it was typed in.

    A message typed in a workspace container carries the project folder its
    session worked in as `cwd`, and the container as `typed_in`; `folders`
    (page_folders) are project folders too. Returns (messages, counts). Counts
    say what was skipped and why, never what was said: excluded folders by
    reason, harness blocks, unfamiliar shapes, messages attributed.
    """
    messages, counts = [], {"files": 0, "harness": 0, "unfamiliar": 0, "excluded": {}, "attributed": 0}
    owner = _Owners(folders or {}, rem_root)
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
            messages += _file_messages(path, kind, parse, read_meta, since, rem_root, counts, owner)
    return sorted(messages, key=lambda m: (m["timestamp"], m["source"])), counts


def _file_messages(path, kind, parse, read_meta, since, rem_root, counts, owner) -> list[dict]:
    found, turns, held = [], [], []
    with path.open("rb") as source:
        first = source.readline(1_000_000)
        try:
            meta = read_meta(json.loads(first))
        except (ValueError, UnicodeError, AttributeError, RemError):
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
                item = parse(row, since, meta) if isinstance(row, dict) else None
            except (ValueError, UnicodeError, AttributeError, TypeError, RemError):
                continue
            if item is SKIPPED or item is UNFAMILIAR:
                counts["unfamiliar" if item is UNFAMILIAR else "harness"] += 1
                continue
            if not item or item.get("role") != "user":
                continue
            turns.append(at)  # every typed message opens a turn, wherever it was typed
            cwd = item.get("cwd") or meta.get("cwd") or ""
            why = "no folder recorded" if not cwd else project_exclusion(Path(cwd))
            if not why and rem_root and Path(cwd).resolve().is_relative_to(rem_root.resolve()):
                why = "the notebook itself"
            session = item.get("session") or meta.get("id") or path.stem
            message = {"source": f"{kind}:{session}:{at}", "tool": kind,
                       # One spelling, so times from both tools compare as text.
                       "timestamp": timestamp(item["timestamp"]).isoformat(),
                       "cwd": cwd, "text": SECRET_SHAPES.sub(REDACTED, item["text"])}
            if why == CONTAINER:
                held.append((at, message))
            elif why:
                counts["excluded"][why] = counts["excluded"].get(why, 0) + 1
            else:
                found.append(message)
    return found + _attributed(path, kind, held, turns, owner, counts)


def _attributed(path, kind, held, turns, owner, counts) -> list[dict]:
    """Messages typed in a workspace, each moved to the project folder its session worked in."""
    if not held:
        return []
    container = held[0][1]["cwd"]
    chosen = _choose(_evidence(path, kind, container, owner), turns)
    found = []
    for at, message in held:
        folder = chosen(at)
        if folder:
            counts["attributed"] += 1
            found.append({**message, "cwd": folder, "typed_in": message["cwd"]})
        else:
            counts["excluded"][CONTAINER] = counts["excluded"].get(CONTAINER, 0) + 1
    return found


def _choose(calls: list[tuple[int, set, bool]], turns: list[int]):
    """The folder a message's own turn touched most, else the session's; the first touched wins a tie."""
    session, per_turn, first = collections.Counter(), collections.defaultdict(collections.Counter), {}
    for at, folders, ahead in calls:
        # A Codex turn_context comes just before the message whose turn it opens.
        turn = bisect_right(turns, at) - 1 + ahead
        for folder in sorted(folders):
            first.setdefault(folder, len(first))
            session[folder] += 1
            if 0 <= turn < len(turns):
                per_turn[turns[turn]][folder] += 1

    def most(counter):
        return max(counter, key=lambda folder: (counter[folder], -first[folder])) if counter else None
    return lambda at: most(per_turn.get(at, {})) or most(session)


def _evidence(path: Path, kind: str, container: str, owner) -> list[tuple[int, set, bool]]:
    """Every tool call and change of folder in one session file: (offset, project folders, opens next turn).

    Only the calls, never their output: a path named in output is not a place
    the session worked. One call counts once per folder, however often it names it.
    """
    calls, here = [], container
    markers = CALL_MARKERS[kind]
    with path.open("rb") as source:
        offset = 0
        for line in source:
            at, offset = offset, offset + len(line)
            if not any(marker in line for marker in markers):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            named = _named(row, kind, here) if isinstance(row, dict) else None
            if not named:
                continue
            texts, here, ahead = named
            folders = {owner(p, container) for text in texts for p in _paths(text, here)} - {None}
            if folders:
                calls.append((at, folders, ahead))
    return calls


def _named(row: dict, kind: str, here: str):
    """(texts that name paths, the folder the call ran in, whether it opens the next turn), or None."""
    if kind == "claude-code":
        content = (row.get("message") or {}).get("content") if isinstance(row.get("message"), dict) else None
        uses = [part["input"] for part in content if isinstance(part, dict) and part.get("type") == "tool_use"
                and isinstance(part.get("input"), dict)] if isinstance(content, list) else []
        if not uses:
            return None
        cwd = row.get("cwd") if isinstance(row.get("cwd"), str) and row.get("cwd") else here
        return [cwd] + [value for use in uses for key, value in use.items()
                        if key in CLAUDE_PATH_KEYS and isinstance(value, str)], cwd, False
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if row.get("type") == "turn_context":
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
        return ([cwd] if cwd else []), cwd or here, True
    if row.get("type") != "response_item":
        return None
    value = {"function_call": payload.get("arguments"), "custom_tool_call": payload.get("input"),
             "local_shell_call": payload.get("action")}.get(payload.get("type"))
    if value is None:
        return None
    return [value if isinstance(value, str) else json.dumps(value)], here, False


def _paths(text: str, here: str) -> set[str]:
    """Absolute paths named in a call, and `cd` / `git -C` / `workdir` targets resolved against `here`."""
    named = {m.group(1) for m in ABSOLUTE.finditer(text)}
    named |= {os.path.join(here, os.path.expanduser(m.group(1))) for m in MOVED.finditer(text)}
    return {os.path.normpath(os.path.expanduser(p)) for p in named if len(p) < 4096}


class _Owners:
    """A path's deepest project folder inside a workspace: a page's folder, or one with its own `.git`."""

    def __init__(self, folders: dict, rem_root: Path | None):
        self.folders, self.cache = folders, {}
        self.rem = str(rem_root.resolve()) if rem_root else ""

    def __call__(self, path: str, container: str) -> str | None:
        if not path.startswith(container.rstrip("/") + "/"):
            return None  # the workspace itself, or outside it: no evidence
        if path not in self.cache:
            if path in self.folders or os.path.exists(os.path.join(path, ".git")):
                self.cache[path] = path if self._usable(path) else None
            else:
                self.cache[path] = self(os.path.dirname(path), container)
        return self.cache[path]

    def _usable(self, folder: str) -> bool:
        inside_rem = self.rem and (folder == self.rem or folder.startswith(self.rem + "/"))
        return not inside_rem and not project_exclusion(Path(folder))


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
        raise RemError("Refusing to read linked operational state")
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
            days: int = LOOKBACK_DAYS, now: datetime | None = None, recent_days: int = RECENT_DAYS,
            lock_held: bool = False) -> dict:
    """Refresh every project page's material; return counts, never message text.

    With no `since`, the first extraction reads `days` back and every later one
    reads from the previous extraction (less OVERLAP). `full` reads the whole
    window again. New messages are merged by id, so a re-read adds nothing twice.
    A folder with messages and no page gets the map's page if its newest message
    is within `recent_days`; older ones stay listed as `unmapped`. `lock_held`
    says the caller already holds the maintenance lock the new pages need.
    """
    now = now or datetime.now(timezone.utc)
    notebook = Notebook(root)
    base = _private_dir(state_path(root, "projects"))
    index = read_json(base / "index.json", {})
    if since is None:
        previous = index.get("extracted_at")
        since = (timestamp(previous) - OVERLAP) if previous and not full else now - timedelta(days=days)
    folders = page_folders(notebook)
    messages, counts = session_messages(subscriptions, since=since, rem_root=root, folders=folders)
    created = _new_pages(root, _unmapped(messages, folders), now - timedelta(days=recent_days), lock_held)
    if created:
        folders = page_folders(notebook)
    by_page = {}
    for message in messages:
        record = page_for(message["cwd"], folders)
        if record:
            by_page.setdefault(record, []).append(message)
    pages = []
    for record in sorted(set(folders.values())):
        pages.append(_merge(root, record, by_page.get(record, []), full=full, now=now))
    moved = [m for m in messages if m.get("typed_in")]
    workspace = {"attributed": len(moved), "folders": len({m["cwd"] for m in moved}),
                 "stayed_out": counts["excluded"].get(CONTAINER, 0)}
    index = {"extracted_at": now.isoformat(), "since": since.isoformat(), "created": created,
             "workspace": workspace, "unmapped": _unmapped(messages, folders)}
    write_json(base / "index.json", index)
    return {"since": since.isoformat(), "files_read": counts["files"], "messages": len(messages),
            "pages": pages, "created": created, "workspace": workspace, "unmapped": index["unmapped"],
            "excluded": counts["excluded"], "harness_blocks_skipped": counts["harness"],
            "unfamiliar_skipped": counts["unfamiliar"]}


def _unmapped(messages: list[dict], folders: dict) -> list[dict]:
    """Folders with messages and no page, most recently active first."""
    rows = {}
    for message in messages:
        if page_for(message["cwd"], folders):
            continue
        row = rows.setdefault(message["cwd"], {"path": message["cwd"], "messages": 0, "sessions": set(),
                                               "first": message["timestamp"], "last": ""})
        row["messages"] += 1
        row["sessions"].add(message["source"].rsplit(":", 1)[0])
        row["first"] = min(row["first"], message["timestamp"])
        row["last"] = max(row["last"], message["timestamp"])
    return [{**row, "sessions": len(row["sessions"])}
            for row in sorted(rows.values(), key=lambda r: r["last"], reverse=True)]


def _new_pages(root: Path, unmapped: list[dict], cutoff: datetime, lock_held: bool) -> list[str]:
    """The map's page for each folder active since `cutoff` that has none; returns the records made.

    Made by the map's own code (`map.project_groups`, `map.file_project`), so a
    page is the stub, the record name and the worktree-joins-its-repository
    grouping `co rem init` would have given it.
    """
    recent = [row for row in unmapped if timestamp(row["last"]) >= cutoff]
    if not recent:
        return []
    from .map import file_project, project_groups
    from .scan import _repo_identity
    rows = []
    for row in recent:
        repo = _repo_identity(Path(row["path"]))
        rows.append({"path": row["path"], "sessions": row["sessions"], "turns": row["messages"],
                     "first": row["first"][:10],
                     "last": row["last"][:10], "repo": repo.get("toplevel", ""), "origin": repo.get("origin", "")})
    created = []
    with nullcontext() if lock_held else maintenance_lock(root, wait=60):
        notebook = Notebook(root)
        for identity, group in project_groups(rows).items():
            record, made = file_project(notebook, identity, group, refresh=False)
            if made:
                created.append(record)
    return created


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


def mark_refused(root: Path, record: str, through: str, why: str, *, now: datetime | None = None) -> None:
    """The page was refused for the messages up to `through`: wait for newer ones (#2026).

    Retried with the same material, an over-limit page was refused on every
    sync: about 260k tokens and no change in two a6 runs."""
    folder = _private_dir(_folder(root, record))
    state = page_state(root, record)
    state.update(refused_through=through, refused_at=(now or datetime.now(timezone.utc)).isoformat(),
                 refused_why=why[:300])
    write_json(folder / "state.json", state)


def adopt(root: Path, old: str, new: str) -> int:
    """Page `old` was merged into `new` (#1974): its messages go with it.

    Extraction reads only what is new, so messages filed under the old page
    would never be filed again. They are merged by id into the new page's
    material; the old folder moves to `.state/archived/projects/`. Returns how
    many messages were added.
    """
    folder = _folder(root, old)
    if not folder.is_dir():
        return 0
    messages = stored(root, old)
    result = _merge(root, new, messages, full=False, now=datetime.now(timezone.utc)) if messages else {"added": 0}
    target = state_path(root, f"archived/projects-material/{Path(old).stem}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        target = target.with_name(f"{target.name}-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}")
    folder.replace(target)
    return result["added"]
