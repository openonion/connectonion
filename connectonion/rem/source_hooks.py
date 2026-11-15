"""Selected-source boundary proposed in #3040; initial single-vault integration.

Register module paths, never imported provider objects. Each operation reads
current saved selections before loading a module. Imports and metadata hooks
must not open source storage, decrypt credentials or use the network.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import importlib
from pathlib import Path
from typing import Protocol, TYPE_CHECKING, cast

from .files import RemError, material_lock, read_json, state_path
from . import source_versions

if TYPE_CHECKING:
    from .source import Batch


class Source(Protocol):
    """A module of functions; acquisition and offline consumption are separate.

    Subscription is the current saved selection, not a credential container.
    Data methods revalidate its scope at the storage boundary. collect returns
    proposed progress; only the caller commits it after the batch is accepted.
    """

    kind: str
    skill: str

    def status(self, subscription: dict) -> dict: ...
    def consent(self, subscription: dict) -> str: ...
    def pending(self, root: Path, subscription: dict, progress: dict) -> dict: ...
    def configure(self, root: Path, **options) -> dict: ...
    def fetch(self, root: Path, subscription: dict) -> dict: ...
    def collect(self, root: Path, subscription: dict, progress: dict,
                max_items: int, max_chars: int) -> Batch: ...
    def gather(self, root: Path, subscription: dict, handles: list[str], *,
               start: datetime, record: str) -> tuple[list[dict], list[str]]: ...
    def record_of(self, source_id: str) -> str | None: ...
    def cited(self, root: Path, subscription: dict, source_id: str) -> dict | None: ...


# One registration per kind, in code (never an import path from notebook JSON).
# Provider migrations add their entries here after the contract is agreed.
MODULES: dict[str, str] = {"obsidian": "connectonion.rem.obsidian_source"}


class SourceUnavailable(RemError):
    """An expected acquisition failure with a safe explanation, no secrets/body.

    Adapters translate only expected service/file availability errors to this
    type. Programming errors and corrupt saved data must propagate instead.
    """


def selected(root: Path) -> dict[str, dict]:
    """Enabled registered selections, without importing or probing any source."""
    saved = read_json(state_path(root, "subscriptions.json"), {})
    if not isinstance(saved, dict):
        raise RemError("Invalid subscriptions file; preserve it for diagnosis")
    result = {}
    for name, subscription in saved.items():
        if not isinstance(subscription, dict):
            raise RemError("Invalid source subscription; preserve it for diagnosis")
        for flag in ("enabled", "consented", "unsubscribed"):
            if flag in subscription and type(subscription[flag]) is not bool:
                raise RemError(f"Invalid source {flag} flag; preserve it for diagnosis")
        if (subscription.get("kind") in MODULES and subscription.get("enabled")
                and not subscription.get("unsubscribed")):
            result[name] = subscription
    return result


def _load(subscription: dict) -> Source:
    kind = subscription["kind"]
    module = cast(Source, importlib.import_module(MODULES[kind]))
    if module.kind != kind:
        raise RemError(f"Source module does not declare registered kind {kind!r}")
    return module


def _approved(root: Path, name: str) -> dict:
    subscription = selected(root).get(name)
    if subscription is None or not approved(root, name, subscription):
        raise RemError("Source is disabled or not yet authorized; run start to confirm access")
    return subscription


def statuses(root: Path) -> dict[str, dict]:
    """Selected source metadata only, including sources awaiting consent."""
    return {name: _load(sub).status(sub) for name, sub in selected(root).items()}


def consent_lines(root: Path) -> dict[str, str]:
    """Describe selection before reading it; this does not grant consent."""
    return {name: _load(sub).consent(sub) for name, sub in selected(root).items()}


def fetch(root: Path, *, names=None) -> dict[str, dict]:
    """Acquire snapshots before the caller takes its long-lived notebook lock.

    A local source may scan selected files; a remote source may call its API.
    Each adapter owns short storage transactions/locks and scope revalidation.
    An expected failure is explicit and does not stop other selected sources.
    """
    results = {}
    for name, sub in selected(root).items():
        if (names is not None and name not in names) or not approved(root, name, sub):
            continue
        try:
            sub = _approved(root, name)
            results[name] = {"ok": True, "result": _load(sub).fetch(root, sub)}
        except SourceUnavailable as error:
            results[name] = {"ok": False, "error": str(error)}
    return results


def collect(root: Path, name: str, progress: dict, max_items: int, max_chars: int) -> Batch:
    """Consume saved material only; never mutate the caller's checkpoint.

    Caller owns the notebook transaction and persists Batch.progress only when
    the corresponding REM work is kept. Provider must honor both input limits.
    """
    if max_items <= 0 or max_chars <= 0:
        raise ValueError("Batch limits must be positive")
    with material_lock(root):
        sub = _approved(root, name)
        return _load(sub).collect(root, sub, deepcopy(progress), max_items, max_chars)


def gather(root: Path, handles: list[str], *, start: datetime, record: str, names=None
           ) -> tuple[list[dict], list[str]]:
    """Search approved saved selections; unselected sources add no coverage."""
    items, coverage = [], []
    for name, sub in selected(root).items():
        if (names is not None and name not in names) or not approved(root, name, sub):
            continue
        with material_lock(root):
            sub = _approved(root, name)
            found, lines = _load(sub).gather(root, sub, list(handles), start=start, record=record)
        items.extend(found)
        coverage.extend(lines)
    return items, coverage


def _version_kind(root: Path, prefix: str) -> source_versions.Kind | None:
    matches = [(name, sub) for name, sub in selected(root).items()
               if sub["kind"] == prefix and approved(root, name, sub)]
    if not matches:
        return None
    provider = _load(matches[0][1])

    def snapshot(notebook: Path, source_id: str) -> dict | None:
        with material_lock(notebook):
            for name, _ in matches:
                sub = selected(notebook).get(name)
                if sub is None or sub["kind"] != prefix or not approved(notebook, name, sub):
                    continue
                value = provider.cited(notebook, sub, source_id)
                if value is not None:
                    return value
            return None

    return source_versions.Kind(provider.record_of, snapshot)


def record_of(root: Path, source_id: str) -> str | None:
    """Read selection, then ask a pure ID parser; no existence/order guarantee."""
    return source_versions.record_of(source_id, resolve=lambda kind: _version_kind(root, kind))


def cited(root: Path, source_id: str) -> dict | None:
    """Exact saved version in current approved scope; never fetch or use latest."""
    return source_versions.cited(root, source_id, resolve=lambda kind: _version_kind(root, kind))


def superseded(root: Path, before: set[str], after: set[str]) -> set[str]:
    """Reuse #3055's same-record replacement rule within this notebook."""
    return source_versions.superseded(before, after, resolve=lambda kind: _version_kind(root, kind))


def scope_value(subscription: dict) -> dict:
    """Stable configured scope in the existing consent summary, without runtime status."""
    ignored = {"id", "enabled", "consented", "unsubscribed", "adapter", "status"}
    return {key: value for key, value in subscription.items() if key not in ignored}


def approved(root: Path, name: str, subscription: dict | None = None) -> bool:
    """Check selection and the recorded scope/model approval without reading source storage."""
    from .config import read_config
    sub = selected(root).get(name) if subscription is None else subscription
    if not sub or not sub.get("enabled") or not sub.get("consented") or sub.get("unsubscribed"):
        return False
    receipt = read_json(state_path(root, "consent.json"), {})
    summary = receipt.get("summary_value", {})
    agreed = summary.get("sources", {}).get(name, {})
    if agreed.get("scope") != scope_value(sub):
        return False
    config = read_config(root, validated=False)
    return all(summary.get(key) == config[key] for key in ("runner", "model"))


def pending(root: Path, name: str, progress: dict) -> dict:
    """Metadata only; a selection waiting for approval does not open source storage."""
    sub = selected(root)[name]
    if not approved(root, name, sub):
        return {"body_reads": False, "consented": False, "note": "Run co rem start to approve this selection"}
    return _load(sub).pending(root, sub, deepcopy(progress))


def material_ids(items: list[dict]) -> set[str]:
    """Original IDs, including originals carried by extraction notes."""
    result = set()
    for item in items:
        values = list(item.get("sources") or [])
        if item.get("role") != "extract":
            values.append(item.get("source", ""))
        for value in values:
            if isinstance(value, str) and value.partition(":")[0] in MODULES:
                result.add(value)
    return result


def material_approved(root: Path, items: list[dict]) -> bool:
    """Recheck retained material before a model turn or native-task replay."""
    originals = []
    for item in items:
        if item.get("role") == "original_evidence" and item.get("file"):
            path = Path(item["file"]).resolve()
            if not path.is_relative_to((root / ".state").resolve()):
                raise RemError("Original evidence must be retained inside this notebook")
            originals.extend(read_json(path, []))
    return all(cited(root, source_id) is not None for source_id in material_ids([*items, *originals]))


def require_material(root: Path, items: list[dict]) -> None:
    if not material_approved(root, items):
        raise RemError("Saved source material is no longer approved or available; "
                       "run co rem start and prepare a new task")


def task_material(root: Path, task: dict) -> None:
    """Validate persisted task material before offering or accepting a native task."""
    directory = Path(task["directory"])
    items = read_json(directory / "material.json", [])
    payload = task.get("task", {})
    items = [*items, *task.get("items", []), *task.get("prior_items", []),
             *payload.get("items", []), *payload.get("prior_items", [])]
    require_material(root, items)


def version_context(root: Path, source_id: str) -> dict | None:
    """Migrate registered sources; retain explicit legacy callbacks for other kinds."""
    if source_id.partition(":")[0] in MODULES:
        return cited(root, source_id)
    return source_versions.cited(root, source_id)


def guard_turn(root: Path, items: list[dict], execute):
    """Recheck retained evidence before every retry or follow-up model call."""
    def guarded(*args, **kwargs):
        require_material(root, items)
        return execute(*args, **kwargs)
    return guarded
