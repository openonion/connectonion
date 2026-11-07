"""Consented notebook-local Granola snapshots, shared by map, investigate and sync.

The Granola CLI owns remote collection. This reader never loads credentials or polls
Granola; its subscription pins the declared account and selected scope.
"""
import json
import re
from pathlib import Path

import yaml

from ..useful_tools.adapter import snapshot_hash, record_id, record_reference, validate_record
from .files import Notebook, RemError
from .imported_candidates import _time
from .imported_evidence import evidence_material
from .source import Batch


def _safe(root: Path, path: Path) -> Path:
    root = root.resolve()
    if not path.is_relative_to(root) or path.resolve() != path:
        raise RemError("Granola import paths must stay inside the notebook without symlinks")
    return path


def identity(root: Path) -> dict:
    """Read only the source declaration; never a record body, even on add/consent."""
    path = _safe(root, root.resolve() / "docs/granola/source.yaml")
    if not path.is_file():
        raise RemError("Import selected Granola notes into this notebook's docs/granola first; see `co granola import --help`")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as error:
        raise RemError("Invalid Granola source.yaml; preserve it for diagnosis") from error
    if not isinstance(doc, dict) or doc.get("driver") != "granola" or doc.get("schema_version", 1) not in (1, 2):
        raise RemError("Expected a Granola source declaration with schema version 1 or 2")
    from ..useful_tools.granola import validate_profile
    account, scope = doc.get("account"), doc.get("scope")
    try:
        validate_profile(account)
    except ValueError as error:
        raise RemError("Invalid Granola profile") from error
    if not isinstance(scope, dict) or not isinstance(scope.get("folder_id"), str) or not scope["folder_id"].strip():
        raise RemError("Invalid selected Granola personal folder")
    if doc.get("media_policy") != "metadata_only":
        raise RemError("Granola REM requires metadata-only media policy")
    limit = scope.get("limit", 1000)
    note = scope.get("note_id")
    if (type(limit) is not int or not 1 <= limit <= 1000
            or (note is not None and (not isinstance(note, str) or not note.strip() or limit != 1))):
        raise RemError("Invalid Granola selected note/limit scope")
    selected = {"folder_id": scope["folder_id"], "limit": limit}
    if type(scope.get("include_children", False)) is not bool:
        raise RemError("Invalid Granola include_children scope")
    if scope.get("include_children"):
        selected["include_children"] = True
    if note is not None:
        selected["note_id"] = note
    return {"account": account, "folder_id": scope["folder_id"], "scope": selected,
            **({"credential_binding": doc["credential_binding"]} if doc.get("credential_binding") else {})}


def snapshot_rows(root: Path, sub: dict) -> list[tuple[dict, str]]:
    """Latest complete record per stable ID; any corrupt/foreign row fails closed."""
    if not sub.get("enabled") or not sub.get("consented"):
        return []
    declared = identity(root)
    if declared != sub.get("import_identity"):
        raise RemError("Granola source declaration changed; review it, then re-add granola and approve with `co rem init --no-start`")
    directory = root.resolve() / "docs/granola"
    from ..useful_tools.granola_collection import record_in_folder_scope
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
                    raise RemError(f"Invalid Granola JSONL row {number}; preserve the import for diagnosis") from error
                if (validate_record(row) or row["source"] != "granola" or row["account"] != declared["account"]
                        or row["id"] != record_id("granola", row["account"], row["external_id"])
                        or not record_in_folder_scope(row, declared["folder_id"], declared["scope"].get("include_children", False))
                        or (declared["scope"].get("note_id") and row["external_id"] != declared["scope"]["note_id"])
                        or row["extensions"].get("summary_kind") != "generated_summary"
                        or row.get("media")
                        or row["author"]
                        or set(row["extensions"]) - {"folder_id", "folder_name", "scheduled_start", "scheduled_end", "summary_kind", "collection_root_folder_id", "collection_folder_path"}):
                    raise RemError(f"Invalid or out-of-scope Granola record at row {number}; source progress preserved")
                rank = (_time(row["updated"] or row["at"]), _time(row["fetched"]))
                # Keep the first citation for identical copies in daily/export files.
                prior = latest.get(row["id"])
                if prior is None or rank >= prior[0]:
                    same = prior is not None and snapshot_hash(row) == snapshot_hash(prior[1])
                    latest[row["id"]] = (rank, row, prior[2] if same else record_reference(path, row, root))
    return [(value[1], value[2]) for _, value in sorted(latest.items())]


def item(root: Path, row: dict, reference: str) -> dict:
    return {"role": "original", "source": "adapter:" + reference, "source_kind": "granola",
            "timestamp": row["updated"] or row["at"] or row["fetched"],
            "text": evidence_material([row])[0]}


def collect_granola(root: Path, sub: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not isinstance(progress, dict):
        raise RemError("Invalid Granola source progress; preserve it for diagnosis")
    rows = snapshot_rows(root, sub)
    if not sub.get("enabled") or not sub.get("consented"):
        return Batch([], dict(progress))
    versions = progress.get("versions", {})
    if not isinstance(versions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in versions.items()):
        raise RemError("Invalid Granola source progress; preserve it for diagnosis")
    seen = dict(versions)
    items = []
    for row, reference in rows:
        if len(items) >= max_items:
            break
        version = snapshot_hash(row)
        if seen.get(row["id"]) == version:
            continue
        material = item(root, row, reference)
        size = len(json.dumps(material, ensure_ascii=False))
        if size > max_chars:
            if not items and max_items > 0:
                raise RemError("A Granola record exceeds the input budget; increase the configured batch limits, then retry")
            break
        items.append(material)
        max_chars -= size
        seen[row["id"]] = version
    return Batch(items, {"versions": seen})


def map_granola(root: Path, sub: dict, report: dict) -> None:
    """Inventory imports without pretending folders or titles are projects."""
    rows = snapshot_rows(root, sub)
    report["coverage"].append(f"granola: {len(rows)} selected local snapshots; no remote polling; semantic organization during normal Maintain")


def investigation_items(root: Path, sub: dict, record: str, start, end) -> list[dict]:
    """Gather cited evidence or title matches as leads, never identity proof."""
    notebook = Notebook(root)
    page = notebook.read(record)
    # Current upstream keeps source definitions in Markdown rather than exposing
    # the later Reader helper used by the GitLab feature branch.  Read only the
    # canonical Granola references we created; a citation never becomes an
    # identity claim merely because its record ID appears on a page.
    cited = set(re.findall(
        r"(?:adapter:)?docs/granola/[^\s?#]+\.jsonl#([^?\s]+)\?version=[0-9a-f]{64}", page))
    title = next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), "")
    result = []
    for row, ref in snapshot_rows(root, sub):
        mentioned = bool(title and len(title) >= 3 and re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", row["text"], re.I))
        if (row["id"] in cited or mentioned) and start <= _time(row["updated"] or row["at"] or row["fetched"]) < end:
            result.append(item(root, row, ref))
    return result


def canonical_sources(text: str) -> str:
    """Normalize a free-form inline Sources spelling to Reader definitions."""
    text = re.sub(r"(?m)^(?:##[ \t]+)?Sources?:?[ \t]*$(?=\n(?:[ \t]*\n)*[ \t]*(?:[-*][ \t]*)?(?:\[W?\d+\]|\d+\.)[ \t]+(?:adapter:)?docs/granola/)",
                  "## Sources", text)
    pattern = r"(?m)^Sources:[ \t]*\[(W?\d+)\][ \t]+((?:adapter:)?docs/granola/[^\s]+\?version=[0-9a-f]{64})([^\n]*)$"
    return re.sub(pattern, lambda m: "## Sources\n- [" + m[1] + "] " + m[2]
                  + (" — " + m[3].strip(" —–") if m[3].strip() else ""), text)
