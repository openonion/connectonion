"""Private, resumable body snapshots and material indexes for the first Wiki pass."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import WikiError, atomic_write, read_json, state_path, write_json
from .mail import _address, _addresses


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def message_path(root: Path, provider: str, message_id: str) -> Path:
    if provider not in ("gmail", "outlook") or not message_id:
        raise WikiError("Mail archive needs a provider and message ID")
    return state_path(root, f"mail/messages/{provider}/{_key(message_id)}.json")


def person_index_path(root: Path, record: str) -> Path:
    return state_path(root, f"mail/people/{_key(record)}.jsonl")


def project_index_path(root: Path, record: str) -> Path:
    return state_path(root, f"mail/projects/{_key(record)}.jsonl")


def _jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def _person_indexes(root: Path, report: dict, messages: list[dict]) -> int:
    address_to_record = {}
    for person in report.get("people", []):
        for address in person.get("addresses", []):
            address_to_record[address.casefold()] = person["record"]
    owner = report.get("owner") or {}
    for address in owner.get("addresses", []):
        address_to_record[address.casefold()] = owner["record"]
    pages = {row["record"] for row in report.get("people", [])}
    pages.update([owner["record"]] if owner.get("record") else [])
    indexes = {record: [] for record in pages}
    for row in messages:
        found = {}
        for role, addresses in (("from", [_address(row.get("from", ""))]),
                                ("to", _addresses(row.get("to"))),
                                ("cc", _addresses(row.get("cc")))):
            for address in addresses:
                record = address_to_record.get(address)
                if record:
                    found.setdefault(record, set()).add(role)
        for record, roles in found.items():
            indexes[record].append({"provider": row["source"], "id": row["id"],
                                    "date": row.get("date", ""), "roles": sorted(roles),
                                    "message": str(message_path(root, row["source"], row["id"]).relative_to(root))})
    for record, rows in indexes.items():
        _jsonl(person_index_path(root, record), sorted(rows, key=lambda item: (item["date"], item["id"])))
    return len(indexes)


def _project_indexes(root: Path, report: dict, sessions: list[dict]) -> int:
    indexes = {}
    for project in report.get("projects", []):
        paths = set(project.get("paths", []))
        rows = [{"source": row["source"], "path": row["path"], "modified": row["modified"]}
                for row in sessions if row.get("cwd") in paths]
        _jsonl(project_index_path(root, project["record"]), rows)
        indexes[project["record"]] = len(rows)
    return len(indexes)


def archive_init(root: Path, report: dict, clients: dict, progress=None) -> dict:
    """Fetch 90-day provider body snapshots once; keep files if interrupted.

    The inventory is the bounded enumeration. This pass uses its IDs, never a
    second mailbox-wide query, and an existing valid snapshot is reused on a
    retry. Attachments stay outside this first-pass archive.
    """
    inventory = state_path(root, "source-inventory.jsonl")
    rows = [json.loads(line) for line in inventory.read_text(encoding="utf-8").splitlines() if line]
    missing_ids = sum(row.get("type") == "mail" and not row.get("id") for row in rows)
    messages = list({(row["source"], row["id"]): row for row in rows
                     if row.get("type") == "mail" and row.get("id")}.values())
    sessions = [row for row in rows if row.get("type") == "session"]
    started = report["started"]
    end = datetime.fromisoformat(started)
    start = end - timedelta(days=report["days"])
    state = state_path(root, "mail/archive.json")
    result = {"phase": "running", "started": started, "range_start": start.isoformat(),
              "range_end": end.isoformat(), "target": len(messages), "saved": 0,
              "reused": 0, "failed": missing_ids,
              "failed_keys": [{"key": "missing-id", "error": "MissingId"}] if missing_ids else [],
              "people_indexes": 0,
              "project_indexes": 0, "providers": sorted(clients),
              "owner_addresses": (report.get("owner") or {}).get("addresses", []),
              "attachments": "not downloaded"}
    write_json(state, result)
    for index, row in enumerate(messages, 1):
        provider, message_id = row["source"], row["id"]
        key = _key(provider + ":" + message_id)
        try:
            path = message_path(root, provider, message_id)
            if path.is_file():
                stored = read_json(path, {})
                if stored.get("provider") != provider or stored.get("id") != message_id:
                    raise WikiError("Existing mail snapshot does not match its source ID")
                result["reused"] += 1
            else:
                client = clients.get(provider)
                if client is None:
                    raise WikiError("Mail provider unavailable during body archive")
                body = client.get_email_body(message_id)
                if not isinstance(body, str):
                    raise WikiError("Mail provider returned no text body")
                snapshot = {"provider": provider, "id": message_id, "date": row.get("date", ""),
                            "from": row.get("from", ""), "to": row.get("to", []), "cc": row.get("cc", []),
                            "subject": row.get("subject", ""), "body": body,
                            "body_format": "provider-rendered text, not original MIME",
                            "fetched_at": datetime.now(timezone.utc).isoformat()}
                write_json(path, snapshot)
                result["saved"] += 1
        except Exception as error:  # A single unavailable message must not discard the map.
            result["failed"] += 1
            result["failed_keys"].append({"key": key, "error": type(error).__name__})
        if progress and (index == 1 or index % 25 == 0 or index == len(messages)):
            progress(f"Mail bodies: {index}/{len(messages)} checked; {result['saved']} saved, "
                     f"{result['reused']} reused, {result['failed']} failed")
        if index % 25 == 0:
            write_json(state, result)
    result["people_indexes"] = _person_indexes(root, report, messages)
    result["project_indexes"] = _project_indexes(root, report, sessions)
    mail_scan_errors = [error for error in report.get("errors", [])
                        if error.get("source") in ("gmail", "outlook")]
    result["phase"] = ("partial" if result["failed"] or mail_scan_errors else
                       "unavailable" if not clients else "complete")
    result["finished"] = datetime.now(timezone.utc).isoformat()
    write_json(state, result)
    summary = state_path(root, "mail/summary.md")
    atomic_write(summary, "\n".join(["# Initial mail materials", "",
                                      f"Range: {start.date()} to {end.date()} ({report['days']} days)",
                                      f"Status: {result['phase']}",
                                      f"Messages observed: {result['target']}",
                                      f"Bodies saved: {result['saved']}; reused: {result['reused']}; failed: {result['failed']}",
                                      f"People indexes: {result['people_indexes']}; project indexes: {result['project_indexes']}",
                                      "Bodies are private provider-rendered snapshots; attachments are not downloaded.",
                                      "No mail body is placed in a shareable Wiki page.", ""]) + "\n")
    return {key: value for key, value in result.items() if key not in ("failed_keys", "owner_addresses")}


def person_material(root: Path, record: str) -> tuple[dict[str, list[dict]], datetime, datetime] | None:
    """Read a complete local archive for one mapped page, without a provider query."""
    manifest = read_json(state_path(root, "mail/archive.json"), {})
    if manifest.get("phase") != "complete":
        return None
    index = person_index_path(root, record)
    if not index.is_file():
        return None
    own = {address.casefold() for address in manifest.get("owner_addresses", [])}
    by_provider: dict[str, list[dict]] = {provider: [] for provider in manifest.get("providers", [])}
    from .mail import strip_noise, strip_quoted
    for line in index.read_text(encoding="utf-8").splitlines():
        ref = json.loads(line)
        snapshot = read_json(state_path(root, ref["message"].removeprefix(".state/")), {})
        if (not isinstance(snapshot, dict) or snapshot.get("id") != ref["id"]
                or snapshot.get("provider") != ref["provider"] or "body" not in snapshot):
            return None
        provider, message_id = snapshot["provider"], snapshot["id"]
        sender = str(snapshot.get("from") or "")
        body = str(snapshot.get("body") or "")
        head, _, rest = body.partition("--- Email Body ---")
        text = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
        sender_address = _address(sender)
        by_provider.setdefault(provider, []).append({"role": "user" if sender_address in own or "@" not in sender_address else "other",
                                                     "speaker": sender, "text": text,
                                                     "timestamp": snapshot.get("date", ""),
                                                     "subject": snapshot.get("subject", ""),
                                                     "source": f"{provider}:{_key(message_id)[:12]}",
                                                     "_mail_id": message_id})
    return (by_provider, datetime.fromisoformat(manifest["range_start"]),
            datetime.fromisoformat(manifest["range_end"]))
