"""Local OneNote origins projected into the existing Reader context."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .files import EMAIL, KEY_SHAPES, RemError, safe_path
from ..useful_tools.adapter import record_reference, validate_record

SOURCES = {"onenote"}
PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)
CREDENTIALS = {"access_token", "refresh_token", "id_token", "token", "api_key",
               "api_token", "authorization", "password"}
EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def source_key(citation: str) -> str:
    """A display alias, never a replacement for the adapter's stored identity."""
    return "source-ref:" + hashlib.sha256(citation.strip().encode("utf-8")).hexdigest()


def _citation(value: str):
    value = value.removeprefix("adapter:")
    relative, marker, identity = value.partition("#")
    identity = identity if marker else value
    identity, version_marker, version = identity.partition("?version=")
    source = identity.partition(":")[0]
    if source not in SOURCES:
        return None
    invalid = identity.count(":") < 2 or any(ord(c) < 32 for c in value)
    if version_marker and (not marker or not re.fullmatch(r"[0-9a-f]{64}", version)):
        invalid = True
    if marker and (not relative.startswith(f"docs/{source}/") or not relative.endswith(".jsonl")):
        invalid = True
    return source, identity, relative if marker else "", version if version_marker else "", invalid


def _empty(source, citation):
    return dict(source=source, status="not_found", link="unavailable", reason="missing_record", warning="",
                subject="", external_id="", kind="", url="", reference=source_key(citation), excerpt="",
                truncated=False, time="", fetched="", sender="", thread="", input_scope="")


def _instant(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else EARLIEST
    except (ValueError, OverflowError):
        return EARLIEST


def _version(root, item):
    record, path, _ = item
    return record_reference(path, record, root).rpartition("?version=")[2]


def _order(root, item):
    record, path, line = item
    time = next((t for key in ("updated", "at", "fetched") if (t := _instant(record[key])) != EARLIEST), EARLIEST)
    return time, _instant(record["fetched"]), _version(root, item), path.relative_to(root).as_posix(), line


def _clean(text, private=False):
    if PRIVATE.search(text) and not private:
        return ""
    return "[secret-shaped text withheld]" if KEY_SHAPES.search(text) else text.strip()


def _link(record):
    raw = record["url"]
    if not raw:
        return "", "unavailable", "no_url"
    try:
        url = urlsplit(raw)
        if (url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None
                or re.search(r"[\s\x00-\x1f\x7f\\]", raw) or KEY_SHAPES.search(raw)):
            return "", "unavailable", "unsafe_url"
        _ = url.port  # Reject malformed ports, even for OneNote.
        if any(key.lower() in CREDENTIALS for key, _ in parse_qsl(url.query) + parse_qsl(url.fragment)):
            return "", "unavailable", "unsafe_url"
        if record["source"] == "onenote":
            if record["extensions"].get("url_is_api") or url.hostname.lower() == "graph.microsoft.com":
                return "", "api_only", "api_only"
    except ValueError:
        return "", "unavailable", "unsafe_url"
    return raw, "ok", ""


def _view(root, citation, item, private):
    record, _, _ = item
    context = _empty(record["source"], citation)
    text = _clean(record["text"], private)
    url, link, reason = _link(record)
    sender = EMAIL.sub("", _clean(record["author"])).strip(" <>()")
    context.update(status="resolved", link=link, reason=reason, url=url, subject=_clean(record["title"]),
                   external_id="", kind=record["kind"],
                   excerpt=text[:2048], truncated=len(text) > 2048, time=record["updated"] or record["at"],
                   fetched=record["fetched"], sender=sender,
                   reference=source_key(citation) + "?version=" + _version(root, item))
    if record["source"] == "onenote":
        for field in ("subject", "sender", "excerpt"):
            context[field] = context[field].replace(record["account"], "[account]")
    return {key: _clean(value) if isinstance(value, str) and key != "excerpt" else value
            for key, value in context.items()}


def _source_paths(root, source):
    """Unlike Path.glob, walk reports directory permission and enumeration errors."""
    paths, errors = [], []

    def failed(error):
        if not isinstance(error, FileNotFoundError):
            errors.append("read_error")

    for group in ("daily", "exports"):
        try:
            base = safe_path(root, f"docs/{source}/{group}")
            for directory, dirs, files in os.walk(base, onerror=failed, followlinks=False):
                depth = len(Path(directory).relative_to(base).parts)
                for name in dirs:
                    if (Path(directory) / name).is_symlink():
                        errors.append("read_error")
                dirs[:] = [name for name in dirs if not name.startswith(".") and not (Path(directory) / name).is_symlink()
                           and (group == "daily" or depth == 0)]
                paths.extend(Path(directory) / name for name in files if not name.startswith(".")
                             and (name.endswith(".jsonl") if group == "daily" else depth == 1 and name == "records.jsonl"))
        except (OSError, RemError):
            errors.append("read_error")
    return sorted(paths), "read_error" if errors else ""


class SourceRecords:
    """One render's read cache; never retained between snapshots or notebooks."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {}
        self.sources = {}

    def _read(self, path, source):
        if path in self.files:
            return self.files[path]
        rows, problem = [], ""
        try:
            safe_path(self.root, path.relative_to(self.root).as_posix())
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        except (OSError, UnicodeError, RemError):
            self.files[path] = ([], "read_error")
            return self.files[path]
        for line, raw in enumerate(text.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                problem = "read_error"
                continue
            if validate_record(row) or row["source"] != source:
                problem = problem or "invalid_record"
                continue
            rows.append((row, path, line))
        self.files[path] = rows, problem
        return rows, problem

    def _scan(self, source):
        if source in self.sources:
            return self.sources[source]
        rows, problem = [], ""
        try:
            paths, problem = _source_paths(self.root, source)
            for path in paths:
                items, error = self._read(path, source)
                rows.extend(items)
                problem = error or problem
        except (OSError, RemError):
            problem = "read_error"
        self.sources[source] = rows, problem
        return rows, problem

    def context(self, citation, private=False):
        parsed = _citation(citation.strip())
        if parsed is None:
            return None
        source, identity, relative, version, invalid = parsed
        context = _empty(source, citation)
        try:
            path = safe_path(self.root, relative) if relative else None
        except RemError:
            path, invalid = None, True
        if invalid:
            return {**context, "status": "error", "reason": "invalid_reference"}
        rows, problem = self._read(path, source) if path is not None else self._scan(source)
        matches = [item for item in rows if item[0]["id"] == identity
                   and (not version or _version(self.root, item) == version)]
        if not matches:
            return {**context, "status": "error", "reason": problem} if problem else context
        chosen = matches[0] if path is not None else max(matches, key=lambda item: _order(self.root, item))
        context = _view(self.root, citation, chosen, private)
        if problem and not version:
            context["warning"] = "incomplete_read"
        return context


def source_record_context(root: Path, source_id: str, *, private: bool = False) -> dict | None:
    """Resolve supported citations locally; None is reserved for other providers."""
    return SourceRecords(root).context(source_id, private)


def public_sources(records: list[dict], contexts: dict) -> tuple[list[dict], dict]:
    """Replace internal source identities only in the disposable Reader projection."""
    aliases = {key: source_key(key) for key, value in contexts.items() if value.get("source") in SOURCES}
    from .reader_model import source_references
    for row in records:
        for text in [row["text"], *(row.get("translations") or {}).values()]:
            aliases.update({raw: source_key(raw) for _, raw in source_references(text) if _citation(raw) is not None})
    ordered = sorted(aliases, key=len, reverse=True)

    def project(value):
        if isinstance(value, str):
            for raw in ordered:
                value = value.replace(raw, aliases[raw])
            return value
        if isinstance(value, list):
            return [project(item) for item in value]
        if isinstance(value, dict):
            return {aliases.get(key, key): project(item) for key, item in value.items()}
        return value

    return project(records), project(contexts)


def public_source_text(text: str) -> str:
    """Apply the same aliases at the live translation response boundary."""
    return public_sources([{"text": text}], {})[0][0]["text"]


def public_projection(data: dict) -> dict:
    """Alias account-bearing citations throughout a disposable Reader response."""
    from .reader_model import source_references
    aliases = {key: source_key(key) for key, value in data.get("source_context", {}).items()
               if value.get("source") == "onenote"}

    def discover(value):
        if isinstance(value, str):
            for _, raw in source_references(value):
                if _citation(raw) is not None:
                    aliases[raw] = source_key(raw)
        elif isinstance(value, list):
            for child in value:
                discover(child)
        elif isinstance(value, dict):
            for child in value.values():
                discover(child)

    discover(data)
    ordered = sorted(aliases, key=len, reverse=True)

    def project(value):
        if isinstance(value, str):
            for raw in ordered:
                value = value.replace(raw, aliases[raw])
            return value
        if isinstance(value, list):
            return [project(child) for child in value]
        if isinstance(value, dict):
            value = {key: child for key, child in value.items()
                     if key not in {"credential_file", "credential_home"}}
            if isinstance(value.get("import_identity"), dict):
                value = {**value, "import_identity": {key: child for key, child in value["import_identity"].items()
                                                      if key != "account"}}
            if value.get("kind") == "onenote":
                value = {key: child for key, child in value.items() if key != "root"}
            return {aliases.get(key, key): project(child) for key, child in value.items()}
        return value

    return project(data)
