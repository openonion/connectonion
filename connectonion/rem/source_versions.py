"""Sources whose citations name one saved version of a record that keeps changing.

A task tracker re-saves a task each time it changes, so a page can cite
version 3 of a task while version 5 is the newest on disk. Two generic places
must know which saved version a source id is, without knowing the source:

- the reader and the claim audit show the excerpt of the version cited, not
  the newest one (`cited`);
- page review lets a rewrite replace a cited version with another version of
  the same record, instead of reporting the old id as dropped evidence
  (`superseded`). A version that is replaced by nothing is still a loss.

`record(source)` names the record a version id belongs to and `snapshot(root,
source)` returns exactly that saved version. Both work offline. New source
hooks supply a notebook-scoped resolver; no lookup imports every provider.
The explicit callback registry remains for existing callers while the REM
stages migrate. A scoped resolver never falls back to that global registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Kind:
    record: Callable[[str], str | None]
    snapshot: Callable[[Path, str], dict | None]


KINDS: dict[str, Kind] = {}
Resolver = Callable[[str], Kind | None]


def register(prefix: str, *, record: Callable[[str], str | None],
             snapshot: Callable[[Path, str], dict | None]) -> None:
    """Make `prefix:` source ids versioned. Registering a prefix again replaces it."""
    KINDS[prefix] = Kind(record, snapshot)


def _kind(source: str, resolve: Resolver | None) -> Kind | None:
    prefix, separator, _ = source.partition(":")
    if not separator:
        return None
    return resolve(prefix) if resolve is not None else KINDS.get(prefix)


def record_of(source: str, *, resolve: Resolver | None = None) -> str | None:
    """The record a version id belongs to, or None for any other source id."""
    kind = _kind(source, resolve)
    return kind.record(source) if kind else None


def cited(root: Path, source: str, *, resolve: Resolver | None = None) -> dict | None:
    """The saved excerpt of exactly the cited version, or None."""
    kind = _kind(source, resolve)
    return kind.snapshot(root, source) if kind else None


def _record_key(source: str, resolve: Resolver | None) -> tuple[str, str] | None:
    identity = record_of(source, resolve=resolve)
    return (source.partition(":")[0], identity) if identity is not None else None


def superseded(before: set[str], after: set[str], *, resolve: Resolver | None = None) -> set[str]:
    """Ids in `before` that `after` replaced with another version of the same record."""
    replacements = {_record_key(source, resolve) for source in after - before} - {None}
    return {source for source in before - after if _record_key(source, resolve) in replacements}
