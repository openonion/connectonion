"""Consented notebook-local OneNote snapshots, shared by map, investigate and sync.

The OneNote CLI owns remote collection. This reader never loads credentials or polls
OneNote; its subscription pins the declared account and selected scope.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..useful_tools.adapter import snapshot_hash, record_id, record_reference, validate_record
from .files import Notebook, RemError
from .imported_evidence import evidence_material
from .source import Batch


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _safe(root: Path, path: Path) -> Path:
    root = root.resolve()
    if not path.is_relative_to(root) or path.resolve() != path:
        raise RemError("OneNote import paths must stay inside the notebook without symlinks")
    return path


def identity(root: Path) -> dict:
    """Read only the source declaration; never a record body, even on add/consent."""
    path = _safe(root, root.resolve() / "docs/onenote/source.yaml")
    if not path.is_file():
        raise RemError("Import selected OneNote notes into this notebook's docs/onenote first; see `co onenote source sync --help`")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as error:
        raise RemError("Invalid OneNote source.yaml; preserve it for diagnosis") from error
    if not isinstance(doc, dict) or doc.get("driver") != "onenote" or doc.get("schema_version", 1) not in (1, 2):
        raise RemError("Expected a OneNote source declaration with schema version 1 or 2")
    account, scope = doc.get("account"), doc.get("scope")
    if not isinstance(account, str) or not account.strip() or not isinstance(scope, dict):
        raise RemError("Invalid OneNote account or scope")
    pages = scope.get("pages")
    if (not isinstance(pages, list) or not pages or any(not isinstance(v, str) or not v.strip() for v in pages)
            or any(scope.get(k) is not None and not isinstance(scope.get(k), str) for k in ("notebook", "section"))):
        raise RemError("Invalid selected OneNote page scope")
    return {"account": account, "scope": {**scope, "pages": sorted(set(pages))}}


def snapshot_rows(root: Path, sub: dict) -> list[tuple[dict, str]]:
    """Latest complete record per stable ID; any corrupt/foreign row fails closed."""
    if not sub.get("enabled") or not sub.get("consented"):
        return []
    declared = identity(root)
    if declared != sub.get("import_identity"):
        raise RemError("OneNote source declaration changed; review it, then re-add onenote and approve with `co rem init --no-start`")
    directory = root.resolve() / "docs/onenote"
    latest = {}
    files = sorted([*directory.glob("daily/*/*/*.jsonl"), *directory.glob("exports/*/records.jsonl")])
    for path in files:
        _safe(root, path)
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise RemError(f"Invalid OneNote JSONL row {number}; preserve the import for diagnosis") from error
                if (validate_record(row) or row["source"] != "onenote" or row["account"] != declared["account"]
                        or row["id"] != record_id("onenote", row["account"], row["external_id"])
                        or row["external_id"] not in declared["scope"]["pages"]
                        or not isinstance(row["extensions"].get("scope"), dict)
                        or any(row["extensions"]["scope"].get(k) != declared["scope"].get(k) for k in ("notebook", "section"))
                        or ("pages" in row["extensions"]["scope"] and (
                            not isinstance(row["extensions"]["scope"]["pages"], list)
                            or row["external_id"] not in row["extensions"]["scope"]["pages"]
                            or any(v not in declared["scope"]["pages"] for v in row["extensions"]["scope"]["pages"])))):
                    raise RemError(f"Invalid or out-of-scope OneNote record at row {number}; source progress preserved")
                rank = (_time(row["updated"] or row["at"]), _time(row["fetched"]))
                # Keep the first citation for identical copies in daily/export files.
                prior = latest.get(row["id"])
                if prior is None or rank >= prior[0]:
                    same = prior is not None and snapshot_hash(row) == snapshot_hash(prior[1])
                    latest[row["id"]] = (rank, row, prior[2] if same else record_reference(path, row, root))
    return [(value[1], value[2]) for _, value in sorted(latest.items())]


def item(root: Path, row: dict, reference: str) -> dict:
    return {"role": "original", "source": "adapter:" + reference, "source_kind": "onenote",
            "timestamp": row["updated"] or row["at"] or row["fetched"],
            "text": evidence_material([row])[0]}


def collect_onenote(root: Path, sub: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not isinstance(progress, dict):
        raise RemError("Invalid OneNote source progress; preserve it for diagnosis")
    rows = snapshot_rows(root, sub)
    if not sub.get("enabled") or not sub.get("consented"):
        return Batch([], dict(progress))
    versions = progress.get("versions", {})
    if not isinstance(versions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in versions.items()):
        raise RemError("Invalid OneNote source progress; preserve it for diagnosis")
    seen = dict(versions)
    items = []
    for row, reference in rows:
        if len(items) >= max_items:
            break
        version = snapshot_hash({**row, "extensions": {k: v for k, v in row["extensions"].items() if k != "ingestion"}})
        if seen.get(row["id"]) == version:
            continue
        material = item(root, row, reference)
        size = len(json.dumps(material, ensure_ascii=False))
        if size > max_chars:
            if not items and max_items > 0:
                raise RemError("A OneNote record exceeds the input budget; increase the configured batch limits, then retry")
            break
        items.append(material)
        max_chars -= size
        seen[row["id"]] = version
    return Batch(items, {"versions": seen})


def map_onenote(root: Path, sub: dict, report: dict) -> None:
    """Inventory imports without pretending folders or titles are projects."""
    rows = snapshot_rows(root, sub)
    report["coverage"].append(f"onenote: {len(rows)} selected local snapshots; no remote polling; semantic organization during normal Maintain")


def investigation_items(root: Path, sub: dict, record: str, start, end) -> list[dict]:
    """Gather cited evidence or title matches as leads, never identity proof."""
    from .reader_model import source_references
    notebook = Notebook(root)
    page = notebook.read(record)
    from .source_links import _citation
    cited = {parsed[1] for _, value in source_references(page)
             if (parsed := _citation(value)) and not parsed[-1]}
    title = next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), "")
    result = []
    for row, ref in snapshot_rows(root, sub):
        mentioned = bool(title and len(title) >= 3 and re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", row["text"], re.I))
        if (row["id"] in cited or mentioned) and start <= _time(row["updated"] or row["at"] or row["fetched"]) < end:
            result.append(item(root, row, ref))
    return result


def canonical_sources(text: str) -> str:
    """Normalize a free-form inline Sources spelling to Reader definitions."""
    text = re.sub(r"(?m)^(?:##[ \t]+)?Sources?:?[ \t]*$(?=\n(?:[ \t]*\n)*[ \t]*(?:[-*][ \t]*)?(?:\[W?\d+\]|\d+\.)[ \t]+(?:adapter:)?docs/onenote/)",
                  "## Sources", text)
    pattern = r"(?m)^Sources:[ \t]*\[(W?\d+)\][ \t]+((?:adapter:)?docs/onenote/[^\s]+\?version=[0-9a-f]{64})([^\n]*)$"
    return re.sub(pattern, lambda m: "## Sources\n- [" + m[1] + "] " + m[2]
                  + (" — " + m[3].strip(" —–") if m[3].strip() else ""), text)


def pinned_record(root: Path, source: str) -> dict | None:
    """Resolve a validated immutable OneNote original, without network or a model."""
    from ..useful_tools.adapter import resolve_reference
    reference = source.removeprefix("adapter:")
    relative, marker, wanted = reference.partition("#")
    if (not marker or not relative.startswith("docs/onenote/")
            or not relative.endswith(".jsonl") or not re.search(r"\?version=[0-9a-f]{64}$", wanted)):
        return None
    path = root.resolve() / relative
    if not path.is_relative_to(root.resolve()) or path.resolve() != path:
        return None
    record = resolve_reference(reference, root)
    return record if record is not None and not validate_record(record) and record["source"] == "onenote" else None


def evidence_item(root: Path, source: str) -> dict | None:
    """Use full canonical JSON for claim review, preserving the record budget."""
    record = pinned_record(root, source)
    return item(root, record, source.removeprefix("adapter:")) if record is not None else None
