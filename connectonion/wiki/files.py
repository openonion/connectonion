"""Canonical Markdown and small operational files; no knowledge database."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

CATEGORIES = ("people", "projects", "skills", "knowledge", "opportunities",
              "decisions", "principles", "works", "agenda", "notes")
MAX_NOTE_BYTES = 1_000_000
# The maintainer has a read-only shell and this is its only write path; a key it
# was tricked into cat-ing must not become a page. Shapes, not words: prose about
# "the API key" is fine, the key itself is not.
SECRET_SHAPES = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}|"
    r"\bxox[abpr]-[A-Za-z0-9-]{8,}|\bAIza[0-9A-Za-z_-]{30,}|\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.")


class WikiError(Exception):
    """Safe, user-facing Wiki error (never include source body or credentials)."""


def safe_path(root: Path, relative: str) -> Path:
    """Reject traversal and links instead of following them into another store."""
    parts = PurePosixPath(relative).parts
    if (not parts or relative.startswith("/") or "\\" in relative
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in relative)):
        raise WikiError("Expected a relative notebook path")
    if any(part in (".", "..") or part.startswith(".") for part in parts):
        raise WikiError("Hidden paths and traversal are not notebook content")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise WikiError("Symlinks are not supported inside the notebook")
    return path


def atomic_write(path: Path, text: str) -> None:
    """Replace one file, not the notebook; this is not a snapshot/version store."""
    if path.is_symlink():
        raise WikiError("Refusing to replace a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".wiki-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def state_path(root: Path, name: str) -> Path:
    """Operational paths are private to the wrapper, never exposed to the AI."""
    state = root / ".state"
    if state.is_symlink():
        raise WikiError("The Wiki state directory cannot be a symlink")
    return safe_path(state, name)


def read_json(path: Path, default):
    if path.is_symlink():
        raise WikiError("Refusing to read linked operational state")
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise WikiError(f"Invalid operational file: {path.name}; preserve it for diagnosis") from error


def write_json(path: Path, value) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def maintenance_lock(root: Path):
    """One OS-owned lock for every write path; process death releases it."""
    import fcntl

    path = state_path(root, "maintenance.lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise WikiError("Wiki is busy; wait for the active maintenance run") from error
        yield
    finally:
        os.close(fd)


class Notebook:
    """Small file API: semantic choices belong to the maintainer, not this class."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, record: str, *, writing: bool = False) -> Path:
        path = safe_path(self.root, record)
        parts = PurePosixPath(record).parts
        if parts[0] not in CATEGORIES or len(parts) < 2 or path.suffix != ".md":
            raise WikiError("Expected a Markdown record inside a Wiki category")
        if writing and (path.name.lower() in ("agents.md", "skill.md", "claude.md")
                        or parts[:2] == ("skills", "approved")):
            raise WikiError("Runtime instructions and approved Skills are not writable notebook targets")
        if parts[0] == "skills" and (len(parts) < 3 or parts[1] not in ("candidates", "approved")):
            raise WikiError("Skill notes belong in skills/candidates")
        if path.is_file() and path.stat().st_nlink != 1:
            raise WikiError("Hardlinked files are not supported notebook content")
        return path

    def list(self, category: str = "") -> list[str]:
        if category and category not in CATEGORIES:
            # Category names are ours, never private, so the offending value can be shown.
            raise WikiError(f"Unknown category {category!r}; choose from {', '.join(CATEGORIES)}")
        result = []
        for name in (category,) if category else CATEGORIES:
            directory = safe_path(self.root, name)
            for path in sorted(directory.rglob("*.md")):
                record = path.relative_to(self.root).as_posix()
                self.path(record)
                if path.is_file():
                    result.append(record)
        return result

    def read(self, record: str) -> str:
        path = self.path(record)
        if not path.is_file():
            raise WikiError("Record not found; list the notebook for current record paths")
        if path.stat().st_size > MAX_NOTE_BYTES:
            raise WikiError("Record exceeds the one-megabyte reading limit")
        return path.read_text(encoding="utf-8")

    def write(self, record: str, content: str) -> bool:
        path = self.path(record, writing=True)
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_NOTE_BYTES:
            raise WikiError("Markdown exceeds the one-megabyte writing limit")
        if SECRET_SHAPES.search(content):
            raise WikiError("Refusing to write secret-shaped content (a key or token) into a notebook page")
        if path.exists() and self.read(record) == content:
            return False
        atomic_write(path, content)
        return True

    def delete(self, record: str) -> bool:
        path = self.path(record, writing=True)
        if not path.exists():
            return False
        path.unlink()
        return True

    def search(self, query: str, category: str = "") -> list[dict]:
        if not query.strip():
            raise WikiError("Search needs a nonempty query")
        found = []
        for record in self.list(category):
            for number, line in enumerate(self.read(record).splitlines(), 1):
                if query.casefold() in line.casefold():
                    found.append({"record": record, "line": number, "text": line[:500]})
        return found
