"""
Purpose: A small file for an agent `co send` cannot reach directly waits on the backend, boxed to it, for a week
LLM-Note:
  Dependencies: imports from [base64, hashlib, json, time, datetime, pathlib, requests, nacl, backend.py, credentials.py, handoff/sealing.py (_box), network/host/file_inbox.py (landing, trust bar), network/trust/tools.py] | imported by [cli/commands/send_commands.py] | tested by [tests/unit/test_co_send_leaves_a_small_file_waiting.py]
  Data flow: _headers(keys) signs in as exactly those keys | leave(keys, to, path, name) → box(meta with a nonce) + box(bytes) → POST /api/v1/files | collect(keys, co_dir) → GET /api/v1/files → per file: trusted sender? → GET bytes → unbox (proves the sender) → sha256 == meta → nonce already in received.jsonl? → room on disk? → stage in .partial/backend/, link into .co/inbox/files/<date>/ + received.jsonl → DELETE on the backend
  State/Effects: leave() stores one file on the backend | collect() writes files and received.jsonl lines under the project's .co/inbox/files/ and deletes what it landed from the backend
  Integration: exposes leave(), collect(), STASH_BYTES, KEPT_DAYS
  Performance: one request per file; a file is at most STASH_BYTES and is held in memory once
  Errors: leave() raises SendRefused with the backend's reason | collect() leaves a file from an untrusted sender, or one with no room for it, waiting and reports it; a box that does not open, a meta that is not ours, a sha256 that does not match or an unsafe name is deleted and reported; a file gone meanwhile (404) is skipped | network errors propagate

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
import os
import secrets
import shutil
import time
from datetime import date
from pathlib import Path

STASH_BYTES = 10 * 1024 * 1024
KEPT_DAYS = 7
# What a NaCl box adds to what it seals: the backend's size is the box's.
BOX_OVERHEAD = 40


_tokens: dict = {}


def _headers(keys) -> dict:
    """A token for exactly `keys`, which also seal and open the boxes.

    The ambient OPENONION_API_KEY belongs to ~/.co, while a project with its own
    key sends and receives as that key. Boxing as one and listing as the other
    left files nobody could find, so each identity signs in for itself.
    """
    if keys["address"] not in _tokens:
        from ..backend import backend_url
        from .agent_auth import signed_agent_token

        _tokens[keys["address"]] = signed_agent_token(keys, backend_url())
    return {"Authorization": f"Bearer {_tokens[keys['address']]}"}


def leave(keys, to_address: str, path: Path, name: str) -> dict:
    """Leave `path` waiting for `to_address` as `name`; the backend's record."""
    import requests

    from ..backend import backend_url
    from ..handoff.sealing import _box
    from .file_send import SendRefused

    data = path.read_bytes()
    box = _box(keys["signing_key"], to_address)
    # The nonce is what the receiver remembers, so a box delivered twice lands once.
    meta = {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "nonce": secrets.token_hex(16)}
    response = requests.post(
        f"{backend_url()}/api/v1/files", params={"to": to_address}, data=bytes(box.encrypt(data)),
        headers={**_headers(keys), "Content-Type": "application/octet-stream",
                 "X-File-Meta": base64.b64encode(bytes(box.encrypt(json.dumps(meta).encode()))).decode()},
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

    found = {"landed": [], "waiting": [], "refused": []}
    response = requests.get(f"{backend_url()}/api/v1/files", headers=_headers(keys), timeout=30)
    if response.status_code == 404:
        return found
    response.raise_for_status()
    for row in response.json()["files"]:
        if not _trusted(row["from_address"], co_dir):
            found["waiting"].append({"from": row["from_address"], "size": row["size"] - BOX_OVERHEAD,
                                     "expires_at": row["expires_at"], "reason": "not a contact"})
            continue
        outcome, entry = _take(keys, co_dir, row)
        if outcome:
            found[outcome].append(entry)
    return found


def _trusted(sender: str, co_dir: Path) -> bool:
    from .host.file_inbox import SEND_REQUIRES
    from .trust.tools import get_level, is_admin
    return is_admin(sender, co_dir) or get_level(sender, co_dir) in SEND_REQUIRES


def _take(keys, co_dir: Path, row: dict) -> tuple[str | None, dict]:
    """("landed" | "refused" | "waiting" | None, entry) for one waiting file; None when it is gone."""
    import requests

    from ..backend import backend_url

    url = f"{backend_url()}/api/v1/files/{row['id']}"
    response = requests.get(url, headers=_headers(keys), timeout=120)
    if response.status_code == 404:   # the sender took it back, or another co receive has it
        return None, {}
    response.raise_for_status()
    outcome, entry = _open(keys, co_dir, row, response.content)
    if outcome != "waiting":
        gone = requests.delete(url, headers=_headers(keys), timeout=30)
        if gone.status_code != 404:
            gone.raise_for_status()
    return outcome, entry


def _open(keys, co_dir: Path, row: dict, blob: bytes) -> tuple[str, dict]:
    from nacl.exceptions import CryptoError

    from ..handoff.sealing import _box
    from .host.file_inbox import DISK_MARGIN_BYTES, FileRefused, files_dir, received

    sender = row["from_address"]
    box = _box(keys["signing_key"], sender)
    try:
        meta = json.loads(box.decrypt(base64.b64decode(row["meta"])))
        name, size, sha256, nonce = meta["name"], meta["size"], meta["sha256"], meta["nonce"]
        data = box.decrypt(blob)
    except (CryptoError, ValueError, KeyError, TypeError):
        return "refused", {"from": sender, "reason": "not a file its sender boxed for this agent; deleted"}
    if hashlib.sha256(data).hexdigest() != sha256 or len(data) != size:
        return "refused", {"from": sender, "name": name, "reason": "sha256 does not match; deleted"}
    root = files_dir(co_dir)
    root.mkdir(parents=True, exist_ok=True)
    already = next((e for e in received(co_dir) if e.get("nonce") == nonce and e["from"] == sender), None)
    if already:   # landed before the backend copy was deleted, or delivered again
        return "landed", already
    if shutil.disk_usage(root).free - size < DISK_MARGIN_BYTES:
        return "waiting", {"from": sender, "size": size, "expires_at": row["expires_at"],
                           "reason": "less than 1 GB would be left free on this disk"}
    try:
        return "landed", _land(root, sender, meta, data)
    except FileRefused as refused:   # an unsafe name; a direct send refuses it at the offer
        return "refused", {"from": sender, "name": name, "reason": f"{refused}; deleted"}


def _land(root: Path, sender: str, meta: dict, data: bytes) -> dict:
    """Write it where a direct send lands, never over anything there, and record it the same way."""
    from .host.file_inbox import _landing, safe_name

    staging = root / ".partial" / "backend"
    staging.mkdir(parents=True, exist_ok=True)
    partial = staging / f"{meta['nonce']}.{os.getpid()}.part"
    partial.write_bytes(data)
    while True:
        target = _landing(root / date.today().isoformat(), safe_name(meta["name"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(partial, target)   # fails if anything took the name meanwhile; replace would overwrite it
            break
        except FileExistsError:
            continue
    partial.unlink()
    entry = {"from": sender, "name": meta["name"], "size": meta["size"], "sha256": meta["sha256"],
             "path": target.relative_to(root).as_posix(), "at": int(time.time()), "via": "backend",
             "nonce": meta["nonce"]}
    with (root / "received.jsonl").open("a") as log:
        log.write(json.dumps(entry) + "\n")
    return entry
