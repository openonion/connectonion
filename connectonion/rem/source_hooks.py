"""Proposed selected-source boundary for #3040; not yet wired into REM stages.

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

from .files import RemError, read_json, state_path
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
    def fetch(self, root: Path, subscription: dict) -> dict: ...
    def collect(self, root: Path, subscription: dict, progress: dict,
                max_items: int, max_chars: int) -> Batch: ...
    def gather(self, root: Path, subscription: dict, handles: list[str], *,
               start: datetime, record: str) -> tuple[list[dict], list[str]]: ...
    def record_of(self, source_id: str) -> str | None: ...
    def cited(self, root: Path, subscription: dict, source_id: str) -> dict | None: ...


# One registration per kind, in code (never an import path from notebook JSON).
# Provider migrations add their entries here after the contract is agreed.
MODULES: dict[str, str] = {}


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
    if subscription is None or not subscription.get("consented"):
        raise RemError("Source is disabled or not yet authorized; run start to confirm access")
    return subscription


def statuses(root: Path) -> dict[str, dict]:
    """Selected source metadata only, including sources awaiting consent."""
    return {name: _load(sub).status(sub) for name, sub in selected(root).items()}


def consent_lines(root: Path) -> dict[str, str]:
    """Describe selection before reading it; this does not grant consent."""
    return {name: _load(sub).consent(sub) for name, sub in selected(root).items()}


def fetch(root: Path) -> dict[str, dict]:
    """Acquire snapshots before the caller takes its long-lived notebook lock.

    A local source may scan selected files; a remote source may call its API.
    Each adapter owns short storage transactions/locks and scope revalidation.
    An expected failure is explicit and does not stop other selected sources.
    """
    results = {}
    for name, sub in selected(root).items():
        if not sub.get("consented"):
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
    sub = _approved(root, name)
    return _load(sub).collect(root, sub, deepcopy(progress), max_items, max_chars)


def gather(root: Path, handles: list[str], *, start: datetime, record: str
           ) -> tuple[list[dict], list[str]]:
    """Search approved saved selections; unselected sources add no coverage."""
    items, coverage = [], []
    for name, sub in selected(root).items():
        if not sub.get("consented"):
            continue
        sub = _approved(root, name)
        found, lines = _load(sub).gather(root, sub, list(handles), start=start, record=record)
        items.extend(found)
        coverage.extend(lines)
    return items, coverage


def _version_kind(root: Path, prefix: str) -> source_versions.Kind | None:
    matches = [(name, sub) for name, sub in selected(root).items()
               if sub["kind"] == prefix and sub.get("consented")]
    if not matches:
        return None
    provider = _load(matches[0][1])

    def snapshot(notebook: Path, source_id: str) -> dict | None:
        for name, _ in matches:
            sub = selected(notebook).get(name)
            if sub is None or sub["kind"] != prefix or not sub.get("consented"):
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
