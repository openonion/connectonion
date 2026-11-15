"""Local Obsidian adapter matching the draft #3040 source protocol.

Registered through the provisional selected-source dispatcher. Content hooks
require a current approved selection, checked again under the snapshot storage lock. The shared
stage still owns notebook-wide consent verification and checkpoint commits.
Content reads reuse a notebook lock held by the current thread; acquisition
runs before the long-lived stage lock. The interface is pending #3040 review.
"""

from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from . import obsidian, obsidian_store as store
from .files import RemError
from .source import Batch, _fit, timestamp


kind = "obsidian"
skill = "rem-source-obsidian"
GATHER_MAX_ITEMS = 100
GATHER_MAX_CHARS = 100_000
record_of = obsidian.record_of


def status(subscription: dict) -> dict:
    """Describe configured names and scope; never probe the live vault or store."""
    selection = obsidian._saved_selection(subscription)
    return {"kind": kind, "vault": str(selection.vault), "folders": list(selection.folders),
            "enabled": subscription.get("enabled", False),
            "consented": subscription.get("consented", False),
            "unsubscribed": subscription.get("unsubscribed", False)}


def consent(subscription: dict) -> str:
    """Describe acquisition and model use without granting access."""
    info = status(subscription)
    return (f"Read Markdown in {', '.join(info['folders'])} from vault {info['vault']}; "
            "save local snapshots for REM batches, investigation and exact-version citations.")


def fetch(root: Path, subscription: dict) -> dict:
    """Acquire scoped snapshots locally; call outside the stage's notebook lock."""
    from .source_hooks import SourceUnavailable
    try:
        return store.collect(root, expected=subscription)
    except (OSError, obsidian.vault_reader.ObsidianError) as error:
        raise SourceUnavailable("Selected vault could not be collected; check co obsidian ls and retry sync") from error


def _checkpoint(root: Path, subscription: dict, progress: dict) -> dict:
    selection = obsidian._saved_selection(subscription)
    value = [str(root.resolve()), str(selection.vault), sorted(selection.folders)]
    scope = sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()
    if not isinstance(progress, dict):
        raise RemError("Invalid Obsidian batch progress; preserve it for diagnosis")
    if progress and (set(progress) != {"scope", "sequence"} or not isinstance(progress["scope"], str)
                     or type(progress["sequence"]) is not int or progress["sequence"] < 0):
        raise RemError("Invalid Obsidian batch progress; preserve it for diagnosis")
    sequence = progress["sequence"] if progress.get("scope") == scope else 0
    return {"scope": scope, "sequence": sequence}


def _item(snapshot: dict) -> dict | None:
    context = obsidian._snapshot_context(snapshot)
    if context is None:
        return None
    return {"source": snapshot["source_id"], "role": "note", "speaker": "",
            "text": context["excerpt"], "subject": context["subject"], "project": "",
            "reference": context["subject"], "timestamp": context["time"],
            "captured_at": context["captured_at"], "input_scope": context["input_scope"]}


def _size(item: dict) -> int:
    return len(json.dumps(item, ensure_ascii=False))


def collect(root: Path, subscription: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    """Read saved changes without source I/O or persisted checkpoint changes.

    Only current versions are offered; deleted/superseded events are consumed
    without replaying old text. Scope changes restart consumption. A first note
    larger than the input budget is explicitly truncated using REM's fitter.
    """
    if type(max_items) is not int or type(max_chars) is not int or min(max_items, max_chars) <= 0:
        raise ValueError("Batch limits must be positive integers")
    checkpoint = _checkpoint(root, subscription, progress)
    items, used = [], 0
    with closing(store.iter_changes(root, checkpoint["sequence"], expected=subscription)) as changes:
        for change in changes:
            item = _item(change["snapshot"]) if change["snapshot"] is not None else None
            if item is not None:
                if len(items) == max_items or items and used + _size(item) > max_chars:
                    break
                item = _fit(item, max_chars) if not items else item
                items.append(item)
                used += _size(item)
            checkpoint["sequence"] = change["sequence"]
    return Batch(items, checkpoint)


def gather(root: Path, subscription: dict, handles: list[str], *, start: datetime,
           record: str) -> tuple[list[dict], list[str]]:
    """Literal candidate matches in current saved notes, filtered by saved mtime.

    start limits note modification time, not the dates of claims in the text.
    Matching a handle is evidence to inspect, not a claim of person identity.
    record is the target REM page; it does not widen the source selection.
    """
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("Investigation start must include a timezone")
    if not handles or isinstance(handles, str) or any(not isinstance(h, str) or not h.strip() for h in handles):
        raise ValueError("Investigation needs nonempty handles")
    needles = list(dict.fromkeys(handle.strip().casefold() for handle in handles))
    items, used, limited = [], 0, False
    with closing(store.iter_latest(root, expected=subscription)) as snapshots:
        for snapshot in snapshots:
            item = _item(snapshot)
            if item is None or timestamp(item["timestamp"]) < start:
                continue
            text = (item["subject"] + "\n" + item["text"]).casefold()
            if not any(needle in text for needle in needles):
                continue
            if len(items) == GATHER_MAX_ITEMS or items and used + _size(item) > GATHER_MAX_CHARS:
                limited = True
                break
            fitted = _fit(item, GATHER_MAX_CHARS) if not items else item
            limited = limited or fitted != item
            items.append(fitted)
            used += _size(fitted)
    suffix = "; limited by the investigation budget" if limited else ""
    return items, [f"obsidian: {len(items)} saved note match(es) in the selected folders{suffix}; "
                   "matched literal text within the saved modification-time window, not claim dates"]


def cited(root: Path, subscription: dict, source_id: str) -> dict | None:
    """Return the exact saved version only while the supplied scope remains approved."""
    return obsidian.cited(root, source_id, expected=subscription)


def pending(root: Path, subscription: dict, progress: dict) -> dict:
    checkpoint = _checkpoint(root, subscription, progress)
    return store.pending_metadata(root, checkpoint["sequence"], expected=subscription)


def configure(root: Path, *, vault: str, folders: list[str], replace: bool = False) -> dict:
    """Explicit selection command; paths are validated, note bodies are not read."""
    if not vault or not folders:
        raise RemError("Name one vault and explicit folders: --vault <path> --folder <folder>")
    try:
        path = Path(vault).expanduser()
        if not path.is_absolute():
            matches = [row for row in obsidian.vault_reader.discover_vaults() if row["name"] == vault]
            if len(matches) != 1:
                raise RemError("Vault name is missing or ambiguous; use its absolute path from co obsidian vaults")
            path = Path(matches[0]["path"])
        if root.resolve().is_relative_to(path.resolve()):
            raise RemError("The snapshot notebook must be outside the Obsidian vault")
        selection = obsidian.save_selection(root, path, folders, replace=replace)
    except obsidian.vault_reader.ObsidianError as error:
        raise RemError(str(error)) from error
    return {"subscription": kind, "enabled": True, "vault": str(selection.vault),
            "folders": list(selection.folders), "consented": obsidian._subscriptions(root)[kind]["consented"]}
