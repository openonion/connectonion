"""Explicit daily/export storage for the read-only OneNote source."""

import json
import re
from datetime import datetime
from pathlib import Path

import yaml

from .._version import __version__
from ..rem.files import atomic_write
from .adapter import AdapterResult, _snapshot_hash, append_daily_jsonl, validate_record
from .onenote_scope import source_config


def prepare_import(source_dir: Path, mode: str, export_id: str | None) -> Path:
    """Validate the destination before any Graph access or filesystem writes."""
    if mode not in {"daily", "export"}:
        raise ValueError("Import mode must be daily or export.")
    if mode == "daily":
        if export_id is not None:
            raise ValueError("--export-id is only valid with --mode export.")
        today = datetime.now().date()
        return source_dir / "daily" / f"{today.year:04d}" / f"{today.month:02d}" / f"{today.day:02d}.jsonl"
    if not export_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", export_id):
        raise ValueError("Export requires --export-id with 1-80 letters, digits, underscores or hyphens.")
    directory = source_dir / "exports" / export_id
    if directory.exists():
        raise ValueError("Export ID already exists. Choose another --export-id; existing exports are preserved.")
    return directory / "records.jsonl"


def page_version(value) -> str:
    """Use the exact Graph timestamp, preserving all fractional digits."""
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
        if stamp.tzinfo:
            return value
    return ""


def snapshot_version(record: dict, *, full: bool = False) -> tuple[str, str]:
    stamp = page_version(record["updated"])
    if stamp and not full:
        return record["id"], stamp
    extensions = {key: value for key, value in record["extensions"].items() if key != "ingestion"}
    return record["id"], _snapshot_hash({**record, "extensions": extensions})


def daily_checkpoint(source_dir: Path, account: str, scope: dict, *, full: bool = False) -> set[tuple[str, str]]:
    """The committed daily snapshots are the checkpoint, including after interruption."""
    versions = set()
    for path in sorted(source_dir.glob("daily/*/*/*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for lineno, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Existing JSONL is corrupted at line {lineno} in {path.name}.") from error
                if validate_record(record):
                    raise ValueError(f"Existing JSONL is corrupted at line {lineno} in {path.name} or uses "
                                     "an incompatible record format. Preserve it and choose a new --output.")
                if (record["source"] != "onenote" or record["account"] != account
                        or record["extensions"].get("scope") != scope):
                    raise ValueError("This source directory belongs to another account or scope. Use a separate --output directory.")
                versions.add(snapshot_version(record, full=full))
    return versions


def write_import(result: AdapterResult, source_dir: Path, target: Path, scope: dict,
                 mode: str, export_id: str | None, command: str) -> dict:
    """Save the shared record contract, selected scope and validation provenance."""
    for record in result.records:
        record["extensions"]["ingestion"] = {"mode": mode, "path": target.relative_to(source_dir).as_posix()}
        problems = validate_record(record)
        if problems:
            raise ValueError("Invalid shared record before storage: " + "; ".join(problems))
    account = result.records[0]["account"]
    config = source_dir / "source.yaml"
    doc = source_config(source_dir, account, scope, command, daily=mode == "daily")
    now = doc["validated_with"]["timestamp"]
    if mode == "daily":
        # Keep classification and actual file consistent if collection crosses midnight.
        date = datetime.strptime(target.relative_to(source_dir).as_posix(), "daily/%Y/%m/%d.jsonl").date()
        target, written = append_daily_jsonl(result.records, source_dir, date=date, keep_versions=True, atomic=True)
        stats = {"written": written, "skipped": len(result.records) - written}
    else:
        # mkdir is exclusive so a concurrent export cannot overwrite an existing ID.
        target.parent.mkdir(parents=True, exist_ok=False)
        atomic_write(target, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in result.records))
        manifest = {"source": "onenote", "account": account, "scope": scope, "export_id": export_id,
                    "created": now, "records": len(result.records), "errors": result.errors,
                    "media_policy": "metadata_only", "connectonion_version": __version__}
        atomic_write(target.parent / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        stats = {"written": len(result.records), "skipped": 0}
    atomic_write(config, yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return {"records": len(result.records), **stats, "errors": result.errors, "jsonl": str(target),
            "source_yaml": str(config), "mode": mode, "registration": "external_import_only",
            "note": ""}


def restore_source_config(source_dir: Path, account: str, scope: dict, command: str) -> Path:
    """Restore the declaration if the daily commit succeeded before its write."""
    config = source_dir / "source.yaml"
    doc = source_config(source_dir, account, scope, command, daily=True)
    atomic_write(config, yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return config
