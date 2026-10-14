"""
Purpose: Discover Obsidian's registered vaults and validate an explicit folder scope
LLM-Note:
  Dependencies: imports from [json, os, sys, pathlib, dataclasses, typing] | imported by [cli/commands/obsidian_commands.py]
  Data flow: current platform → obsidian.json → registered paths → sorted vault records; explicit vault and folders → validated scope
  State/Effects: reads the registry and directory metadata only; no scanning, Markdown reads, imports or writes
  Errors: ObsidianError for unreadable or malformed registry and unavailable directories; ValueError for unsafe or missing folder selections
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

HELP = "co obsidian vaults --help"
EXCLUDED_DIRS = frozenset({".obsidian", ".trash", ".git"})


class ObsidianError(Exception):
    """What went wrong, the next command, and any files a later read could not load."""

    def __init__(self, message: str, next_step: str, *, failed_paths=None):
        super().__init__(message)
        self.next_step = next_step
        self.failed_paths = failed_paths


@dataclass(frozen=True)
class _Scope:
    """Canonical roots for later readers, which must also skip excluded dirs and symlinks."""

    vault_path: Path
    folders: tuple[Path, ...]
    excluded_dirs: frozenset[str] = EXCLUDED_DIRS
    follow_symlinks: bool = False


def _registry_path() -> Path:
    """Only the native registry for this platform; discovery never searches the disk."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/obsidian/obsidian.json"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config/obsidian/obsidian.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata or not appdata.strip():
            raise ObsidianError("APPDATA is missing; cannot locate the Obsidian registry.", HELP)
        return Path(appdata) / "obsidian/obsidian.json"
    raise ObsidianError("Obsidian vault discovery supports macOS, Linux and Windows.", HELP)


def _registry_entries(data) -> list[dict]:
    """Unknown fields are harmless; paths and an optional boolean open flag must be usable."""
    if not isinstance(data, dict) or not isinstance(data.get("vaults", {}), dict):
        raise ObsidianError("The Obsidian registry must contain a vaults object.", HELP)
    entries = list(data.get("vaults", {}).values())
    for entry in entries:
        if not isinstance(entry, dict):
            raise ObsidianError("The Obsidian registry contains an invalid vault entry.", HELP)
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ObsidianError("A registered Obsidian vault has no valid path.", HELP)
        if not Path(path).is_absolute():
            raise ObsidianError("Registered Obsidian vault paths must be absolute.", HELP)
        if "open" in entry and not isinstance(entry["open"], bool):
            raise ObsidianError("A registered Obsidian vault has an invalid open flag.", HELP)
    return entries


def _read_vault_registry(registry_path: Path) -> list[dict]:
    """Missing registration is an empty result; a damaged file is never an empty success."""
    try:
        content = registry_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except UnicodeError:
        raise ObsidianError("The Obsidian registry is not valid UTF-8.", HELP) from None
    except OSError:
        raise ObsidianError("Cannot read the Obsidian registry. Check its permissions.", HELP) from None
    try:
        data = json.loads(content)
    except ValueError:
        raise ObsidianError("The Obsidian registry is not valid JSON.", HELP) from None
    return _registry_entries(data)


def discover_vaults() -> list[dict]:
    """Registered vaults only, including stale paths; no note contents are opened."""
    vaults = {}
    for entry in _read_vault_registry(_registry_path()):
        path = Path(entry["path"]).expanduser()
        try:
            path = path.resolve()
            available = path.is_dir()
        except (OSError, RuntimeError):
            path = Path(os.path.abspath(path))
            available = False
        # normcase uses the native Windows path rules; POSIX paths retain their case.
        key = os.path.normcase(str(path))
        if key in vaults:
            vaults[key]["open"] |= entry.get("open", False)
        else:
            vaults[key] = {"name": path.name or str(path), "path": str(path),
                           "available": available, "open": entry.get("open", False)}
    return sorted(vaults.values(), key=lambda v: (v["name"], v["path"]))


def _directory(path: Path) -> Path:
    """Require a readable directory, without opening any of its children."""
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_dir():
            raise ObsidianError("The selected Obsidian scope must be a directory.", HELP)
        if not os.access(resolved, os.R_OK | os.X_OK):
            raise ObsidianError("Cannot read the selected Obsidian directory.", HELP)
    except (OSError, RuntimeError):
        raise ObsidianError("The selected Obsidian directory is missing or unreadable.", HELP) from None
    return resolved


def _scope_folder(vault: Path, folder: str) -> Path:
    """Refuse excluded directories and every selected symlink, including links within the vault."""
    if not isinstance(folder, str) or not folder.strip() or "\x00" in folder:
        raise ValueError("Choose a non-empty vault-relative folder.")
    relative = Path(folder)
    if relative.root or relative.drive or ".." in relative.parts:
        raise ValueError("Folders must be vault-relative, without '..' traversal.")
    excluded = {os.path.normcase(name) for name in EXCLUDED_DIRS}
    current = vault
    for part in relative.parts:
        if os.path.normcase(part) in excluded:
            raise ValueError("The .obsidian, .trash and .git directories are always excluded.")
        current = current / part
        if current.is_symlink():
            raise ValueError("Obsidian folder scopes cannot follow symlinks.")
    selected = _directory(current)
    if not selected.is_relative_to(vault):
        raise ValueError("The selected folder must remain inside the vault.")
    return selected


def _validate_scope(vault_path: Path, folders: Sequence[str]) -> _Scope:
    """Validate all selections before removing overlap; '.' still carries the system exclusions."""
    if vault_path is None or not str(vault_path).strip():
        raise ValueError("Choose an explicit Obsidian vault path.")
    if not folders or isinstance(folders, (str, bytes)):
        raise ValueError("Choose folders explicitly; use '.' for the whole vault.")
    vault_path = Path(vault_path).expanduser()
    if vault_path.is_symlink():
        raise ValueError("Obsidian folder scopes cannot follow a symlink vault.")
    vault = _directory(vault_path)
    selected = {_scope_folder(vault, folder) for folder in folders}
    roots = []
    for path in sorted(selected, key=lambda p: (len(p.parts), str(p))):
        if not any(path.is_relative_to(root) for root in roots):
            roots.append(path)
    return _Scope(vault, tuple(roots))
