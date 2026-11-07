"""Consented notebook-local Jira snapshots, shared by map, investigate and sync.

The Jira CLI owns remote collection. This reader never loads credentials or polls
Jira; its subscription pins the declared account and issue/project scope.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from ..useful_tools.adapter import snapshot_hash, record_id, record_reference, validate_record
from .files import Notebook, RemError
from .imported_candidates import candidate_id, _time
from .imported_evidence import evidence_material
from .source import Batch


def _safe(root: Path, path: Path) -> Path:
    root = root.resolve()
    if not path.is_relative_to(root) or path.resolve() != path:
        raise RemError("Jira import paths must stay inside the notebook without symlinks")
    return path


def identity(root: Path) -> dict:
    """Read only the source declaration; never a record body, even on add/consent."""
    path = _safe(root, root.resolve() / "docs/jira/source.yaml")
    if not path.is_file():
        raise RemError("Import selected Jira issues into this notebook's docs/jira first; see `co jira sync --help`")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeError) as error:
        raise RemError("Invalid Jira source.yaml; preserve it for diagnosis") from error
    if not isinstance(doc, dict) or doc.get("driver") != "jira" or doc.get("schema_version", 1) not in (1, 2):
        raise RemError("Expected a Jira source declaration with schema version 1 or 2")
    account = doc.get("account")
    url = urlsplit(account) if isinstance(account, str) else None
    if not url or url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise RemError("Jira source account must be an HTTPS site without credentials")
    if doc.get("schema_version", 1) == 2:
        scope = doc.get("canonical_scope")
        if not isinstance(scope, dict):
            raise RemError("Invalid Jira canonical scope")
        projects, issues = [scope.get("project")], scope.get("keys", [])
        if scope.get("type") not in ("project", "project+keys") or (scope.get("type") == "project+keys" and not issues):
            raise RemError("Invalid Jira canonical scope type")
        authorised = doc.get("authorised_identity")
        if not isinstance(authorised, dict) or not isinstance(authorised.get("accountId"), str) or not authorised["accountId"].strip():
            raise RemError("Invalid Jira authorised identity")
    else:
        scope = doc.get("scope")
        if not isinstance(scope, dict):
            raise RemError("Invalid Jira selected scope")
        projects, issues, authorised = scope.get("projects"), scope.get("issues"), None
    if (not isinstance(projects, list) or not projects or any(not isinstance(p, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", p) for p in projects)
            or not isinstance(issues, list) or any(not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", k)
                or k.rsplit("-", 1)[0] not in projects for k in issues)
            or (doc.get("schema_version", 1) == 1 and not issues)):
        raise RemError("Invalid Jira project/issue scope")
    return {"account": account, "projects": sorted(set(projects)), "issues": sorted(set(issues)),
            "authorised_identity": authorised}


def snapshot_rows(root: Path, sub: dict) -> list[tuple[dict, str]]:
    """Latest complete record per stable ID; any corrupt/foreign row fails closed."""
    if not sub.get("enabled") or not sub.get("consented"):
        return []
    declared = identity(root)
    if declared != sub.get("import_identity"):
        raise RemError("Jira source declaration changed; review it, then re-add jira and approve with `co rem init --no-start`")
    directory = root.resolve() / "docs/jira"
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
                    raise RemError(f"Invalid Jira JSONL row {number}; preserve the import for diagnosis") from error
                if (validate_record(row) or row["source"] != "jira" or row["account"] != declared["account"]
                        or row["id"] != record_id("jira", row["account"], row["external_id"])
                        or row["external_id"].rsplit("-", 1)[0] not in declared["projects"]
                        or (declared["issues"] and row["external_id"] not in declared["issues"])):
                    raise RemError(f"Invalid or out-of-scope Jira record at row {number}; source progress preserved")
                rank = (_time(row["updated"] or row["at"]), _time(row["fetched"]))
                # Keep the first citation for identical copies in daily/export files.
                prior = latest.get(row["id"])
                if prior is None or rank >= prior[0]:
                    same = prior is not None and snapshot_hash(row) == snapshot_hash(prior[1])
                    latest[row["id"]] = (rank, row, prior[2] if same else record_reference(path, row, root))
    return [(value[1], value[2]) for _, value in sorted(latest.items())]


def entities(row: dict) -> list[dict]:
    """Only explicit, source-qualified identity: no fuzzy name merging."""
    project = row["external_id"].rsplit("-", 1)[0]
    found = [{"category": "projects", "name": project,
              "id": candidate_id("project", "jira", row["account"], project)}]
    fields = row["extensions"]
    people = fields.get("people")
    for role in ("reporter", "assignee"):
        native = people.get(role) if isinstance(people, dict) else None
        name = fields.get(role) or (row["author"] if role == "reporter" else "")
        if isinstance(native, str) and native.strip() and isinstance(name, str) and name.strip() and "\n" not in name and "\r" not in name:
            found.append({"category": "people", "name": name.strip(),
                          "id": candidate_id("person", "jira", row["account"], native)})
    return found


def entity_record(notebook: Notebook, entity: dict) -> str:
    from .map import _record
    proposed = _record(entity["category"], entity["name"], entity["id"])
    suffix = "-" + Path(proposed).name.rsplit("-", 1)[-1]
    matches = [page for page in notebook.list(entity["category"]) if Path(page).name.endswith(suffix)]
    if len(matches) > 1:
        raise RemError("Multiple REM pages share a Jira identity; resolve the duplicates before reading")
    return matches[0] if matches else proposed


def item(root: Path, row: dict, reference: str) -> dict:
    notebook = Notebook(root)
    return {"role": "original", "source": "adapter:" + reference, "source_kind": "jira",
            "timestamp": row["updated"] or row["at"] or row["fetched"],
            "target_records": sorted({entity_record(notebook, entity) for entity in entities(row)}),
            "text": evidence_material([row])[0]}


def collect_jira(root: Path, sub: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    if not isinstance(progress, dict):
        raise RemError("Invalid Jira source progress; preserve it for diagnosis")
    rows = snapshot_rows(root, sub)
    if not sub.get("enabled") or not sub.get("consented"):
        return Batch([], dict(progress))
    versions = progress.get("versions", {})
    if not isinstance(versions, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in versions.items()):
        raise RemError("Invalid Jira source progress; preserve it for diagnosis")
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
                raise RemError("A Jira record exceeds the input budget; increase the configured batch limits, then retry")
            break
        items.append(material)
        max_chars -= size
        seen[row["id"]] = version
    return Batch(items, {"versions": seen})


def map_jira(root: Path, sub: dict, report: dict) -> None:
    """Add canonical stubs to the existing map; never rewrite an authored page."""
    rows = snapshot_rows(root, sub)
    notebook = Notebook(root)
    mapped = {}
    for row, reference in rows:
        for entity in entities(row):
            one = mapped.setdefault(entity["id"], {**entity, "evidence": [], "last": ""})
            one["evidence"].append(reference)
            stamp = row["updated"] or row["at"] or row["fetched"]
            if _time(stamp) >= _time(one["last"]):
                one.update(name=entity["name"], last=stamp)
    for entity in mapped.values():
        record = entity_record(notebook, entity)
        made = (notebook.stub_person(record, entity["name"]) if entity["category"] == "people"
                else notebook.stub_project(record, entity["name"]))
        if made:
            report["created"].append(record)
        report[entity["category"]].append({"record": record, "name": entity["name"],
            "import_id": entity["id"], "evidence": entity["evidence"], "paths": [],
            "addresses": [], "last": entity["last"]})
    report["coverage"].append(f"jira: {len(rows)} selected local snapshots; no remote polling")


def investigation_items(root: Path, sub: dict, record: str, start, end) -> list[dict]:
    result = []
    for row, ref in snapshot_rows(root, sub):
        material = item(root, row, ref)
        if record in material["target_records"] and start <= _time(material["timestamp"]) < end:
            result.append(material)
    return result
