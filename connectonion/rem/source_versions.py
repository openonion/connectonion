"""Sources whose citations name one saved version of a record that keeps changing.

A task tracker re-saves a task each time it changes, so a page can cite
version 3 of a task while version 5 is the newest on disk. Two generic places
must know which saved version a source id is, without knowing the source:

- the reader and the claim audit show the excerpt of the version cited, not
  the newest one (`cited`);
- page review lets a rewrite replace a cited version with a newer version of
  the same record, instead of reporting the old id as dropped evidence
  (`superseded`). A version that is replaced by nothing is still a loss.

A source kind registers itself once, with `register(prefix, record=..., snapshot=...)`:
`record(source)` names the record a version id belongs to (None when the id is
not one of this kind's versions) and `snapshot(root, source)` returns the
local excerpt of exactly that version, or None when it cannot be shown. Both
must work offline and never decrypt a credential. A source module registers
when it is imported and names itself in PROVIDERS, so the reader finds it
without generic code importing any one source.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Kind:
    record: Callable[[str], str | None]
    snapshot: Callable[[Path, str], dict | None]


KINDS: dict[str, Kind] = {}
# Modules that call `register` when imported; loaded on the first lookup.
PROVIDERS: tuple[str, ...] = ()
_loaded: list[str] = []


def register(prefix: str, *, record: Callable[[str], str | None],
             snapshot: Callable[[Path, str], dict | None]) -> None:
    """Make `prefix:` source ids versioned. Registering a prefix again replaces it."""
    KINDS[prefix] = Kind(record, snapshot)


def _kind(source: str) -> Kind | None:
    for name in PROVIDERS:
        if name not in _loaded:
            _loaded.append(name)
            importlib.import_module(name)
    return KINDS.get(source.partition(":")[0]) if ":" in source else None


def record_of(source: str) -> str | None:
    """The record a version id belongs to, or None for any other source id."""
    kind = _kind(source)
    return kind.record(source) if kind else None


def cited(root: Path, source: str) -> dict | None:
    """The saved excerpt of exactly the cited version, or None."""
    kind = _kind(source)
    return kind.snapshot(root, source) if kind else None


def superseded(before: set[str], after: set[str]) -> set[str]:
    """Ids in `before` that `after` replaced with another version of the same record."""
    newer = {record_of(source) for source in after - before} - {None}
    return {source for source in before - after if record_of(source) in newer}
