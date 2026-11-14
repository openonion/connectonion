"""
Purpose: Discover registered Obsidian vaults and read or search an explicit note scope
LLM-Note:
  Dependencies: imports from [json, os, sys, pathlib, dataclasses, typing, yaml, _attachment_files] | imported by [cli/commands/obsidian_commands.py]
  Data flow: registry → vault records; explicit folders → filename index → selected Markdown → parsed notes, links and backlinks → list/read/search
  State/Effects: discovery reads registry and path metadata only; note operations read selected UTF-8 files and index vault filenames; never writes to the vault
  Errors: ObsidianError for unavailable registry/directories or an incomplete note load; ValueError for unsafe scope, note paths or queries
"""

import json
import os
import posixpath
import re
import shlex
import stat
import sys
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Sequence
from urllib.parse import unquote

import yaml

from ._attachment_files import path_of_open_file

HELP = "co obsidian vaults --help"
EXCLUDED_DIRS = frozenset({".obsidian", ".trash", ".git"})


class ObsidianError(Exception):
    """What went wrong, the next command, and any selected files that could not load."""

    def __init__(self, message: str, next_step: str, *, failed_paths=None):
        super().__init__(message)
        self.next_step = next_step
        self.failed_paths = failed_paths


@dataclass(frozen=True)
class _Scope:
    """Canonical roots; readers must still skip excluded directories and symlinks."""

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


# -- scope reads ----------------------------------------------------------

@dataclass(frozen=True)
class _VaultIndex:
    """Relative filenames only; resolving a link never opens its target."""

    paths: tuple[str, ...]

    @cached_property
    def by_path(self) -> dict[str, list[str]]:
        matches = {}
        for path in self.paths:
            matches.setdefault(os.path.normcase(path), []).append(path)
        return matches

    @cached_property
    def by_name(self) -> dict[str, list[str]]:
        matches = {}
        for path in self.paths:
            matches.setdefault(os.path.normcase(PurePosixPath(path).name), []).append(path)
        return matches


def _in_scope(scope: _Scope, path: Path) -> bool:
    return any(path.is_relative_to(root) for root in scope.folders)


@contextmanager
def _open_directory(path: Path):
    """Pin every directory component on POSIX, without following a replaced symlink."""
    if os.open not in os.supports_dir_fd:
        if path.is_symlink() or path.resolve(strict=True) != path:
            raise OSError("The directory changed while reading it")
        yield None
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _walk_files(path: Path, descriptor=None):
    """Enumerate filenames once, skipping system directories and all symlinks."""
    excluded = {os.path.normcase(name) for name in EXCLUDED_DIRS}
    with os.scandir(descriptor if descriptor is not None else path) as entries:
        for entry in entries:
            if entry.is_symlink():
                continue
            child = path / entry.name
            if entry.is_dir(follow_symlinks=False):
                if os.path.normcase(entry.name) in excluded:
                    continue
                if descriptor is None:
                    with _open_directory(child) as handle:
                        yield from _walk_files(child, handle)
                else:
                    handle = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=descriptor)
                    try:
                        yield from _walk_files(child, handle)
                    finally:
                        os.close(handle)
            elif entry.is_file(follow_symlinks=False):
                yield child


def _build_vault_index(vault_path: Path) -> _VaultIndex:
    """Index the whole vault's filenames, including attachments, without reading bodies."""
    try:
        with _open_directory(vault_path) as descriptor:
            paths = tuple(sorted(path.relative_to(vault_path).as_posix()
                                 for path in _walk_files(vault_path, descriptor)))
    except (OSError, RuntimeError):
        raise ObsidianError("Cannot complete the Obsidian filename index. Check directory access.", HELP) from None
    return _VaultIndex(paths)


def _scan_markdown(scope: _Scope, *, index: _VaultIndex | None = None) -> list[Path]:
    """Reuse the filename pass when loading notes; never scan selected folders twice."""
    if index is not None:
        return [scope.vault_path / path for path in index.paths
                if PurePosixPath(path).suffix.lower() == ".md"
                and _in_scope(scope, scope.vault_path / path)]
    try:
        paths = set()
        for folder in scope.folders:
            with _open_directory(folder) as descriptor:
                paths.update(path for path in _walk_files(folder, descriptor) if path.suffix.lower() == ".md")
        return sorted(paths, key=lambda path: path.relative_to(scope.vault_path).as_posix())
    except (OSError, RuntimeError):
        raise ObsidianError("Cannot complete the selected Obsidian scope scan.", HELP) from None


def _resolve_note_path(scope: _Scope, note_path: str) -> str:
    """Refuse unsafe paths before loading any note in the selected scope."""
    if not isinstance(note_path, str) or not note_path.strip() or "\x00" in note_path:
        raise ValueError("Choose a non-empty vault-relative Markdown path.")
    relative = PurePosixPath(note_path)
    native = Path(note_path)
    if "\\" in note_path:
        raise ValueError("Use forward slashes in vault-relative note paths.")
    if relative.is_absolute() or native.root or native.drive or ".." in relative.parts or ".." in native.parts:
        raise ValueError("Note paths must be vault-relative, without '..' traversal.")
    if relative.suffix.lower() != ".md":
        raise ValueError("Choose a Markdown (.md) note.")
    current = scope.vault_path
    excluded = {os.path.normcase(name) for name in scope.excluded_dirs}
    for part in relative.parts:
        if os.path.normcase(part) in excluded:
            raise ValueError("The .obsidian, .trash and .git directories are always excluded.")
        current = current / part
        if current.is_symlink():
            raise ValueError("Obsidian note reads cannot follow symlinks.")
    if not _in_scope(scope, current):
        raise ValueError("The requested note is outside the selected folders.")
    try:
        if current.resolve(strict=True) != current or not current.is_file():
            raise OSError
    except (OSError, RuntimeError):
        raise ObsidianError(f"Cannot find or read note {relative.as_posix()!r}.", HELP) from None
    return relative.as_posix()


def _read_markdown(scope: _Scope, path: Path) -> tuple[str, int]:
    """Authorize the open handle before reading; keep UTF-8 content and newline bytes intact."""
    key = _resolve_note_path(scope, path.relative_to(scope.vault_path).as_posix())
    path = scope.vault_path / key
    with _open_directory(path.parent) as parent:
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_BINARY", 0))
        descriptor = os.open(path.name if parent is not None else path, flags, dir_fd=parent)
        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or path_of_open_file(stream) != path:
                raise OSError("The note changed location while opening it")
            content = stream.read()
            after = os.fstat(stream.fileno())
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise OSError("The note changed while reading it")
    return content, before.st_mtime_ns


# -- Markdown -------------------------------------------------------------

def _yaml_value(value, ancestors=frozenset()):
    """Convert safe YAML dates to ISO strings and refuse non-JSON or recursive values."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        json.dumps(value, allow_nan=False)
        return value
    if id(value) in ancestors:
        raise ValueError("Recursive YAML properties are not supported")
    parents = ancestors | {id(value)}
    if isinstance(value, list):
        return [_yaml_value(item, parents) for item in value]
    if isinstance(value, dict):
        return {str(_yaml_value(key, parents)): _yaml_value(item, parents) for key, item in value.items()}
    raise ValueError("YAML properties must contain JSON-compatible values")


def _frontmatter(content: str) -> tuple[dict, int]:
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").rstrip("\r\n \t") != "---":
        return {}, 0
    for end in range(1, len(lines)):
        if lines[end].rstrip("\r\n \t") in {"---", "..."}:
            data = yaml.safe_load("".join(lines[1:end]))
            if data is not None and not isinstance(data, dict):
                raise ValueError("Frontmatter must be a YAML mapping")
            return _yaml_value(data or {}), sum(len(line) for line in lines[:end + 1])
    raise ValueError("Frontmatter has no closing delimiter")


def _without_code(body: str) -> str:
    """Blank code while preserving offsets, so extracted links retain their original raw text."""
    lines, fence = [], None
    for line in body.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        in_code = fence is not None or line.startswith(("    ", "\t"))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
            in_code = True
        lines.append(re.sub(r"[^\r\n]", " ", line) if in_code else line)
    text = "".join(lines)
    return re.sub(r"(`+)(?!`)(.*?)(?<!`)\1(?!`)",
                  lambda match: re.sub(r"[^\r\n]", " ", match[0]), text, flags=re.S)


def _extract_tags(content: str, body_offset: int, frontmatter: dict) -> list[str]:
    """Properties first, then body tags; preserve the first spelling of each tag."""
    candidates = []
    for field in ("tags", "tag"):
        value = frontmatter.get(field, [])
        if isinstance(value, str):
            value = re.split(r"[\s,]+", value.strip())
        if isinstance(value, list):
            candidates.extend(item.lstrip("#") for item in value if isinstance(item, str) and item.lstrip("#"))
    body = _without_code(content[body_offset:])
    body = re.sub(r"(?:[a-zA-Z][\w+.-]*://|mailto:|www\.)[^\s<>]+", " ", body)
    body = re.sub(r"(?m)^ {0,3}#{1,6}(?:[ \t]+|$)[^\r\n]*", "", body)
    body = re.sub(r"!?\[\[[^\]\r\n]*\]\]|!?\[[^\]\r\n]*\]\([^\r\n]*?\)", " ", body)
    for match in re.finditer(r"(?<![\w/#\\])#([\w/\-\u0080-\U0010ffff]+)", body):
        characters = []
        for char in match[1]:
            if char not in "_-/" and unicodedata.category(char)[0] not in "LNMS":
                break
            characters.append(char)
        tag = "".join(characters).rstrip("/")
        if tag and not tag.isdecimal():
            candidates.append(tag)
    unique = {}
    for tag in candidates:
        unique.setdefault(tag.casefold(), tag)
    return list(unique.values())


def _closing(text: str, start: int, opening: str, closing: str) -> int | None:
    """Find a balanced Markdown label or destination, respecting escaped delimiters."""
    depth, index = 1, start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _extract_links(content: str, body_offset: int) -> list[dict]:
    """Keep wiki and inline Markdown links in source order, without expanding embeds."""
    raw_body = content[body_offset:]
    body = _without_code(raw_body)
    links, index = [], 0
    while index < len(body):
        start = index
        embedded = body[index:index + 2] == "!["
        if embedded:
            index += 1
        if body[index:index + 1] != "[" or (start and body[start - 1] == "\\"):
            index = start + 1
            continue
        if body[index:index + 2] == "[[":
            end = body.find("]]", index + 2)
            if end < 0 or "\n" in body[index:end]:
                index = start + 1
                continue
            target, separator, alias = raw_body[index + 2:end].partition("|")
            alias = alias if separator else None
            end += 2
        else:
            label = _closing(body, index, "[", "]")
            end = _closing(body, label + 1, "(", ")") if label is not None and body[label + 1:label + 2] == "(" else None
            if end is None:
                index = start + 1
                continue
            alias = raw_body[index + 1:label]
            destination = raw_body[label + 2:end].strip()
            match = re.fullmatch(r'<(.*?)>(?:\s+["\x27].*["\x27])?|(.+?)(?:\s+["\x27].*["\x27])?', destination, re.S)
            target = (match[1] if match[1] is not None else match[2]) if match else destination
            end += 1
        target, separator, anchor = target.partition("#")
        links.append({"raw": raw_body[start:end], "target": target, "alias": alias,
                      "anchor": anchor if separator else None, "embedded": embedded,
                      "target_kind": "note", "resolved_path": None, "resolution": "unresolved"})
        index = end
    return links


def _parse_markdown(content: str, relative_path: str, mtime_ns: int) -> dict:
    """The filename is the title; full source content is returned only once."""
    frontmatter, offset = _frontmatter(content)
    return {"note_key": relative_path, "path": relative_path,
            "title": PurePosixPath(relative_path).stem, "content": content, "body_offset": offset,
            "frontmatter": frontmatter, "tags": _extract_tags(content, offset, frontmatter),
            "links": _extract_links(content, offset), "backlinks": [],
            "modified_at": datetime.fromtimestamp(mtime_ns / 1_000_000_000, timezone.utc).isoformat(),
            "mtime_ns": mtime_ns}


def _link_candidates(target: str, index: _VaultIndex) -> list[str]:
    """An omitted extension means Markdown; attachment extensions must be explicit."""
    wanted = {os.path.normcase(target)}
    if PurePosixPath(target).suffix.lower() != ".md":
        wanted.add(os.path.normcase(target + ".md"))
    return sorted({path for name in wanted for path in index.by_path.get(name, [])})


def _resolve_link(link: dict, source: str, index: _VaultIndex, scope: _Scope) -> None:
    target = link["target"]
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("//"):
        link["resolution"] = "external"
        link["target_kind"] = "attachment"
        return
    wiki = link["raw"].lstrip("!").startswith("[[")
    target = target if wiki else unquote(re.sub(r"\\([\\() ])", r"\1", target))
    suffix = PurePosixPath(target).suffix.lower()
    link["target_kind"] = "note" if not suffix or suffix == ".md" else "attachment"
    if not target:
        candidates = [source]
    elif not wiki:
        key = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
        candidates = [] if key == ".." or key.startswith(("../", "/")) else _link_candidates(key, index)
    elif "/" in target:
        key = posixpath.normpath(target)
        candidates = [] if key == ".." or key.startswith(("../", "/")) else _link_candidates(key, index)
    else:
        local = posixpath.join(posixpath.dirname(source), target)
        candidates = _link_candidates(local, index)
        if not candidates:
            names = {target, target + ".md"} if suffix != ".md" else {target}
            names = {os.path.normcase(name) for name in names}
            candidates = sorted({path for name in names for path in index.by_name.get(name, [])})
    if len(candidates) > 1:
        link["resolution"] = "ambiguous"
    elif candidates:
        path = candidates[0]
        link["resolved_path"] = path
        link["target_kind"] = "note" if PurePosixPath(path).suffix.lower() == ".md" else "attachment"
        link["resolution"] = "resolved" if _in_scope(scope, scope.vault_path / path) else "out_of_scope"


def _resolve_links(notes: list[dict], index: _VaultIndex, scope: _Scope) -> None:
    """Use root paths, then same-directory names, then unique names across the vault."""
    for note in notes:
        for link in note["links"]:
            _resolve_link(link, note["path"], index, scope)


def _build_backlinks(notes: list[dict]) -> None:
    by_path = {note["path"]: note for note in notes}
    for note in notes:
        note["backlinks"] = []
    for source in notes:
        for index, link in enumerate(source["links"]):
            target = by_path.get(link["resolved_path"])
            if target is not None and link["resolution"] == "resolved" and link["target_kind"] == "note":
                target["backlinks"].append({"source_path": source["path"], "link_index": index})


def _load_scope_notes(scope: _Scope) -> list[dict]:
    """All-or-error: parse each selected note once and report every bad file together."""
    index = _build_vault_index(scope.vault_path)
    notes, failed = [], []
    for path in _scan_markdown(scope, index=index):
        key = path.relative_to(scope.vault_path).as_posix()
        try:
            content, mtime_ns = _read_markdown(scope, path)
            notes.append(_parse_markdown(content, key, mtime_ns))
        except (OSError, UnicodeError, ValueError, yaml.YAMLError, ObsidianError, RecursionError):
            failed.append(key)
    if failed:
        raise ObsidianError("Cannot load Obsidian notes: " + ", ".join(failed), HELP, failed_paths=failed)
    _resolve_links(notes, index, scope)
    _build_backlinks(notes)
    return notes


def _load_notes(vault_path: Path, *, folders: Sequence[str]) -> list[dict]:
    return _load_scope_notes(_validate_scope(vault_path, folders))


def _select_note(notes: list[dict], ref: str) -> dict:
    path_reference = "/" in ref or ref.lower().endswith(".md")
    found = [note for note in notes if note["path" if path_reference else "title"] == ref]
    if len(found) == 1:
        return found[0]
    if not found:
        raise ObsidianError(f"No note {ref!r} in the selected folders.", HELP)
    raise ObsidianError(f"Several notes are named {ref!r}: " + ", ".join(note["path"] for note in found), HELP)


def list_notes(vault_path: Path, *, folders: Sequence[str]) -> list[dict]:
    """Read selected Markdown notes, with properties and links; the vault stays unchanged."""
    return _load_notes(vault_path, folders=folders)


def read_note(vault_path: Path, ref: str, *, folders: Sequence[str]) -> dict:
    """Read a relative path or exact filename title, with backlinks from the same scope."""
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("Choose a note path or filename title.")
    scope = _validate_scope(vault_path, folders)
    if "/" in ref or "\\" in ref or ref.lower().endswith(".md") or Path(ref).is_absolute():
        ref = _resolve_note_path(scope, ref)
    return _select_note(_load_scope_notes(scope), ref)


# -- search ---------------------------------------------------------------

def _property_text(value) -> list[str]:
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in [str(key), *_property_text(item)]]
    if isinstance(value, list):
        return [text for item in value for text in _property_text(item)]
    return [str(value)]


def _search_fields(note: dict) -> dict[str, list[str]]:
    return {"title": [note["title"]], "body": [note["content"][note["body_offset"]:]],
            "tags": note["tags"], "frontmatter": _property_text(note["frontmatter"]),
            "links": [text for link in note["links"] for text in (link["target"], link["alias"]) if text]}


def _field_matches(field: str, values: list[str], term: str) -> bool:
    folded = term.casefold()
    if field == "tags":
        folded = folded.lstrip("#")
        return any(value.casefold() == folded or value.casefold().startswith(folded + "/") for value in values)
    return any(folded in value.casefold() for value in values)


def _match_query(note: dict, terms: list[str]) -> list[str]:
    """Every term must match this note, across the five supported fields."""
    fields = _search_fields(note)
    matches = [{field for field, values in fields.items() if _field_matches(field, values, term)} for term in terms]
    if not all(matches):
        return []
    return [field for field in fields if any(field in match for match in matches)]


def _make_excerpt(note: dict, terms: list[str], fields: list[str]) -> str:
    """Map folded positions back to source characters, including expansions such as ß → ss."""
    values = _search_fields(note)
    body = values["body"][0]
    folded = body.casefold()
    hits = [(folded.find(term.casefold()), len(term.casefold())) for term in terms if term.casefold() in folded]
    if hits:
        positions = [index for index, char in enumerate(body) for _ in char.casefold()]
        start, length = min(hits)
        return body[max(0, positions[start] - 80):positions[start + length - 1] + 81]
    for field in fields:
        for value in values[field]:
            if any(_field_matches(field, [value], term) for term in terms):
                return value
    return ""


def search_notes(vault_path: Path, query: str, *, folders: Sequence[str]) -> list[dict]:
    """Search selected notes with AND terms or quoted phrases; title matches come first."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Choose a non-empty search query.")
    terms = shlex.split(query)
    if not terms or any(not term for term in terms):
        raise ValueError("Choose a non-empty search query.")
    hits = []
    for note in _load_notes(vault_path, folders=folders):
        fields = _match_query(note, terms)
        if fields:
            hits.append({key: note[key] for key in ("note_key", "path", "title", "modified_at")}
                        | {"matched_fields": fields, "excerpt": _make_excerpt(note, terms, fields)})
    return sorted(hits, key=lambda hit: ("title" not in hit["matched_fields"], hit["path"]))
