"""Incremental filenames and single live notes for the Obsidian source CLI.

Reads only an already validated scope. No registry, cache, cursor, saved body,
network call or REM dependency. A note ID identifies its vault and relative path,
not a version; the caller must supply the authorized folders on every read.
"""

import os
import re
import stat
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import quote, unquote

import yaml

from . import obsidian as api

CHANGES_HELP = "co obsidian changes --help"
SHOW_HELP = "co obsidian show --help"


def read_window(value: str) -> tuple[datetime, datetime]:
    """Capture the upper bound before touching the source; reject bad cursors."""
    until = datetime.now(timezone.utc)
    try:
        since = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("--since must be an ISO date and time with a timezone.") from None
    if since.tzinfo is None or since.utcoffset() is None:
        raise ValueError("--since needs a timezone, such as 2026-11-20T00:00:00Z.")
    if since > until:
        raise ValueError("--since cannot be in the future. Check the time and timezone.")
    return since, until


def _time_ns(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000


def _iso_time(nanoseconds: int) -> str:
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    second = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{second}.{fraction:09d}+00:00"


def _note_id(scope: api._Scope, key: str) -> str:
    vault = sha256(os.fsencode(scope.vault_path)).hexdigest()
    return f"{vault}:{quote(key, safe='/')}"


def _id_path(scope: api._Scope, identifier: str) -> str:
    """Decode one canonical ID; an ID never widens the supplied scope."""
    vault, separator, encoded = identifier.partition(":")
    if not separator or vault != sha256(os.fsencode(scope.vault_path)).hexdigest():
        raise ValueError("Use a note ID from changes for this vault, without the obsidian: citation prefix.")
    try:
        key = unquote(encoded, errors="strict")
    except UnicodeError:
        raise ValueError("The note ID contains invalid text. Copy it from changes again.") from None
    if not key or quote(key, safe='/') != encoded:
        raise ValueError("The note ID is malformed. Copy it from changes again.")
    if key != PurePosixPath(key).as_posix():
        raise ValueError("The note ID path is malformed. Copy it from changes again.")
    return api._resolve_note_path(scope, key)


def _modified_ns(scope: api._Scope, key: str) -> int:
    """Check the filename through pinned directories without opening its body."""
    path = scope.vault_path / api._resolve_note_path(scope, key)
    with api._open_directory(path.parent) as parent:
        info = os.stat(path.name if parent is not None else path, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("The note changed while checking it")
    return info.st_mtime_ns


def _item(scope: api._Scope, key: str, modified_ns: int) -> dict:
    path = PurePosixPath(key)
    return {"id": _note_id(scope, key), "title": path.stem,
            "time": _iso_time(modified_ns), "path": key, "folder": path.parent.as_posix(),
            "link": "obsidian://open?path=" + quote(str(scope.vault_path / key), safe="")}


def changes(scope: api._Scope, since: datetime, until: datetime) -> dict:
    """List metadata in an inclusive time window, oldest first; all or error."""
    lower, upper = _time_ns(since), _time_ns(until)
    changed = []
    for key in api._build_scope_index(scope).paths:
        if PurePosixPath(key).suffix.lower() != ".md":
            continue
        try:
            modified = _modified_ns(scope, key)
        except (OSError, ValueError, api.ObsidianError) as error:
            raise api.ObsidianError(f"Cannot check note {key!r}; list changes again after checking access.",
                                    CHANGES_HELP) from error
        if lower <= modified <= upper:
            changed.append((modified, key))
    return {"since": since.isoformat(), "until": until.isoformat(),
            "items": [_item(scope, key, stamp) for stamp, key in sorted(changed)]}


def show(scope: api._Scope, identifier: str) -> dict:
    """Read one live note by stable ID or scoped relative path, without a cache."""
    if re.match(r"^[a-f0-9]{64}:", identifier):
        key = _id_path(scope, identifier)
    elif identifier.startswith("obsidian:"):
        raise ValueError("Remove the initial obsidian: from the citation before calling show.")
    else:
        key = api._resolve_note_path(scope, identifier)
    try:
        content, modified = api._read_markdown(scope, scope.vault_path / key)
        note = api._parse_markdown(content, key, modified)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, RecursionError) as error:
        raise api.ObsidianError(f"Cannot read note {key!r}; check its access and Markdown properties.",
                                SHOW_HELP) from error
    author = note["frontmatter"].get("author")
    return {**_item(scope, key, modified), "text": content,
            "author": author if isinstance(author, str) and author.strip() else None,
            "properties": note["frontmatter"], "tags": note["tags"], "links": note["links"]}
