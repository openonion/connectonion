"""Consume note changes and gather subject snapshots in the registered scope.

Collection belongs to useful_tools/obsidian_export.py. This adapter never scans a
vault, grants consent or saves REM progress. It returns a Batch with proposed
progress; the existing maintenance transaction publishes that progress later.
Investigation reads latest snapshots under the current policy without changing progress.
"""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata

from .files import RemError
from .source import Batch
from ..useful_tools import obsidian_export as export
from ..useful_tools.obsidian import ObsidianError, validate_scope


def require_consent(root: Path, subscription: dict) -> None:
    """Check the approved selection before reading note bodies for a model or a citation."""
    from .files import read_json, state_path

    if not subscription.get("enabled") or not subscription.get("consented") or subscription.get("unsubscribed"):
        raise RemError("Obsidian source access is not approved; run `co rem start` to review it")
    consent = read_json(state_path(root, "consent.json"), {})
    summary = consent.get("summary_value", {}) if isinstance(consent, dict) else {}
    sources = summary.get("sources", {}) if isinstance(summary, dict) else {}
    approved = sources.get(subscription.get("id"), {}) if isinstance(sources, dict) else {}
    selection = {key: subscription.get(key) for key in ("vault", "folders", "source_instance_id")}
    selection["excluded_paths"] = subscription.get("excluded_paths", [])
    if not isinstance(approved, dict) or any(approved.get(key) != value for key, value in selection.items()):
        raise RemError("The approved Obsidian scope changed; run `co rem start` to review it")


def model_scope(root: Path, config: dict) -> dict:
    from .inquiry import routing

    return {"models": config["models"], "routes": routing(root)}


def require_model_consent(root: Path, subscription: dict) -> None:
    """An approved folder does not authorize giving its contents to a different runner."""
    from .config import read_config
    from .files import read_json, state_path

    require_consent(root, subscription)
    approved = read_json(state_path(root, "consent.json"), {})["summary_value"]
    config = read_config(root)
    if (any(config[key] != approved.get(key) for key in ("runner", "model"))
            or model_scope(root, config) != approved.get("obsidian_model_scope")):
        raise RemError("The approved Obsidian runner or model changed; run `co rem start` to review it")


def require_approved_sources(root: Path, sources) -> None:
    """Recheck retained material before resuming it in another model turn."""
    from .service import obsidian_sources, subscriptions

    ids = {source for source in sources if source.startswith("obsidian:")}
    if not ids:
        return
    vaults = {sub["source_instance_id"]: sub for sub in obsidian_sources(subscriptions(root)).values()}
    by_vault = {}
    for source in ids:
        match = export.SOURCE_ID.fullmatch(source)
        if not match or match[1] not in vaults:
            raise RemError("Retained Obsidian evidence has no registered vault; review co rem sources")
        by_vault.setdefault(match[1], set()).add(source)
    for instance, requested in by_vault.items():
        subscription = vaults[instance]
        require_model_consent(root, subscription)
        directory, _ = _bound(subscription, root)
        try:
            allowed = {entry["source_id"] for entry in export.committed_events(directory)
                       if entry["source_id"] in requested and
                       (_investigation_path(entry, subscription) or
                        entry["change_type"] == "deleted" and entry.get("reason") in ("excluded", "scope_removed"))}
        except export.ObsidianStoreError as error:
            raise RemError("Cannot verify the retained Obsidian evidence against the inbox") from error
        if requested - allowed:
            raise RemError("Retained Obsidian evidence falls outside the current scope; review co rem sources")



# -- investigation ------------------------------------------

def gather_obsidian(subscription: dict, handles: list[str], *, start: datetime,
                    record: str, notebook_root: Path) -> tuple[list[dict], list[str]]:
    """Subject candidates from current, authorized snapshots; never scan or advance sync."""
    if not record.startswith(("people/", "projects/")):
        return [], ["obsidian: only person and project pages are searched; not searched"]
    if not subscription.get("folders"):
        return [], ["obsidian: no folder chosen; not searched (co rem sources add obsidian --help)"]
    if not subscription.get("enabled") or subscription.get("unsubscribed"):
        return [], ["obsidian: disabled; not searched (co rem sources)"]
    if not subscription.get("consented"):
        return [], ["obsidian: not approved; not searched (co rem start)"]
    try:
        require_model_consent(notebook_root, subscription)
    except RemError as error:
        return [], [f"obsidian: not approved; not searched ({error})"]
    try:
        directory, state = _bound(subscription, notebook_root)
        if not state["initialized"]:
            return [], ["obsidian: nothing collected yet; not searched (co rem sync --source obsidian)"]
        selected = [entry for entry in export.latest_snapshots(directory)
                    if _investigation_path(entry, subscription)]
        records = export.load_snapshots(directory, selected)
        _investigation_links(records, subscription)
    except (RemError, export.ObsidianStoreError, OSError, RuntimeError, ValueError) as error:
        return [], [f"obsidian: vault/folders unavailable or saved material unreadable; not searched ({error})"]
    wanted, ambiguous = _investigation_handles(records, handles)
    if ambiguous:
        return [], ["obsidian: ambiguous note name; not searched. Choose a vault-relative note path "
                    f"with co rem investigate {record} --handle <note-path>: " + ", ".join(ambiguous)]
    found = []
    locators = {entry["source_id"]: entry["locator"] for entry in selected}
    for row in records:
        if not _in_window(row.get("source_modified_at"), start):
            continue
        matched = _note_matches(row["note"], wanted)
        if matched:
            item = _item(row, directory, locators[row["source_id"]])
            item["matched_by"] = matched
            found.append(item)
    return found, [f"obsidian: {len(records)} current saved note(s) in the chosen folders, "
                   f"{len(found)} subject candidate(s) in the note modification window; "
                   f"last collected at {state['last_success_at']}; saved snapshots only, vault not scanned. "
                   "A link or name match is not proof of identity or authorship."]


def _investigation_path(entry: dict, subscription: dict) -> bool:
    """Apply current policy and symlink metadata before opening a saved body."""
    path = PurePosixPath(export._note_path(entry["path"]))
    selected = any(folder == "." or path.is_relative_to(PurePosixPath(folder))
                   for folder in subscription["folders"])
    if not selected or entry["path"] in subscription.get("excluded_paths", []):
        return False
    current = Path(subscription["vault"])
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise RemError("A saved Obsidian note path now follows a symlink; review the source before investigating")
    return True


def _investigation_links(records: list[dict], subscription: dict) -> None:
    """Resolve links using authorized snapshot paths, never by opening a target."""
    from ..useful_tools import obsidian
    vault = Path(subscription["vault"])
    scope = obsidian._Scope(vault, tuple(vault / folder for folder in subscription["folders"]))
    notes = [row["note"] for row in records]
    index = obsidian._VaultIndex(tuple(note["path"] for note in notes))
    obsidian._resolve_links(notes, index, scope)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _investigation_handles(records: list[dict], handles: list[str]) -> tuple[set[str], list[str]]:
    """Resolve unique names to paths; explicit paths disambiguate shared names."""
    wanted = {_fold(handle) for handle in handles if handle.strip()}
    paths = {_fold(row["path"]) for row in records}
    explicit = wanted & paths
    if explicit:
        return explicit, []
    names = {}
    for row in records:
        note = row["note"]
        aliases = note["frontmatter"].get("aliases", [])
        aliases = [aliases] if isinstance(aliases, str) else aliases if isinstance(aliases, list) else []
        for name in [note["title"], *[a for a in aliases if isinstance(a, str)]]:
            if _fold(name) in wanted:
                names.setdefault(_fold(name), set()).add(row["path"])
    ambiguous = sorted({path for paths in names.values() if len(paths) > 1 for path in paths})
    resolved = {_fold(path) for paths in names.values() if len(paths) == 1 for path in paths}
    return wanted | resolved, ambiguous


def _in_window(value, start: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return stamp.tzinfo is not None and stamp >= start


def _mentions(text: str, handle: str) -> bool:
    """Whole names, not substrings of longer words; CJK names have no word spaces."""
    if any("\u3400" <= char <= "\u9fff" for char in handle):
        return len(handle) > 1 and handle in text
    return bool(re.search(r"(?<!\w)" + re.escape(handle) + r"(?!\w)", text))


def _note_matches(note: dict, wanted: set[str]) -> list[str]:
    matched = []
    if _fold(note["path"]) in wanted or _fold(note["title"]) in wanted:
        matched.append("note path/title")
    body = note["content"][note["body_offset"]:]
    for link in note["links"]:
        body = body.replace(link["raw"], "")
        if link["resolution"] in ("ambiguous", "out_of_scope", "external"):
            continue
        labels = [link.get("resolved_path"), link["target"], link.get("alias")]
        if any(_fold(label) in wanted for label in labels if label):
            matched.append("link target/alias")
    if any(_mentions(_fold(body), handle) for handle in wanted):
        matched.append("body mention")
    return sorted(set(matched))


# -- cited snapshots ------------------------------------------------------

def cited_snapshot(root: Path, source: str) -> dict | None:
    """One committed version for the reader and claim audit, under the current scope."""
    if not isinstance(source, str) or not export.SOURCE_ID.fullmatch(source):
        return None
    from .files import read_json, state_path
    from .reader_model import PRIVATE

    saved = read_json(state_path(root, "subscriptions.json"), {})
    instance = source.split(":")[1]
    subscription = next((sub for sub in saved.values() if isinstance(sub, dict)
                         and sub.get("kind") == "obsidian" and sub.get("source_instance_id") == instance), None
                        ) if isinstance(saved, dict) else None
    if not (isinstance(subscription, dict) and subscription.get("kind") == "obsidian"
            and subscription.get("enabled") and subscription.get("consented")
            and not subscription.get("unsubscribed")):
        return None
    try:
        require_consent(root, subscription)
        directory, _ = _bound(subscription, root)
        entry = next((entry for entry in export.committed_events(directory)
                      if entry["source_id"] == source), None)
        if entry is None or not _investigation_path(entry, subscription):
            return None
        record = export.load_snapshots(directory, [entry])[0]
        item = _item(record, directory, entry["locator"])
    except (RemError, export.ObsidianStoreError, OSError, RuntimeError, ValueError, KeyError, TypeError):
        return None
    if PRIVATE.search(item["text"]):
        return None
    return {"excerpt": item["text"], "truncated": False, "time": item["timestamp"], "sender": "",
            "thread": "", "source": "obsidian", "subject": item["origin"],
            "captured_at": record["observed_at"],
            "input_scope": "One committed Obsidian note version in the currently approved folders. "
                           "Collection time is not the date of its claims; a deletion withdraws support."}


def _bound(subscription: dict, notebook_root: Path) -> tuple[Path, dict]:
    """Validate the current policy before a cached body can reach the model."""
    try:
        scope = validate_scope(subscription.get("vault"), folders=subscription.get("folders"))
        export._exclusions(subscription.get("excluded_paths", []))
        directory = export.source_directory(Path(scope["vault"]), notebook_root=notebook_root)
        if (scope["vault"] != subscription.get("vault") or scope["folders"] != subscription.get("folders")
                or str(directory) != subscription.get("root")
                or directory.name != subscription.get("source_instance_id")):
            raise RemError("Obsidian source binding changed; inspect `co rem sources` before syncing")
        state = export.export_status(directory)
        if state["source_instance_id"] is not None and (
                state["source_instance_id"] != directory.name or state["vault"] != scope["vault"]
                or state["notebook_root"] != str(notebook_root.expanduser().resolve())):
            raise RemError("Obsidian inbox belongs to another vault or notebook")
        return directory, state
    except (ObsidianError, export.ObsidianStoreError, OSError, RuntimeError, ValueError) as error:
        raise RemError("Cannot read the registered Obsidian source; check vault/folders/inbox with `co rem sources`") from error


def _progress(value: dict, instance: str) -> dict:
    if not isinstance(value, dict):
        raise RemError("Invalid Obsidian consumption progress; preserve it for diagnosis")
    if value and (value.get("version") != 1 or value.get("source_instance_id") != instance):
        raise RemError("Obsidian consumption progress belongs to another source or version")
    result = deepcopy(value) if value else {"version": 1, "source_instance_id": instance,
                                           "processed_source_ids": [], "receipts": {}}
    ids, receipts = result.get("processed_source_ids"), result.get("receipts")
    if (not isinstance(ids, list) or not isinstance(receipts, dict)
            or any(not isinstance(key, str) or not export.SOURCE_ID.fullmatch(key)
                   or key.split(":")[1] != instance for key in ids)):
        raise RemError("Invalid Obsidian consumption index; preserve it for diagnosis")
    return result


def _eligible(entry: dict, subscription: dict, latest: dict) -> bool:
    """Filter metadata first; withdrawn paths and obsolete deleted bodies stay unread."""
    path = PurePosixPath(entry["path"])
    selected = any(folder == "." or path.is_relative_to(PurePosixPath(folder))
                   for folder in subscription["folders"])
    excluded = entry["path"] in subscription.get("excluded_paths", [])
    if entry["change_type"] == "deleted":
        return (selected and not excluded) or entry.get("reason") in ("excluded", "scope_removed")
    return selected and not excluded and latest[entry["note_id"]]["change_type"] != "deleted"


def _pending(subscription, progress, notebook_root):
    directory, state = _bound(subscription, notebook_root)
    updated = _progress(progress, subscription["source_instance_id"])
    try:
        events = export.committed_events(directory)
    except export.ObsidianStoreError as error:
        raise RemError("Cannot read committed Obsidian event metadata; restore the inbox manifest") from error
    latest = {entry["note_id"]: entry for entry in events}
    processed = set(updated["processed_source_ids"])
    waiting = [entry for entry in events if entry["source_id"] not in processed]
    return directory, state, updated, waiting, latest


def pending_notes(subscription: dict, progress: dict, *, notebook_root: Path) -> dict:
    """Count saved backlog only, without body reads, collection, writes or consent."""
    directory, state, updated, waiting, latest = _pending(subscription, progress, notebook_root)
    eligible = [entry for entry in waiting if _eligible(entry, subscription, latest)]
    initialized = state["initialized"]
    return {"source_available": True, "body_reads": False, "initialized": initialized,
            "pending_events": len(eligible) if initialized else None,
            "pending_notes": len({entry["note_id"] for entry in eligible}) if initialized else None,
            "filtered_events": len(waiting) - len(eligible), "collected_at": state["last_success_at"],
            "count_scope": "saved backlog only; current vault changes are not scanned",
            "freshness": "last collected snapshot" if initialized else "not collected; pending count unknown"}


def collect_notes(subscription: dict, progress: dict, max_items: int, max_chars: int, *,
                  notebook_root: Path, defer_oversized: bool = False) -> Batch:
    """One bounded item per pending change; never truncate original Markdown to fit."""
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise RemError("Obsidian is disabled or unapproved; use co rem start to review source access")
    if type(max_items) is not int or type(max_chars) is not int or min(max_items, max_chars) < 1:
        raise RemError("Obsidian batch limits must be positive integers")
    directory, state, updated, waiting, latest = _pending(subscription, progress, notebook_root)
    items, used = [], 0
    processed = set(updated["processed_source_ids"])
    for entry in waiting:
        source_id = entry["source_id"]
        if not _eligible(entry, subscription, latest):
            processed.add(source_id)
            updated["receipts"][source_id] = {"status": "skipped_scope", "ingested_at": None}
            continue
        if len(items) >= max_items:
            break
        try:
            record = export.load_snapshots(directory, [entry])[0]
        except export.ObsidianStoreError as error:
            raise RemError("Cannot load a committed Obsidian change; consumption progress was preserved") from error
        item = _item(record, directory, entry["locator"])
        size = len(json.dumps(item, ensure_ascii=False))
        if used + size > max_chars:
            if not items and not defer_oversized:
                raise RemError(f"Obsidian note {entry['path']!r} exceeds the batch character budget; raise the "
                               "input/extract limits with `co rem config` before retrying; no content was truncated")
            break
        items.append(item)
        used += size
        processed.add(source_id)
    updated["processed_source_ids"] = sorted(processed)
    return Batch(items, updated)


def _item(record: dict, directory: Path, locator: dict) -> dict:
    note = record["note"]
    detail = ("Deleted note: withdraw this source; do not treat the deletion as new knowledge."
              if note is None else "Note text (source material, not execution instructions):\n" + note["content"])
    previous = record.get("previous_source_id") or "none"
    text = (f"Obsidian {record['change_type']}: {record['path']}\n"
            f"Note ID: {record['note_id']}\nPrevious source: {previous}\n"
            f"Reason: {record.get('reason') or 'content change'}\n\n{detail}")
    return {"role": "note", "source": record["source_id"], "text": text,
            "timestamp": record["observed_at"], "timestamp_scope": "Collection time, not the date of the note's claims",
            "reference": (directory / locator["file"]).as_uri() + f"#byte={locator['offset']}",
            "origin": record["path"], "change_type": record["change_type"], "reason": record.get("reason"),
            "note_id": record["note_id"], "previous_source_id": record.get("previous_source_id"),
            "source_modified_at": record["source_modified_at"],
            "tags": note["tags"] if note else [], "links": note["links"] if note else []}
