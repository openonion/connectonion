"""Private, resumable body snapshots and material indexes for the first co rem pass."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import RemError, atomic_write, read_json, state_path, write_json
from .mail import _address, _addresses


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def message_path(root: Path, provider: str, message_id: str) -> Path:
    if provider not in ("gmail", "outlook") or not message_id:
        raise RemError("Mail archive needs a provider and message ID")
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def archive_init(root: Path, report: dict, clients: dict, progress=None, *, seconds: float | None = None,
                 clock=time.monotonic, now=_utcnow) -> dict:
    """Fetch 90-day provider body snapshots once; keep files if interrupted.

    The inventory is the bounded enumeration. This pass uses its IDs, never a
    second mailbox-wide query, and an existing valid snapshot is reused on a
    retry. Attachments stay outside this first-pass archive.

    `seconds` bounds the fetching (a resume from sync, #2035): when it is
    spent the archive stops at `phase: paused`, and the next resume reuses
    every body saved so far. `updated` is stamped at every checkpoint, so a
    pass whose process died is told apart from one still running.
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
    # Owner-only all the way down: .state is 0700 already, but a directory made
    # by parents=True takes the umask, and these hold other people's mail.
    for folder in ("mail", "mail/messages", "mail/messages/gmail", "mail/messages/outlook",
                   "mail/people", "mail/projects"):
        state_path(root, folder).mkdir(parents=True, exist_ok=True, mode=0o700)
    state = state_path(root, "mail/archive.json")
    result = {"phase": "running", "started": started, "range_start": start.isoformat(),
              "range_end": end.isoformat(), "target": len(messages), "saved": 0,
              "reused": 0, "failed": missing_ids,
              "failed_keys": [{"key": "missing-id", "error": "MissingId"}] if missing_ids else [],
              "people_indexes": 0,
              "project_indexes": 0, "providers": sorted(clients),
              "owner_addresses": (report.get("owner") or {}).get("addresses", []),
              "attachments": "not downloaded", "updated": now().isoformat()}
    write_json(state, result)
    deadline = None if seconds is None else clock() + seconds
    for index, row in enumerate(messages, 1):
        provider, message_id = row["source"], row["id"]
        key = _key(provider + ":" + message_id)
        try:
            path = message_path(root, provider, message_id)
            if path.is_file():
                stored = read_json(path, {})
                if stored.get("provider") != provider or stored.get("id") != message_id:
                    raise RemError("Existing mail snapshot does not match its source ID")
                result["reused"] += 1
            elif deadline is not None and clock() >= deadline:
                result.update(phase="paused", updated=now().isoformat())
                write_json(state, result)
                return {key: value for key, value in result.items() if key not in ("failed_keys", "owner_addresses")}
            else:
                client = clients.get(provider)
                if client is None:
                    raise RemError("Mail provider unavailable during body archive")
                body = client.get_email_body(message_id)
                if not isinstance(body, str):
                    raise RemError("Mail provider returned no text body")
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
            progress(f"saving mail bodies ({result['saved']} saved, {result['reused']} reused, "
                     f"{result['failed']} failed)", f"{index}/{len(messages)}")
        if index % 25 == 0:
            result["updated"] = now().isoformat()
            write_json(state, result)
    result["people_indexes"] = _person_indexes(root, report, messages)
    result["project_indexes"] = _project_indexes(root, report, sessions)
    mail_scan_errors = [error for error in report.get("errors", [])
                        if error.get("source") in ("gmail", "outlook")]
    result["phase"] = ("partial" if result["failed"] or mail_scan_errors else
                       "unavailable" if not clients else "complete")
    result["finished"] = result["updated"] = now().isoformat()
    write_json(state, result)
    summary = state_path(root, "mail/summary.md")
    atomic_write(summary, "\n".join(["# Initial mail materials", "",
                                      f"Range: {start.date()} to {end.date()} ({report['days']} days)",
                                      f"Status: {result['phase']}",
                                      f"Messages observed: {result['target']}",
                                      f"Bodies saved: {result['saved']}; reused: {result['reused']}; failed: {result['failed']}",
                                      f"People indexes: {result['people_indexes']}; project indexes: {result['project_indexes']}",
                                      "Bodies are private provider-rendered snapshots; attachments are not downloaded.",
                                      "No mail body is placed in a shareable notebook page.", ""]) + "\n")
    return {key: value for key, value in result.items() if key not in ("failed_keys", "owner_addresses")}


def _material_item(snapshot: dict, own: set) -> dict:
    from .mail import strip_noise, strip_quoted
    provider, message_id = snapshot["provider"], snapshot["id"]
    sender = str(snapshot.get("from") or "")
    body = str(snapshot.get("body") or "")
    head, _, rest = body.partition("--- Email Body ---")
    text = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
    sender_address = _address(sender)
    return {"role": "user" if sender_address in own or "@" not in sender_address else "other",
            "speaker": sender, "text": text, "timestamp": snapshot.get("date", ""),
            "subject": snapshot.get("subject", ""), "source": f"{provider}:{_key(message_id)[:12]}",
            "_mail_id": message_id}


def _material(manifest: dict, snapshots: list[dict]) -> tuple[dict[str, list[dict]], datetime, datetime]:
    own = {address.casefold() for address in manifest.get("owner_addresses", [])}
    by_provider: dict[str, list[dict]] = {provider: [] for provider in manifest.get("providers", [])}
    for snapshot in snapshots:
        by_provider.setdefault(snapshot["provider"], []).append(_material_item(snapshot, own))
    return (by_provider, datetime.fromisoformat(manifest["range_start"]),
            datetime.fromisoformat(manifest["range_end"]))


def person_material(root: Path, record: str) -> tuple[dict[str, list[dict]], datetime, datetime] | None:
    """Read a complete local archive for one mapped page, without a provider query."""
    manifest = read_json(state_path(root, "mail/archive.json"), {})
    index = person_index_path(root, record)
    if manifest.get("phase") != "complete" or not index.is_file():
        return None
    snapshots = []
    for line in index.read_text(encoding="utf-8").splitlines():
        ref = json.loads(line)
        snapshot = read_json(state_path(root, ref["message"].removeprefix(".state/")), {})
        if (not isinstance(snapshot, dict) or snapshot.get("id") != ref["id"]
                or snapshot.get("provider") != ref["provider"] or "body" not in snapshot):
            return None
        snapshots.append(snapshot)
    return _material(manifest, snapshots)


def domain_material(root: Path, domains: list[str]) -> tuple[dict[str, list[dict]], datetime, datetime] | None:
    """An org's mail from the complete local archive: every snapshot a domain is on.

    People get an index at init; an org has none, so UNSW's page said "0 loaded
    from private init archive" and listed 3,800 headers from the providers
    instead (#1963). Each snapshot carries its own from/to/cc, so reading them
    is the index: a few thousand small local files, not a mailbox walked a week
    at a time. `.sub.domain` counts too -- student.unsw.edu.au is UNSW.
    """
    manifest = read_json(state_path(root, "mail/archive.json"), {})
    if manifest.get("phase") != "complete" or not domains:
        return None
    suffixes = tuple(f"{sep}{domain}" for domain in domains for sep in ("@", "."))
    snapshots = []
    for provider in manifest.get("providers", []):
        for path in sorted(state_path(root, f"mail/messages/{provider}").glob("*.json")):
            snapshot = read_json(path, {})
            if not isinstance(snapshot, dict) or snapshot.get("provider") != provider or "body" not in snapshot:
                return None
            addresses = [_address(snapshot.get("from", "")), *_addresses(snapshot.get("to")),
                         *_addresses(snapshot.get("cc"))]
            if any(address.endswith(suffixes) for address in addresses):
                snapshots.append(snapshot)
    return _material(manifest, snapshots)


# No checkpoint for this long means no process is saving: init stamps `updated`
# every 25 messages, seconds apart.
STALL_SECONDS = 600
# What one sync may spend resuming it: the rest waits for the next sync.
RESUME_SECONDS = 300


def archive_state(root: Path, now: datetime | None = None) -> dict | None:
    """An unfinished init archive, as status and doctor show it; None when there is none (#2035).

    The 1.9.0a6 acceptance notebook's archive sat at `phase: running`, 550 of
    3,152 bodies saved, for a day: every investigation skipped it and asked the
    mail servers, and nothing said so. `on_disk` counts the snapshots that exist,
    which is what a resume reuses.
    """
    path = state_path(root, "mail/archive.json")
    manifest = read_json(path, {})
    if not isinstance(manifest, dict) or manifest.get("phase") not in ("running", "paused"):
        return None
    now = now or _utcnow()
    updated = manifest.get("updated") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    stalled = (now - datetime.fromisoformat(updated)).total_seconds() > STALL_SECONDS
    on_disk = sum(1 for provider in manifest.get("providers", []) if provider in ("gmail", "outlook")
                  for _ in state_path(root, f"mail/messages/{provider}").glob("*.json"))
    target = manifest.get("target", 0)
    if stalled:
        summary = (f"Mail archive incomplete: {on_disk} of {target} bodies saved, no progress since "
                   f"{updated[:16]}; investigations ask the mail servers until it is done. The next "
                   f"`co rem sync` resumes it from the saved bodies.")
    else:
        summary = f"Mail archive saving: {on_disk} of {target} bodies so far."
    return {"phase": manifest["phase"], "target": target, "on_disk": on_disk, "updated": updated,
            "stalled": stalled, "summary": summary}


def resume_stalled(root: Path, clients: dict, *, seconds: float = RESUME_SECONDS, clock=time.monotonic,
                   now=_utcnow) -> dict | None:
    """Continue a stalled or paused init archive for at most `seconds`; None when there is nothing to do.

    It reuses every body already on disk (`archive_init` checks each one) and
    reads the inventory the map last wrote, so it asks no server for a list.
    A mailbox it cannot open leaves the archive as it is, and says so.
    """
    state = archive_state(root, now=now())
    if not state or not state["stalled"]:
        return None
    report = read_json(state_path(root, "map.json"), {})
    if not report.get("started") or not state_path(root, "source-inventory.jsonl").is_file():
        return None
    providers = read_json(state_path(root, "mail/archive.json"), {}).get("providers", [])
    missing = [provider for provider in providers if clients.get(provider) is None]
    if missing:
        return {"phase": state["phase"], "resumed": False, "reason": f"{', '.join(missing)} unavailable"}
    return archive_init(root, report, {provider: clients[provider] for provider in providers},
                        seconds=seconds, clock=clock, now=now)
