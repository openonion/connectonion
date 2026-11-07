"""Jira-only mapping to the co rem source-record envelope."""

from __future__ import annotations

import datetime
import json
from pathlib import Path


def record_id(account: str, issue_key: str) -> str:
    return f"jira:{account.split('://', 1)[-1].rstrip('/')}:{issue_key}"


def jira_records(issues: list[dict], account: str) -> tuple[list[dict], dict[str, str]]:
    records, errors = [], {}
    fetched = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for index, issue in enumerate(issues):
        key = str(issue.get("key") or "") if isinstance(issue, dict) else ""
        fields = issue.get("fields") if isinstance(issue, dict) else None
        if not key or not isinstance(fields, dict):
            errors[f"jira:item-{index}"] = "mapping error: malformed issue"
            continue
        description = fields.get("description")
        text = description if isinstance(description, str) else ""
        if isinstance(description, dict):
            text = _adf_text(description)
        record = {"id": record_id(account, key), "source": "jira", "account": account,
                  "external_id": key, "kind": _name(fields.get("issuetype")) or "issue",
                  "title": str(fields.get("summary") or ""), "text": text,
                  "url": f"{account}/browse/{key}", "author": _display(fields.get("reporter") or fields.get("creator")),
                  "at": str(fields.get("created") or ""), "updated": str(fields.get("updated") or ""),
                  "fetched": fetched,
                  "extensions": {"status": _name(fields.get("status")), "priority": _name(fields.get("priority")),
                                 "labels": [str(item) for item in fields.get("labels", []) if isinstance(item, str)]}}
        records.append(record)
    return records, errors


def append_daily(records: list[dict], source_dir: Path) -> tuple[Path, int]:
    today = datetime.date.today()
    target = Path(source_dir) / "daily" / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    seen.add(str(json.loads(line).get("id") or ""))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Existing JSONL is malformed: {target}") from exc
    fresh = []
    for record in records:
        if record["id"] not in seen:
            seen.add(record["id"])
            fresh.append(record)
    if fresh:
        with target.open("a", encoding="utf-8") as stream:
            for record in fresh:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target, len(fresh)


def _name(value: object) -> str:
    return str(value.get("name") or "") if isinstance(value, dict) else ""


def _display(value: object) -> str:
    return str(value.get("displayName") or "") if isinstance(value, dict) else ""


def _adf_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    def visit(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content", []) if isinstance(node.get("content"), list) else []:
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    return " ".join(parts)
