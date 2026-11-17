"""
Purpose: A small file for an agent `co send` cannot reach directly waits on the backend, boxed to it, for a week
LLM-Note:
  Dependencies: imports from [base64, hashlib, json, time, datetime, pathlib, requests, nacl, backend.py, credentials.py, handoff/sealing.py (_box), network/host/file_inbox.py (landing, trust bar), network/trust/tools.py] | imported by [cli/commands/send_commands.py] | tested by [tests/unit/test_co_send_leaves_a_small_file_waiting.py]
  Data flow: leave(keys, to, path, name) → box(meta) + box(bytes) → POST /api/v1/files | collect(keys, co_dir) → GET /api/v1/files → per file: trusted sender? → GET bytes → unbox (proves the sender) → sha256 == meta → land in .co/inbox/files/<date>/ + received.jsonl → DELETE on the backend
  State/Effects: leave() stores one file on the backend | collect() writes files and received.jsonl lines under the project's .co/inbox/files/ and deletes what it landed from the backend
  Integration: exposes leave(), collect(), STASH_BYTES, KEPT_DAYS
  Performance: one request per file; a file is at most STASH_BYTES and is held in memory once
  Errors: leave() raises SendRefused with the backend's reason | collect() leaves a file from an untrusted sender waiting and reports it; a box that does not open or a sha256 that does not match is deleted and reported

`co send` sends directly when it can (network/file_send.py). When the receiver is
behind a router or its Host is not running, a file of up to STASH_BYTES waits on
the backend instead (#3088). The backend holds a NaCl box to the receiver, and the
name and sha256 boxed separately, so it never sees a name or a byte of the file.

The receiver takes files only from senders it would take a direct send from: a
contact, a whitelisted address or an admin. The box proves who sent it, so the
backend's `from_address` is never trusted on its own.
"""

import base64
import hashlib
import json
import time
from datetime import date
from pathlib import Path

STASH_BYTES = 10 * 1024 * 1024
KEPT_DAYS = 7


def _headers() -> dict:
    from ..credentials import require_ambient_api_key
    return {"Authorization": f"Bearer {require_ambient_api_key()}"}


def leave(keys, to_address: str, path: Path, name: str) -> dict:
    """Leave `path` waiting for `to_address` as `name`; the backend's record."""
    import requests

    from ..backend import backend_url
    from ..handoff.sealing import _box
    from .file_send import SendRefused

    data = path.read_bytes()
    box = _box(keys["signing_key"], to_address)
    meta = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    response = requests.post(
        f"{backend_url()}/api/v1/files", params={"to": to_address}, data=bytes(box.encrypt(data)),
        headers={**_headers(), "X-File-Meta": base64.b64encode(bytes(box.encrypt(json.dumps(meta).encode()))).decode(),
                 "Content-Type": "application/octet-stream"},
        timeout=120,
    )
    if response.status_code == 404:
        raise SendRefused("the backend does not hold files yet, so this cannot wait for the receiver")
    if response.status_code in (400, 413):
        raise SendRefused(response.json()["detail"])
    response.raise_for_status()
    return {**response.json(), **meta}


def collect(keys, co_dir: Path) -> dict:
    """Take every file waiting for this agent. {"landed": [...], "waiting": [...], "refused": [...]}."""
    import requests

    from ..backend import backend_url

    response = requests.get(f"{backend_url()}/api/v1/files", headers=_headers(), timeout=30)
    if response.status_code == 404:
        return {"landed": [], "waiting": [], "refused": []}
    response.raise_for_status()
    found = {"landed": [], "waiting": [], "refused": []}
    for row in response.json()["files"]:
        if not _trusted(row["from_address"], co_dir):
            found["waiting"].append({"from": row["from_address"], "size": row["size"], "expires_at": row["expires_at"]})
            continue
        outcome, entry = _take(keys, co_dir, row)
        found[outcome].append(entry)
    return found


def _trusted(sender: str, co_dir: Path) -> bool:
    from .host.file_inbox import SEND_REQUIRES
    from .trust.tools import get_level, is_admin
    return is_admin(sender, co_dir) or get_level(sender, co_dir) in SEND_REQUIRES


def _take(keys, co_dir: Path, row: dict) -> tuple[str, dict]:
    import requests
    from nacl.exceptions import CryptoError

    from ..backend import backend_url
    from ..handoff.sealing import _box

    url = f"{backend_url()}/api/v1/files/{row['id']}"
    response = requests.get(url, headers=_headers(), timeout=120)
    response.raise_for_status()
    box = _box(keys["signing_key"], row["from_address"])
    try:
        meta = json.loads(box.decrypt(base64.b64decode(row["meta"])))
        data = box.decrypt(response.content)
    except CryptoError:
        requests.delete(url, headers=_headers(), timeout=30).raise_for_status()
        return "refused", {"from": row["from_address"], "reason": "not boxed by its sender; deleted"}
    if hashlib.sha256(data).hexdigest() != meta["sha256"] or len(data) != meta["size"]:
        requests.delete(url, headers=_headers(), timeout=30).raise_for_status()
        return "refused", {"from": row["from_address"], "name": meta["name"], "reason": "sha256 does not match; deleted"}
    from .host.file_inbox import FileRefused
    try:
        entry = _land(co_dir, row["from_address"], meta, data)
    except FileRefused as refused:   # an unsafe name; a direct send refuses it at the offer
        requests.delete(url, headers=_headers(), timeout=30).raise_for_status()
        return "refused", {"from": row["from_address"], "name": meta["name"], "reason": f"{refused}; deleted"}
    requests.delete(url, headers=_headers(), timeout=30).raise_for_status()
    return "landed", entry


def _land(co_dir: Path, sender: str, meta: dict, data: bytes) -> dict:
    """Write it where a direct send lands, and record it the same way."""
    from .host.file_inbox import _landing, files_dir, safe_name

    root = files_dir(co_dir)
    target = _landing(root / date.today().isoformat(), safe_name(meta["name"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(data)
    partial.replace(target)
    entry = {"from": sender, "name": meta["name"], "size": meta["size"], "sha256": meta["sha256"],
             "path": target.relative_to(root).as_posix(), "at": int(time.time()), "via": "backend"}
    with (root / "received.jsonl").open("a") as log:
        log.write(json.dumps(entry) + "\n")
    return entry
