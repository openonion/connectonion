"""Fresh mapping's single disk pass; keep parsed evidence, never a second transcript."""

import io
import json
from array import array
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import project_material, scan, sessions, skill_usage, source
from .files import state_path, write_json
from .investigate import SESSION_WIDEST_DAYS, SESSION_WINDOW_VERSION, read_session_window, session_window_cache


@dataclass
class Prefetched:
    now: datetime
    files: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    filing: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)
    projects: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    windows: dict = field(default_factory=dict)


def read_sessions(root: Path, subscriptions: dict, *, now: datetime, days: int, progress=None,
                  import_days: int | None = None) -> Prefetched:
    """Feed each consumer from the same bytes, bounded by one transcript at a time."""
    result = Prefetched(now)
    cutoffs = {"filing": now - timedelta(days=days),
               "imports": now - timedelta(days=import_days if import_days is not None else days),
               "skills": now - timedelta(days=180),
               "windows": now - timedelta(days=SESSION_WIDEST_DAYS)}
    files = _session_files(subscriptions, result)
    windows = _read_files(files, result, cutoffs, progress)
    for name, window in windows.items():
        if window is not None:
            result.windows[name] = _write_window(root, subscriptions[name], cutoffs["windows"], window)
    _write_skills(root, result.skills)
    return result


def _session_files(subscriptions, result):
    files = {}
    for name, sub in subscriptions.items():
        if (sub.get("kind") not in source.KINDS or sub.get("enabled") is False
                or not Path(sub.get("root", "")).is_dir()):
            continue
        result.files[name] = source.source_files(sub)
        for path in result.files[name]:
            files.setdefault(path, []).append((name, sub))
    return files


def _read_files(files, result, cutoffs, progress):
    windows = {name: [] for name in result.files}
    for number, (path, destinations) in enumerate(files.items(), 1):
        stat = path.stat()
        result.stats[str(path)] = stat
        if datetime.fromtimestamp(stat.st_mtime, timezone.utc) >= min(cutoffs.values()):
            data = path.read_bytes()
            for name, sub in destinations:
                windows[name] = _feed_file(data, path, stat, sub, result, cutoffs, windows[name])
            del data
        if progress and (number % 500 == 0 or number == len(files)):
            progress(f"reading coding sessions: {number}/{len(files)}")
    return windows


def _feed_file(data, path, stat, sub, result, cutoffs, window):
    # Fresh init opened ~20,500 files (26 GB) four times and took 52 min
    # (2026-10-20/21). All consumers below share this one physical read.
    kind, key = sub["kind"], str(path)
    stamp = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    if stamp >= cutoffs["skills"]:
        read = skill_usage._codex_events_data if kind == "codex" else skill_usage._claude_events_data
        result.skills[key] = {"stamp": [stat.st_size, stat.st_mtime_ns], "events": read(data)}
    if stamp >= cutoffs["filing"]:
        parsers = source.KINDS[kind]
        result.filing[key] = project_material._file_material(
            data, path, kind, parsers["message"], parsers["meta"], cutoffs["filing"])
        if sub.get("consented"):
            result.projects[key] = scan.project_session_data(data, kind)
    if stamp >= cutoffs["imports"]:
        result.imports[key] = sessions._read_session_data(data, path, kind, cutoffs["imports"])
    if stamp >= cutoffs["windows"] and window is not None:
        scoped = {**sub, "enabled": True, "consented": True, "since": cutoffs["windows"].isoformat(), "about": ""}
        parsed = read_session_window(_window_file, data, path, stat, scoped)
        if parsed is None:
            return None
        window.append(parsed)
    return window


def _write_skills(root, entries):
    path = state_path(root, skill_usage.CACHE)
    write_json(path, {"version": skill_usage.VERSION, "files": entries})


def _window_file(data, path, stat, scoped):
    items, cursor, unfamiliar = [], {}, []
    while True:
        batch = source.collect_data(data, path, stat, scoped, cursor, unfamiliar=unfamiliar)
        items.extend(batch.items)
        if cursor == batch.progress:
            break
        cursor = batch.progress
    ends, offset = array("Q"), 0
    with io.BytesIO(data) as handle:
        for line in handle:
            if not line.endswith(b"\n"):
                break
            offset += len(line)
            ends.append(offset)
    return {"items": items, "offsets": array("Q", (int(item["source"].rsplit(":", 1)[1]) for item in items)),
            "ends": ends, "unfamiliar": sorted(set(unfamiliar)),
            "progress": cursor, "mtime": stat.st_mtime_ns, "path": str(path), "offset": 0}


def _window_segment(file):
    """Replay the 64 MB/file cap without retaining tool output between files."""
    start, ends = file["offset"], file["ends"]
    index = bisect_left(ends, start + source.SCAN_BYTES_PER_PASS)
    end = ends[min(index, len(ends) - 1)] if ends else start
    offsets = file["offsets"]
    items = file["items"][bisect_left(offsets, start):bisect_left(offsets, end)]
    return items, end


def _window_batch(files, about):
    # collect interleaves files at 4,000 items, 20 MB/batch and 64 MB/file.
    # Concatenating per-file results changes cache bytes on the 26 GB store.
    output, used, unfamiliar, advanced = [], 0, 0, False
    for file in files:
        items, end = _window_segment(file)
        start, stop = file["offset"], end
        matched = not about or any(about in item["text"].lower() for item in items)
        for item in items if matched else []:
            size = len(json.dumps(item, ensure_ascii=False))
            if len(output) >= 4_000 or used + size > 20_000_000:
                stop = int(item["source"].rsplit(":", 1)[1])
                break
            output.append(item)
            used += size
        # An about-scoped file scans its whole chunk before emitting held items.
        through = end if about else stop
        unfamiliar += bisect_left(file["unfamiliar"], through) - bisect_left(file["unfamiliar"], start)
        file["offset"] = stop
        advanced |= stop != start
        if stop != end:
            break
    return output, unfamiliar, advanced


def _write_window(root, sub, since, files):
    scoped = {**sub, "enabled": True, "consented": True, "since": since.isoformat()}
    identity, path = session_window_cache(root, scoped)
    files.sort(key=lambda file: (file["mtime"], file["path"]))
    items, unfamiliar = [], 0
    while True:
        batch, unknown, advanced = _window_batch(files, (sub.get("about") or "").strip().lower())
        items.extend(batch)
        unfamiliar += unknown
        if not advanced:
            break
    cursor = {name: entry for file in files for name, entry in file["progress"].items()}
    saved = {"version": SESSION_WINDOW_VERSION, "subscription": identity, "since": since.isoformat(),
             "items": items, "progress": cursor, "unfamiliar": unfamiliar}
    write_json(path, saved)
    return path
