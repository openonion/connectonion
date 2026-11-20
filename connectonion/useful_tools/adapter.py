"""OneNote record envelope, immutable references and local JSONL storage.

Extracted from the team shared adapter; sibling-provider converters are excluded.
"""

import datetime
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path



# The shared envelope (#1833): every source writes exactly these top-level fields, plus optional "media".
RECORD_FIELDS = ("id", "source", "account", "external_id", "kind", "title", "text",
                 "url", "author", "at", "updated", "fetched", "extensions")
REQUIRED_FIELDS = ("id", "source", "account", "external_id", "kind", "fetched")
MEDIA_FIELDS = ("sha256", "name", "mime", "size", "status")
MEDIA_STATUSES = ("metadata_only", "stored", "unavailable")


@dataclass
class AdapterResult:
    """Common result type for all co rem source adapters (F13FCAKE-16, F13FCAKE-18).

    records: list of envelope dicts that passed validate_record().
    errors: mapping of label → error message for partial failures and rejected items.
    """

    records: list[dict] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


# Shared identity rule: source + account + external id, e.g. "onenote:test-account:page-1".
def record_id(source: str, account: str, external_id: str) -> str:
    """Globally unique record id; the same external id in two sources or two accounts never collides."""
    account_key = account.split("://", 1)[-1].rstrip("/")
    return f"{source}:{account_key}:{external_id}"


def _now_utc() -> str:
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return stamp.isoformat().replace("+00:00", "Z")


# Build one envelope; anything source-specific belongs under extensions, never at the top level.
def make_record(source: str, account: str, external_id: str, kind: str, *,
                title: str = "", text: str = "", url: str = "", author: str = "",
                at: str = "", updated: str = "", extensions: dict | None = None,
                media: list[dict] | None = None, fetched: str | None = None) -> dict:
    """Return a record in the shared envelope; "media" is present only when there is media."""
    record = {
        "id": record_id(source, account, external_id),
        "source": source, "account": account, "external_id": external_id, "kind": kind,
        "title": title, "text": text, "url": url, "author": author,
        "at": at, "updated": updated, "fetched": fetched or _now_utc(),
        "extensions": extensions or {},
    }
    if media:
        record["media"] = media
    return record


# Media reference (#1938): content hash when the bytes are stored, metadata only otherwise.
def media_ref(name: str, mime: str = "", size: int | None = None,
              sha256: str | None = None, status: str = "metadata_only") -> dict:
    """Describe an image or attachment without embedding or downloading it."""
    return {"sha256": sha256, "name": name, "mime": mime, "size": size, "status": status}


# The one contract check every source mapping is validated against; empty list means valid.
def validate_record(record) -> list[str]:
    """Return every contract violation in one record, worded for a mapping-error report."""
    if not isinstance(record, dict):
        return ["record is not an object"]
    # Every envelope field must be present; optional ones may be empty ("" or {}), never absent.
    problems = [f"missing field '{name}'" for name in RECORD_FIELDS if name not in record]
    problems += [f"missing required field '{name}'" for name in REQUIRED_FIELDS
                 if name in record and not record[name]]
    problems += [f"field '{name}' must be a string" for name in RECORD_FIELDS
                 if name != "extensions" and name in record and not isinstance(record[name], str)]
    if "extensions" in record and not isinstance(record["extensions"], dict):
        problems.append("field 'extensions' must be an object")
    expected = record_id(str(record.get("source", "")), str(record.get("account", "")),
                         str(record.get("external_id", "")))
    if record.get("id") and record["id"] != expected:
        problems.append(f"field 'id' must be '{expected}' (source:account:external_id)")
    problems += _media_problems(record.get("media", []))
    problems += [f"unknown top-level field '{name}'; put source-specific data under extensions"
                 for name in sorted(set(record) - set(RECORD_FIELDS) - {"media"})]
    return problems


def _media_problems(media) -> list[str]:
    if not isinstance(media, list):
        return ["field 'media' must be a list"]
    problems = []
    for index, item in enumerate(media):
        if not isinstance(item, dict) or set(item) != set(MEDIA_FIELDS):
            problems.append(f"media[{index}] must have exactly: {', '.join(MEDIA_FIELDS)}")
        elif item["status"] not in MEDIA_STATUSES:
            problems.append(f"media[{index}] has unknown status {item['status']!r}")
        elif item["status"] == "stored" and not item["sha256"]:
            problems.append(f"media[{index}] is stored but has no sha256 content hash")
    return problems


# Map every item, keep only valid records; malformed or invalid items are reported, not raised.
def _collect(items: list, source: str, shape_problems, build) -> AdapterResult:
    result = AdapterResult()
    seen: set[str] = set()
    for index, item in enumerate(items):
        problems = shape_problems(item)
        record, build_problems = (None, []) if problems else _build(build, item)
        problems = problems or build_problems or validate_record(record) or _duplicate_problem(record, seen)
        if problems:
            result.errors[_error_label(result.errors, source, item, index)] = "mapping error: " + "; ".join(problems)
        else:
            seen.add(record["id"])
            result.records.append(record)
    return result


# Source content is untrusted: an unexpected failure while mapping one item becomes that item's error,
# never an exception that aborts the whole batch (F13FCAKE-11 "malformed content is isolated").
def _build(build, item) -> tuple[dict | None, list[str]]:
    try:
        return build(item), []
    except Exception as exc:  # noqa: BLE001 — reported per item, not swallowed
        return None, [f"content could not be mapped ({type(exc).__name__}: {str(exc)[:200]})"]


# A source that returns the same item twice (e.g. a repeated page) must not yield two records.
def _duplicate_problem(record: dict, seen: set[str]) -> list[str]:
    if record["id"] in seen:
        return [f"duplicate of an earlier item in this batch ({record['id']}); the first copy was kept"]
    return []


# Error labels stay unique: a second bad item with the same key gets "#<position>" instead of overwriting.
def _error_label(errors: dict, source: str, item, index: int) -> str:
    label = f"{source}:{_item_label(item, index)}"
    return f"{label}#{index}" if label in errors else label


def _item_label(item, index: int) -> str:
    if isinstance(item, dict) and (item.get("key") or item.get("id")):
        return str(item.get("key") or item.get("id"))
    return f"item-{index}"


def consume_records(result: AdapterResult) -> list[dict]:
    """Source-agnostic consumer: returns the records from an AdapterResult.

    No source-specific branching — works identically for OneNote or
    any other adapter that produces an AdapterResult.
    """
    return result.records


def write_daily_jsonl(records: list[dict], source_dir: Path) -> Path:
    """Append records as JSONL under source_dir/daily/YYYY/MM/DD.jsonl and return that path.

    Same behaviour as append_daily_jsonl(); use that when the caller needs to know how
    many records were actually appended (CLI summaries).
    """
    return append_daily_jsonl(records, source_dir)[0]


# Same append as write_daily_jsonl, but also reports how many records were new (not deduplicated away).
def append_daily_jsonl(records: list[dict], source_dir: Path, *,
                       date: datetime.date | None = None, keep_versions: bool = False,
                       atomic: bool = False) -> tuple[Path, int]:
    """Append records as JSONL under source_dir/daily/YYYY/MM/DD.jsonl.

    Default (every source): deduplicates by (source, account, id), so an id already in that
    day's file is skipped even if its content changed — the OneNote import relies on this.
    keep_versions=True: deduplicates by identity, updated and a
    content hash excluding fetched, so an edit or newly available history is appended as a new
    snapshot even if updated has not changed, while an unchanged re-read is still skipped.
    Old lines stay untouched either way. Duplicates within the same records list are also suppressed.
    Creates all intermediate directories.  Returns (path written, number of records appended).
    Raises ValueError if the existing file contains a malformed JSON line —
    refuses to append to a corrupted file to avoid data inconsistency.
    """
    source_dir = Path(source_dir)
    # A collection started before midnight stays on its explicitly selected day.
    today = date or datetime.date.today()
    daily_dir = source_dir / "daily" / str(today.year) / f"{today.month:02d}"
    daily_dir.mkdir(parents=True, exist_ok=True)
    target = daily_dir / f"{today.day:02d}.jsonl"

    existing_keys: set[tuple] = set()
    if target.exists():
        with open(target, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        existing_keys.add(_dedupe_key(rec, keep_versions))
                    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
                        raise ValueError(
                            f"Existing JSONL file {target} is corrupted at line {lineno}: {exc}. "
                            "Refusing to append to avoid data inconsistency."
                        ) from exc

    seen_keys: set[tuple] = set(existing_keys)
    new_records: list[dict] = []
    for r in records:
        key = _dedupe_key(r, keep_versions)
        if key not in seen_keys:
            seen_keys.add(key)
            new_records.append(r)

    if atomic:
        # The caller holds the source lock across the checkpoint read and write.
        from ..rem.files import atomic_write
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        if new_records:
            separator = "\n" if previous and not previous.endswith("\n") else ""
            atomic_write(target, previous + separator +
                         "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in new_records))
        return target, len(new_records)

    with open(target, "a", encoding="utf-8") as fh:
        for record in new_records:
            json.dump(record, fh, ensure_ascii=False)
            fh.write("\n")
        if new_records:
            fh.flush()
            os.fsync(fh.fileno())
    return target, len(new_records)


# Content identity: ignore collection time, but include history so a successful retry is kept.
def _snapshot_hash(record: dict) -> str:
    content = {name: value for name, value in record.items() if name != "fetched"}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Same item = same (source, account, id); with keep_versions each distinct snapshot of it counts separately.
def _dedupe_key(record, keep_versions: bool) -> tuple:
    identity = tuple(record.get(name, "") for name in ("source", "account", "id"))
    if not keep_versions:
        return identity
    return (*identity, record.get("updated", ""), _snapshot_hash(record))


# Cite one immutable snapshot, so later appends cannot change the evidence behind a page.
def record_reference(file_path: Path, record: dict, notebook_root: Path) -> str:
    """Return "<file relative to notebook_root>#<record id>?version=<sha256>".

    The path always uses "/" so a reference written on Windows resolves on macOS and Linux.
    The hash covers record content except fetched; an identical re-read cites the same snapshot.
    Raises ValueError if file_path is outside notebook_root or the record has no id.
    """
    root = Path(notebook_root).resolve()
    path = Path(file_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{file_path} is outside the notebook {notebook_root}; a reference must stay inside it.")
    if not isinstance(record, dict) or not record.get("id"):
        raise ValueError("The record has no id, so it cannot be referenced.")
    return f"{path.relative_to(root).as_posix()}#{record['id']}?version={_snapshot_hash(record)}"


# Versioned references match that snapshot; legacy file#id references keep the first matching line.
def resolve_reference(reference: str, notebook_root: Path) -> dict | None:
    """Return the record a record_reference() points to, or None if it cannot be found.

    Versioned references never fall back to another snapshot. Legacy file#id references resolve
    to the first matching line, not the latest. None for a missing version/id/file or an unsafe path.
    Malformed lines are skipped, so reading never raises on a damaged JSON line.
    """
    relative, _, wanted = str(reference).partition("#")
    record_id, marker, version = wanted.rpartition("?version=")
    if marker:
        if not re.fullmatch(r"[0-9a-f]{64}", version):
            return None
        wanted = record_id
    root = Path(notebook_root).resolve()
    path = (root / relative).resolve()
    if not wanted or not path.is_relative_to(root) or not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        record = _json_line(line)
        if isinstance(record, dict) and record.get("id") == wanted:
            if not marker or _snapshot_hash(record) == version:
                return record
    return None


def _json_line(line: str):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def consume_jsonl_records(
    *source_dirs: Path,
    date: datetime.date | None = None,
) -> AdapterResult:
    """Read daily JSONL records from one or more source directories.

    Source-agnostic: works for any directory written by write_daily_jsonl().
    date defaults to today.  Missing or empty files are silently skipped.
    Malformed JSON lines are recorded in result.errors keyed by
    "<file_path>:<line_number>" so callers can detect and report data corruption
    without losing the valid records from other sources.
    """
    if date is None:
        date = datetime.date.today()
    records: list[dict] = []
    errors: dict[str, str] = {}
    for source_dir in source_dirs:
        source_dir = Path(source_dir)
        jsonl_path = (
            source_dir / "daily" / str(date.year) / f"{date.month:02d}" / f"{date.day:02d}.jsonl"
        )
        if not jsonl_path.exists():
            continue
        with open(jsonl_path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        errors[f"{jsonl_path}:{lineno}"] = f"JSON decode error: {exc}"
    return AdapterResult(records=records, errors=errors)


def onenote_pages_to_records(pages: list[dict], account: str, *, fetched: str | None = None) -> AdapterResult:
    """Convert raw OneNote page dicts to shared-contract records (F13FCAKE-16, F13FCAKE-18).

    Envelope: id = "onenote:<account>:<page id>", external_id = page id, kind = "page",
    title, url (oneNoteWebUrl, or contentUrl flagged extensions.url_is_api),
    at = createdDateTime, updated = lastModifiedDateTime; section and notebook go under extensions.
    Page HTML is not fetched here (F13FCAKE-14). Invalid items are reported in errors, not raised.
    """
    stamp = fetched or _now_utc()
    return _collect(pages, "onenote", _onenote_shape_problems, lambda page: _onenote_record(page, account, stamp))


def _onenote_shape_problems(page) -> list[str]:
    return [] if isinstance(page, dict) else ["item is not an object"]


# One OneNote page → one envelope; the web link is preferred over the Graph content URL.
def _onenote_record(page: dict, account: str, fetched: str) -> dict:
    links = page.get("links") if isinstance(page.get("links"), dict) else {}
    web = links.get("oneNoteWebUrl")
    web_url = str(web.get("href") or "") if isinstance(web, dict) else ""
    content_url = str(page.get("contentUrl") or "")
    values = {
        "section": _parent_name(page.get("parentSection")),
        "notebook": _parent_name(page.get("parentNotebook")),
        "url_is_api": True if not web_url and content_url else None,
    }
    # Source details belong under extensions, keeping the shared envelope exact.
    for name in ("scope", "media_fetch_references"):
        if name in page:
            values[name] = page[name]
    return make_record(
        "onenote", account, str(page.get("id") or ""), "page",
        title=str(page.get("title") or ""), text=page.get("text", ""), url=web_url or content_url,
        at=str(page.get("createdDateTime") or ""), updated=str(page.get("lastModifiedDateTime") or ""),
        extensions={name: value for name, value in values.items() if value not in ("", None)},
        media=page.get("media"),
        fetched=fetched,
    )


def _parent_name(parent) -> str:
    return str(parent.get("displayName") or "") if isinstance(parent, dict) else ""


# Public content-hash API for local snapshot readers.
snapshot_hash = _snapshot_hash
