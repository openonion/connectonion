"""
Purpose: Shared record contract and common adapter for co rem source integrations (F13FCAKE-16, F13FCAKE-18).
LLM-Note:
  Dependencies: imports from [datetime, json, dataclasses, pathlib, useful_tools/jira_adf.adf_to_text] | imported by [tests/unit/test_jira.py, cli/commands/jira_commands.py] | no network calls
  Data flow: raw tool output (Jira issues / OneNote pages) → *_to_records() → make_record() envelope → validate_record() → AdapterResult (valid records + per-item errors) → ongoing: write_daily_jsonl() / append_daily_jsonl() under daily/YYYY/MM/DD.jsonl | one-off: write_export() under exports/<id>/{records.jsonl,manifest.json}
  State/Effects: write_daily_jsonl() / append_daily_jsonl() / write_export() create directories and write files (append_daily_jsonl also returns how many records were new); all other functions are pure
  Integration: RECORD_FIELDS is the #1833 envelope every source writes; record_id() is the shared identity rule; make_record() / media_ref() build records; validate_record() is the one contract check for every source; AdapterResult is the shared result type; consume_records() is the in-memory consumer; consume_jsonl_records() reads from disk across multiple source directories; jira_issues_to_records(), onenote_pages_to_records(), and granola_notes_to_records() are the converter functions
  Errors: write_daily_jsonl() raises ValueError if the existing JSONL file contains a malformed line (refuses to append to a corrupted file) | write_export() raises ValueError for an unsafe export id, an existing export or any invalid/duplicate record, before writing anything | consume_jsonl_records() never raises — malformed lines are recorded in AdapterResult.errors keyed by "file:lineno" | converters never raise on bad input — an invalid, malformed or duplicate item is left out of records and reported in AdapterResult.errors keyed by "<source>:<item>"
  F13FCAKE-16 contract status:
    Envelope, identity, extensions, media references and validation implemented for both sources; documented in docs/acceptance/record-contract.md
    OneNote page HTML is not fetched here; readable text conversion is F13FCAKE-14
  F13FCAKE-11 Jira content status:
    Jira.issue_items() requests jira.ISSUE_FIELDS; description ADF → record["text"] via jira_adf.adf_to_text(),
    raw ADF kept under extensions.description_adf; due and resolution dates kept under extensions
    The same item twice in one batch (e.g. overlapping pages) yields one record; the repeat is reported in errors
    Placement is explicit: ongoing changes → write_daily_jsonl(); a one-off project import → write_export() (prototype writer)
  F13FCAKE-12 Jira history status:
    Jira.issue_changelogs() → per-issue outcome {status, histories, reason}; changelog_extension() turns it into
    {status, entries, reason} with entries from jira_changelog_entries() (time, author name, field from → to)
    co jira sync appends with keep_versions=True: a changed item or newly read history is appended as a new snapshot;
      fetched alone never creates a duplicate. Other sources (OneNote) keep the default one-line-per-id-per-day rule
    record_reference() cites "<notebook-relative file>#<id>?version=<content hash>"; resolution keeps that snapshot
    Jira chain -- fully integrated: verify_connection -> issue_items -> issue_changelogs (co jira sync, unless --no-history)
      -> write_source_yaml -> jira_issues_to_records(changelogs=...) -> write_daily_jsonl / write_export
    OneNote chain -- adapter function implemented and tested with synthetic fixtures; live Notes.Read integration is pending authorized account credentials and OneNote team implementation

Common adapter contract for co rem integrations.

Usage:
    from connectonion.useful_tools.adapter import (
        AdapterResult, consume_records, consume_jsonl_records, validate_record,
        write_daily_jsonl, jira_issues_to_records, onenote_pages_to_records,
    )
    result = jira_issues_to_records(issues, base_url)
    records = consume_records(result)          # only records that passed validate_record()
    rejected = result.errors                   # "<source>:<item>" -> reason
    jsonl_path = write_daily_jsonl(result.records, source_dir)
    # Read back from disk (source-agnostic):
    result = consume_jsonl_records(jira_dir, onenote_dir)
    all_records = result.records  # result.errors contains any malformed-line diagnostics
"""

import datetime
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .jira_adf import adf_to_text

# An export id becomes a directory name under exports/: letters, digits, ".", "_", "-" only.
EXPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

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


# Shared identity rule: source + account + external id, e.g. "jira:test.atlassian.net:ALPHA-1".
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

    No source-specific branching — works identically for Jira, OneNote, or
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
    keep_versions=True (co jira sync, F13FCAKE-12): deduplicates by identity, updated and a
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


# One-off import (#1938): a validated snapshot in exports/<id>/, written once and never appended to.
def write_export(records: list[dict], source_dir: Path, export_id: str, scope: dict) -> Path:
    """Write exports/<export_id>/records.jsonl and manifest.json; return the export directory.

    Ongoing changes go to write_daily_jsonl(); a one-off import of a project's history goes here.
    Everything is checked before anything is written: an unsafe export id, an export that already
    exists, any record that fails validate_record() or repeats an id, and records or a scope that
    cannot be serialised to JSON all raise ValueError.
    Files are written into a hidden staging directory first, then renamed into place, so a
    half-written export never appears under exports/; if writing fails the staging directory is
    removed, so the same export id can be retried.
    """
    target = export_target(Path(source_dir), export_id)
    problems = _export_problems(records)
    if problems:
        shown = "; ".join(problems[:5]) + (f"; … {len(problems) - 5} more" if len(problems) > 5 else "")
        raise ValueError(f"Refusing to write export {export_id!r}: {shown}. Nothing was written.")
    lines, manifest_text = _export_payload(records, export_id, scope)
    staging = target.with_name(f".{export_id}.partial")
    staging.mkdir(parents=True)
    try:
        (staging / "records.jsonl").write_text(lines, encoding="utf-8")
        (staging / "manifest.json").write_text(manifest_text, encoding="utf-8")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


# Serialise everything before touching the disk, so a bad value fails with nothing written.
def _export_payload(records: list[dict], export_id: str, scope: dict) -> tuple[str, str]:
    try:
        lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        manifest = json.dumps(_export_manifest(records, export_id, scope), ensure_ascii=False, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Refusing to write export {export_id!r}: records or scope cannot be saved as JSON "
                         f"({exc}). Nothing was written.") from None
    return lines, manifest


# Where an export would go; raises ValueError for an unsafe id, an existing export or a leftover staging folder.
# Callers (co jira sync --export) use it to fail before collecting anything.
def export_target(source_dir: Path, export_id: str) -> Path:
    if not isinstance(export_id, str) or not EXPORT_ID.match(export_id):
        raise ValueError(f"Invalid export id {export_id!r}: use letters, digits, '.', '_' or '-' (max 64), "
                         "e.g. 'ALPHA-history-2026-10-12'. Nothing was written.")
    target = source_dir / "exports" / export_id
    if target.exists():
        raise ValueError(f"Export {export_id!r} already exists at {target}; exports are one-off snapshots. "
                         "Choose a new export id. Nothing was written.")
    staging = target.with_name(f".{export_id}.partial")
    if staging.exists():
        raise ValueError(f"An unfinished earlier attempt left {staging} (for example after a crash). "
                         "Delete that folder and retry. Nothing was written.")
    return target


# Every record must pass the shared contract and appear once; problems are collected, not raised one by one.
def _export_problems(records: list[dict]) -> list[str]:
    problems, seen = [], set()
    for index, record in enumerate(records):
        label = record.get("id") if isinstance(record, dict) and record.get("id") else f"record {index}"
        problems += [f"{label}: {problem}" for problem in validate_record(record)]
        if isinstance(record, dict) and record.get("id") in seen:
            problems.append(f"{label}: duplicate id in this export")
        seen.add(record.get("id") if isinstance(record, dict) else None)
    return problems


def _export_manifest(records: list[dict], export_id: str, scope: dict) -> dict:
    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1
    return {
        "export_id": export_id,
        "created": _now_utc(),
        "scope": scope,
        "sources": sorted({record["source"] for record in records}),
        "accounts": sorted({record["account"] for record in records}),
        "counts": {"records": len(records), "by_kind": dict(sorted(kinds.items()))},
        "files": ["records.jsonl"],
        "contract": "#1833 shared record envelope — docs/acceptance/record-contract.md",
    }


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


def jira_issues_to_records(issues: list[dict], base_url: str, *, fetched: str | None = None,
                           changelogs: dict | None = None) -> AdapterResult:
    """Convert raw Jira issue dicts to shared-contract records (F13FCAKE-11, F13FCAKE-12, F13FCAKE-16, F13FCAKE-18).

    Envelope: id = "jira:<site>:<key>", external_id = issue key, kind = issue type,
    title = summary, text = description as readable text (ADF converted by jira_adf.adf_to_text),
    url = browse URL, author = reporter, at = created, updated = updated.
    Jira-only fields (status, priority, labels, people, parent, due/resolution dates, raw ADF) go under extensions;
    attachments become metadata-only media references. Token and email are never included.
    changelogs: Jira.issue_changelogs() output keyed by issue key. When given, every record gets
    extensions.changelog for its own key (an issue missing from it is marked "unavailable"); when
    None, history was not requested and no changelog is added. A restricted or unavailable history
    never removes the issue's content.
    An item that is not an object or fails validate_record() is reported in errors, not raised.
    """
    stamp = fetched or _now_utc()

    def build(issue):
        return _with_changelog(_jira_record(issue, base_url, stamp), changelogs)

    return _collect(issues, "jira", _jira_shape_problems, build)


# Attach the history read for this record's own issue key; other issues' histories never leak in.
def _with_changelog(record: dict, changelogs: dict | None) -> dict:
    if changelogs is None:
        return record
    outcome = changelogs.get(record["external_id"]) if isinstance(changelogs, dict) else None
    record["extensions"]["changelog"] = changelog_extension(outcome)
    return record


def _jira_shape_problems(issue) -> list[str]:
    if not isinstance(issue, dict):
        return ["item is not an object"]
    if not isinstance(issue.get("fields", {}), dict):
        return ["'fields' is not an object"]
    return []


# One Jira issue → one envelope; the description becomes readable text, its raw ADF stays in extensions.
def _jira_record(issue: dict, base_url: str, fetched: str) -> dict:
    fields = issue.get("fields") or {}
    key = str(issue.get("key") or "")
    return make_record(
        "jira", base_url, key, _name(fields.get("issuetype")) or "issue",
        title=str(fields.get("summary") or ""),
        text=adf_to_text(fields.get("description")),
        url=f"{base_url}/browse/{key}" if key else "",
        author=_display_name(fields.get("reporter") or fields.get("creator")),
        at=str(fields.get("created") or ""), updated=str(fields.get("updated") or ""),
        extensions=_jira_extensions(issue, fields),
        media=[_jira_media(item) for item in _list(fields.get("attachment")) if isinstance(item, dict)],
        fetched=fetched,
    )


# Jira-only fields kept under extensions; empty values are left out.
def _jira_extensions(issue: dict, fields: dict) -> dict:
    parent = fields.get("parent")
    description = fields.get("description")
    people = {}
    for role, person in (("reporter", fields.get("reporter") or fields.get("creator")),
                         ("assignee", fields.get("assignee"))):
        account_id = person.get("accountId") if isinstance(person, dict) else None
        if isinstance(account_id, str) and account_id.strip():
            people[role] = account_id
    values = {
        "issue_id": str(issue.get("id") or ""),
        "status": _name(fields.get("status")),
        "priority": _name(fields.get("priority")),
        "labels": [str(label) for label in _list(fields.get("labels"))],
        "assignee": _display_name(fields.get("assignee")),
        "reporter": _display_name(fields.get("reporter")),
        "people": people or None,
        "parent": str(parent.get("key") or "") if isinstance(parent, dict) else "",
        "duedate": str(fields.get("duedate") or ""),
        "resolutiondate": str(fields.get("resolutiondate") or ""),
        "description_adf": description if isinstance(description, dict) else None,
    }
    return {name: value for name, value in values.items() if value not in ("", None, [])}


def _jira_media(attachment: dict) -> dict:
    return media_ref(str(attachment.get("filename") or ""), str(attachment.get("mimeType") or ""),
                     attachment.get("size"))


def _name(value) -> str:
    return str(value.get("name") or "") if isinstance(value, dict) else ""


def _display_name(person) -> str:
    """Display name only; account emails never enter a record."""
    return str(person.get("displayName") or "") if isinstance(person, dict) else ""


def _list(value) -> list:
    return value if isinstance(value, list) else []


# History outcomes a record may carry (F13FCAKE-12); mirrors jira.CHANGELOG_STATUSES.
CHANGELOG_STATUSES = ("ok", "none", "restricted", "unavailable")
CHANGE_VALUE_CHARS = 1000


# Raw Jira histories → readable entries: when, who (display name only), which field changed from what to what.
def jira_changelog_entries(histories: list) -> tuple[list[dict], int]:
    """Return (entries oldest first, number of malformed histories skipped).

    Entry: {"id", "at", "author", "changes": [{"field", "from", "to"}]}. Only the human-readable
    values (fromString / toString) are kept; Jira's internal ids and account emails are dropped.
    A value longer than CHANGE_VALUE_CHARS is cut and marked. A history that is not an object or
    has no readable change is skipped and counted, never raised.
    """
    entries, skipped = [], 0
    for history in _list(histories):
        entry = _changelog_entry(history)
        if entry is None:
            skipped += 1
        else:
            entries.append(entry)
    return sorted(entries, key=lambda entry: entry["at"]), skipped


def _changelog_entry(history) -> dict | None:
    if not isinstance(history, dict):
        return None
    changes = [{"field": str(item.get("field") or ""),
                "from": _change_value(item.get("fromString")),
                "to": _change_value(item.get("toString"))}
               for item in _list(history.get("items")) if isinstance(item, dict) and item.get("field")]
    if not changes:
        return None
    return {"id": str(history.get("id") or ""), "at": str(history.get("created") or ""),
            "author": _display_name(history.get("author")), "changes": changes}


def _change_value(value) -> str:
    text = "" if value is None else str(value)
    if len(text) <= CHANGE_VALUE_CHARS:
        return text
    return text[:CHANGE_VALUE_CHARS] + f" … [{len(text) - CHANGE_VALUE_CHARS} more characters]"


# One issue's history outcome → the extensions.changelog value stored on its record.
def changelog_extension(outcome) -> dict:
    """{"status", "entries", "reason"?, "skipped"?} from a Jira.issue_changelogs() outcome.

    "none" (never edited) and "restricted"/"unavailable" (could not read) stay distinct; a missing or
    unrecognised outcome becomes "unavailable" so an unknown state is never reported as "no history".
    """
    if not isinstance(outcome, dict) or outcome.get("status") not in CHANGELOG_STATUSES:
        return {"status": "unavailable", "entries": [], "reason": "history outcome missing or unrecognised"}
    entries, skipped = jira_changelog_entries(outcome.get("histories"))
    extension = {"status": outcome["status"], "entries": entries}
    if outcome.get("reason"):
        extension["reason"] = str(outcome["reason"])
    if skipped:
        extension["skipped"] = skipped
    return extension



# Public name used by the Jira checkpoint and REM importer.
snapshot_hash = _snapshot_hash
