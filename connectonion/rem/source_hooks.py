"""Shared selected-source lifecycle for #3040.

Register module paths, never imported provider objects. Each operation reads
current saved selections before loading a module. Imports and metadata hooks
must not open source storage, decrypt credentials or use the network.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import importlib
from pathlib import Path
from hashlib import sha256
import json
from typing import Protocol, TYPE_CHECKING, cast

from .source_citations import read_operation
from .files import RemError, material_lock, read_json, state_path, write_json
from . import source_versions

if TYPE_CHECKING:
    from .source import Batch


class Source(Protocol):
    """A module of functions; acquisition and offline consumption are separate.

    Subscription is the current saved selection, not a credential container.
    Offline hooks read atomically published snapshots under the notebook lock;
    they must never wait for an acquisition/storage writer lock. Fetch owns
    that writer lock and uses acquisition_guard only for final publication.
    Data methods revalidate scope at the storage boundary. collect returns
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
               start: datetime, record: str, end: datetime | None = None,
               owner: bool = False, max_items: int = 100, max_chars: int = 100_000) -> tuple[list[dict], list[str]]: ...
    def record_of(self, source_id: str) -> str | None: ...
    def cited(self, root: Path, subscription: dict, source_id: str) -> dict | None: ...


# Source-owned migrations add one registration here. Never load import paths
# from notebook configuration. This prerequisite deliberately ships no providers.
MODULES: dict[str, str] = {}


class SourceUnavailable(RemError):
    """An expected acquisition failure with a safe explanation, no secrets/body.

    Adapters translate only expected service/file availability errors to this
    type. Account/scope/integrity failures set allow_saved=False and remain
    blocked until successful acquisition. Programming errors propagate.
    """

    def __init__(self, message: str, *, allow_saved: bool = True):
        super().__init__(message)
        self.allow_saved = allow_saved


class SourceBudgetExceeded(RemError):
    """The remaining budget cannot hold even one explicitly clipped item."""


def fit_item(item: dict, max_chars: int) -> dict:
    from .source import _fit
    try:
        return _fit(item, max_chars)
    except RemError as error:
        raise SourceBudgetExceeded(str(error)) from error


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
    if module.skill != f"rem-source-{kind}":
        raise RemError("Source skill must use the registered kind name")
    return module


def _approved(root: Path, name: str) -> dict:
    subscription = selected(root).get(name)
    if subscription is None or not approved(root, name, subscription):
        raise RemError("Source is disabled or not yet authorized; run start to confirm access")
    return subscription


def statuses(root: Path) -> dict[str, dict]:
    """Saved metadata only, also for disabled and awaiting-approval selections."""
    saved = read_json(state_path(root, "subscriptions.json"), {})
    selected(root)  # Validate before displaying any configured source.
    return {name: {"status": ("disabled" if not sub.get("enabled") or sub.get("unsubscribed")
                              else "approved" if approved(root, name, sub) else "awaiting approval")}
            for name, sub in saved.items() if sub.get("kind") in MODULES}


def consent_description(subscription: dict) -> str:
    """Stable before/after approval: show all saved non-secret selection fields."""
    return "Read saved selection: " + json.dumps(scope_value(subscription), ensure_ascii=False, sort_keys=True)


def consent_lines(root: Path) -> dict[str, str]:
    return {name: consent_description(sub) for name, sub in selected(root).items()}


def configure(root: Path, kind: str, **options) -> dict:
    """An explicit user operation; validate metadata, then save without approval.

    The adapter returns a selection, not a saved CLI result. This is the sole
    pre-approval import exception. It must not acquire source bodies.
    """
    if kind not in MODULES:
        raise RemError(f"Unknown registered source {kind!r}")
    before = read_json(state_path(root, "subscriptions.json"), {})
    subscription = _load({"kind": kind}).configure(root, **options)
    if not isinstance(subscription, dict) or subscription.get("kind") != kind:
        raise RemError("Source configuration did not return its registered kind")
    name = subscription.get("id", kind)
    saved = save_selection(root, subscription, enabled=subscription.get("enabled", True),
                           expected=before.get(name, {}))
    return {"subscription": kind, "enabled": saved["enabled"], "scope": scope_value(saved)}


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
            results[name] = {"ok": False, "error": str(error), "allow_saved": error.allow_saved}
        with material_lock(root):
            if not same_selection(root, name, sub):
                results[name] = {"ok": False, "allow_saved": False,
                                 "error": "Source selection changed during acquisition; run start again"}
                continue
            receipts = read_json(state_path(root, "source-acquisition.json"), {})
            previous = receipts.get(name, {})
            if (not results[name]["ok"] and previous.get("scope") == scope_value(sub)
                    and previous.get("allow_saved") is False):
                results[name]["allow_saved"] = False  # Only a successful retry clears an integrity/account block.
            receipts[name] = {**results[name], "scope": scope_value(sub)}
            write_json(state_path(root, "source-acquisition.json"), receipts)
    return results


def collect(root: Path, name: str, progress: dict, max_items: int, max_chars: int) -> Batch:
    """Consume saved material only; never mutate the caller's checkpoint.

    Caller owns the notebook transaction and persists Batch.progress only when
    the corresponding REM work is kept. Provider must honor both input limits.
    Offline reads must not acquire the writer lock used by fetch.
    """
    if type(max_items) is not int or type(max_chars) is not int or min(max_items, max_chars) <= 0:
        raise ValueError("Batch limits must be positive")
    with material_lock(root):
        sub = _approved(root, name)
        require_readable(root, name, sub)
        batch = _load(sub).collect(root, sub, deepcopy(progress), max_items, max_chars)
        if len(batch.items) > max_items or material_size(batch.items) > max_chars:
            raise RemError("Source exceeded the batch budget; progress was not committed")
        remember_material(root, name, sub, batch.items)
        return batch


def gather(root: Path, handles: list[str], *, start: datetime, record: str, names=None,
           end: datetime | None = None, owner: bool = False, max_items: int = 100,
           max_chars: int = 100_000) -> tuple[list[dict], list[str]]:
    """Offline search with one shared budget across the selected providers.

    Window is [start, end); providers explain their timestamp/identity meaning.
    No network acquisition, sync progress changes or unselected coverage lines.
    """
    if start.utcoffset() is None or (end is not None and (end.utcoffset() is None or end <= start)):
        raise ValueError("Investigation needs an aware, increasing time window")
    if type(max_items) is not int or type(max_chars) is not int or min(max_items, max_chars) <= 0:
        raise ValueError("Investigation limits must be positive")
    items, coverage = [], []
    for name, sub in selected(root).items():
        if (names is not None and name not in names) or not approved(root, name, sub):
            continue
        remaining_items, remaining_chars = max_items - len(items), max_chars - material_size(items)
        if min(remaining_items, remaining_chars) <= 0:
            coverage.append(f"{name}: shared investigation budget exhausted; not searched")
            continue
        with material_lock(root):
            sub = _approved(root, name)
            try:
                require_readable(root, name, sub)
            except SourceUnavailable as error:
                coverage.append(f"{name}: {error}; not searched")
                continue
            try:
                found, lines = _load(sub).gather(root, sub, list(handles), start=start, end=end,
                    record=record, owner=owner, max_items=remaining_items, max_chars=remaining_chars)
            except SourceBudgetExceeded:
                if not items:
                    raise
                coverage.append(f"{name}: remaining shared budget cannot hold another item; deferred")
                continue
            if len(found) > remaining_items or material_size(found) > remaining_chars:
                raise RemError("Source exceeded the investigation budget")
            remember_material(root, name, sub, found)
        items.extend(found)
        coverage.extend(lines)
        warning = stale_notice(root, name, sub)
        if warning:
            coverage.append(warning)
    return items, coverage


def _citation_owner(root: Path, target: str) -> tuple[str, dict] | None:
    from .source_citations import lookup
    entry = lookup(root, target)
    if entry:
        sub = selected(root).get(entry["subscription"])
        if sub and sub["kind"] == entry["kind"] and approved(root, entry["subscription"], sub):
            return entry["subscription"], sub
        return None
    prefix = target.partition(":")[0]
    # Only unique source-qualified prefixes can use the legacy route. Opaque
    # Reader paths need an explicit persisted owner, never provider probing.
    matches = [(name, sub) for name, sub in selected(root).items()
               if sub["kind"] == prefix and approved(root, name, sub)]
    return matches[0] if len(matches) == 1 else None


def record_key(root: Path, target: str) -> tuple[str, str] | None:
    owner = _citation_owner(root, target)
    if owner is None:
        return None
    _, sub = owner
    record = _load(sub).record_of(target)
    from .source_citations import lookup
    entry = lookup(root, target)
    if entry and record != entry["record"]:
        return None
    return (sub["kind"], record) if record else None


@read_operation
def record_of(root: Path, source_id: str) -> str | None:
    """Stable identity of an approved citation; no snapshot body reads."""
    key = record_key(root, source_id)
    return key[1] if key else None


@read_operation
def cited(root: Path, source_id: str) -> dict | None:
    """Resolve exact saved bytes under current scope, never fetch or use latest."""
    with material_lock(root):
        owner = _citation_owner(root, source_id)
        if owner is None:
            return None
        name, sub = owner
        try:
            require_readable(root, name, sub)
        except SourceUnavailable:
            return None
        if record_key(root, source_id) is None:
            return None
        return _load(sub).cited(root, sub, source_id)


@read_operation
def superseded(root: Path, before: set[str], after: set[str]) -> set[str]:
    """Same-record replacement, including rollback, without prefix collisions."""
    replacements = {record_key(root, target) for target in after - before} - {None}
    return {target for target in before - after if record_key(root, target) in replacements}


def remember_material(root: Path, name: str, sub: dict, items: list[dict]) -> None:
    """Validate ownership before retaining evidence; never advance consumption."""
    from .source_citations import remember
    provider = _load(sub)
    entries = {}
    for item in items:
        target = item.get("source", "")
        declared = item.get("source_kind", target.partition(":")[0])
        record = provider.record_of(target)
        if declared != sub["kind"] or not record or provider.cited(root, sub, target) is None:
            raise RemError("Source emitted an unresolved or foreign saved citation")
        entries[target] = {"kind": sub["kind"], "record": record, "subscription": name}
    if not same_selection(root, name, sub):
        raise RemError("Source selection changed while reading saved material")
    remember(root, entries)


def managed_target(root: Path, target: str) -> bool:
    from .source_citations import lookup
    return target.partition(":")[0] in {*MODULES, "adapter"} or lookup(root, target) is not None


def scope_value(subscription: dict) -> dict:
    """Stable configured scope in the existing consent summary, without runtime status."""
    ignored = {"id", "enabled", "consented", "unsubscribed", "adapter", "status"}
    return {key: value for key, value in subscription.items() if key not in ignored}


def same_selection(root: Path, name: str, expected: dict) -> bool:
    current = selected(root).get(name)
    return bool(current and scope_value(current) == scope_value(expected) and approved(root, name, current))


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
    """Saved counters only; no body reads, acquisition or progress writes."""
    with material_lock(root):
        sub = selected(root)[name]
        if not approved(root, name, sub):
            return {"count": None, "body_reads": False, "consented": False,
                    "note": "Run co rem start to approve this selection"}
        result = _load(sub).pending(root, sub, deepcopy(progress))
        count = result.get("count")
        if result.get("body_reads") is not False or (count is not None and (type(count) is not int or count < 0)):
            raise RemError("Source pending metadata must report a nonnegative or unknown body-free count")
        receipt = read_json(state_path(root, "source-acquisition.json"), {}).get(name, {})
        if receipt.get("scope") == scope_value(sub) and receipt.get("allow_saved") is False:
            result = {**result, "blocked": True, "note": "Saved material blocked; a successful sync is required"}
        return result


def material_ids(items: list[dict], *, root: Path | None = None) -> set[str]:
    """Original IDs, including originals carried by extraction notes."""
    result = set()
    for item in items:
        values = list(item.get("sources") or [])
        if item.get("role") != "extract":
            values.append(item.get("source", ""))
        for value in values:
            if isinstance(value, str) and (value.partition(":")[0] in {*MODULES, "adapter"}
                    or item.get("source_kind") or (root is not None and managed_target(root, value))):
                result.add(value)
    return result


@read_operation
def material_approved(root: Path, items: list[dict]) -> bool:
    """Recheck retained material before a model turn or native-task replay."""
    originals = []
    for item in items:
        if item.get("role") == "original_evidence" and item.get("file"):
            path = Path(item["file"]).resolve()
            if not path.is_relative_to((root / ".state").resolve()):
                raise RemError("Original evidence must be retained inside this notebook")
            originals.extend(read_json(path, []))
    return all(cited(root, source_id) is not None for source_id in material_ids([*items, *originals], root=root))


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
    if managed_target(root, source_id):
        return cited(root, source_id)
    return source_versions.cited(root, source_id)


def guard_turn(root: Path, items: list[dict], execute):
    """Recheck retained evidence before every retry or follow-up model call."""
    def guarded(*args, **kwargs):
        require_material(root, items)
        return execute(*args, **kwargs)
    return guarded


def require_readable(root: Path, name: str, sub: dict) -> None:
    """Keep account/scope/integrity failures blocked until a successful retry."""
    receipt = read_json(state_path(root, "source-acquisition.json"), {}).get(name, {})
    if (receipt.get("scope") == scope_value(sub) and receipt.get("ok") is False
            and receipt.get("allow_saved") is False):
        raise SourceUnavailable("Saved source access blocked after acquisition failure; retry sync",
                                allow_saved=False)


def acquisition_guard(root: Path, expected: dict, *, name: str | None = None):
    """Short transaction held by adapters while committing acquired snapshots."""
    from contextlib import contextmanager

    @contextmanager
    def guard():
        with material_lock(root):
            selected_name = name or expected.get("id", expected["kind"])
            if not same_selection(root, selected_name, expected):
                raise SourceUnavailable("Source selection changed during acquisition", allow_saved=False)
            yield
    return guard


def reject_options(options: dict) -> None:
    unsupported = [key.replace("_", "-") for key, value in options.items() if value]
    if unsupported:
        raise RemError("Unsupported source option(s): " + ", ".join("--" + key for key in unsupported))


def save_selection(root: Path, subscription: dict, *, enabled: bool = True,
                   expected: dict | None = None) -> dict:
    """Save source-owned metadata; any changed scope needs fresh consent."""
    if type(enabled) is not bool:
        raise RemError("Source configuration enabled flag must be a boolean")
    name = subscription.get("id", subscription["kind"])
    with material_lock(root):
        saved = read_json(state_path(root, "subscriptions.json"), {})
        previous = saved.get(name, {})
        if expected is not None and previous != expected:
            raise RemError("Source configuration changed while validating; inspect sources and retry")
        same = scope_value(previous) == scope_value(subscription)
        subscription = {**subscription, "id": name, "enabled": enabled, "unsubscribed": not enabled,
                        "consented": bool(enabled and same and approved(root, name, previous))}
        saved[name] = subscription
        write_json(state_path(root, "subscriptions.json"), saved)
    return subscription


def scoped_progress(subscription: dict, progress: dict) -> tuple[str, dict]:
    if not isinstance(progress, dict):
        raise RemError("Invalid source progress; preserve it for diagnosis")
    scope = sha256(json.dumps(scope_value(subscription), sort_keys=True).encode()).hexdigest()
    return scope, deepcopy(progress) if progress.get("scope") == scope else {}


def material_size(items: list[dict]) -> int:
    return sum(len(json.dumps(item, ensure_ascii=False)) for item in items)


def bounded(items, max_items: int, max_chars: int) -> tuple[list[dict], bool]:
    """A first oversized item is explicitly truncated; later items are deferred."""
    result, used, limited = [], 0, False
    for item in items:
        if len(result) == max_items or result and used + material_size([item]) > max_chars:
            limited = True
            break
        fitted = fit_item(item, max_chars) if not result else item
        limited = limited or fitted != item
        result.append(fitted)
        used += material_size([fitted])
    return result, limited


def stale_notice(root: Path, name: str, sub: dict) -> str:
    receipt = read_json(state_path(root, "source-acquisition.json"), {}).get(name, {})
    if receipt.get("scope") == scope_value(sub) and receipt.get("ok") is False and receipt.get("allow_saved"):
        return f"{name}: acquisition failed; using previously saved approved material (may be stale)"
    return ""


def material_kinds(items: list[dict]) -> set[str]:
    """Source skill selection is independent of an opaque Reader target prefix."""
    return {item.get("source_kind") or item.get("source", "").partition(":")[0]
            for item in items if item.get("role") != "extract"} & MODULES.keys()


def canonical_sources(text: str) -> str:
    """Normalize Markdown wrappers only; opaque targets still need resolution."""
    from .source_citations import canonical_sources as normalize
    return normalize(text, prefixes={*MODULES, *source_versions.KINDS, "adapter"})
