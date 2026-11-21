"""Read local canonical snapshots for the candidate-only Init modes."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..useful_tools.adapter import record_reference, validate_record
from .files import RemError


def candidate_id(*identity: str) -> str:
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield None


def load_imports(root: Path) -> tuple[list[tuple[dict, str]], list[dict]]:
    """Select the latest valid snapshot per ID and retain its immutable citation."""
    latest, errors = {}, []
    for source in ("jira", "onenote"):
        directory = root / "docs" / source
        files = sorted([*directory.glob("daily/*/*/*.jsonl"),
                        *directory.glob("exports/*/records.jsonl")])
        for path in files:
            try:
                relative = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError as error:
                raise RemError("Imported record files must stay inside the notebook") from error
            for row, record in enumerate(_rows(path), 1):
                problems = validate_record(record)
                if problems or record["source"] != source:
                    errors.append({"file": relative, "row": row,
                                   "reason": "Invalid canonical record or source"})
                    continue
                rank = (_time(record["updated"] or record["at"]), _time(record["fetched"]))
                key = record["id"]
                if key not in latest or rank >= latest[key][0]:
                    latest[key] = (rank, record, record_reference(path, record, root))
    return [(latest[key][1], latest[key][2]) for key in sorted(latest)], errors


def candidate_report(rows, candidates, unresolved, errors) -> dict:
    if candidates or unresolved:
        status = "candidates" if candidates else "insufficient_input"
    else:
        status = "insufficient_input" if rows or errors else "empty_input"
    return {"status": status, "records": len(rows),
            "candidates": sorted(candidates, key=lambda item: item["id"]),
            "unresolved": sorted(unresolved, key=lambda item: item["id"]), "errors": errors}
