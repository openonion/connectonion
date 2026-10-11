"""
Purpose: The record, one append-only line per thing the agent did or declined, for whom, and why
LLM-Note:
  Dependencies: imports from [json, os, re, datetime, pathlib] | imported by [core/agent.py (_record_trace), network/host/server.py (EXEC, Remote Browser), network/trust/tools.py (trust list changes), cli/commands/approvals_commands.py] | tested by [tests/unit/test_the_record.py]
  Data flow: append(co_dir, entry) → one JSON line at <co_dir>/approvals.jsonl | record_tool(agent, trace_entry) turns a finished tool call into an entry | read(co_dir, who, klass, last) → the newest matching entries
  State/Effects: appends to <record_dir>/approvals.jsonl (mode 0600): Agent.record_dir is state_dir, else co_dir, and None with log=False | never creates the directory, and skips one it cannot write | tokens and secret-named assignments are redacted first | never rewrites or truncates, and the agent's own write tools refuse the file (CONTROL_FILES)
  Integration: identity(address) names who asked in #505's namespaces: key:0x…, email:…, chat:<provider>:<sender>, local
  Errors: a torn last line is skipped by read()

Design: #2408. Context over control means most things are done rather than
asked about, so this file is how the owner finds out what was done. It is the
safety net, which is why nothing here can edit or remove a line.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

RECORD = "approvals.jsonl"

# Enough to recognise a call; the record says what ran, not everything it said.
ARGS_CHARS = 300

# The record is append-only and the agent cannot edit it, so a secret written
# here could only be scrubbed by hand. Tokens and assignments to secret-named
# variables are cut before they are written.
_SECRETS = re.compile(
    r"(?i)\b(sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[abpr]-[A-Za-z0-9-]{8,}|AKIA[A-Z0-9]{12,})"
    r"|(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"
    r"|(\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*\s*[=:]\s*)[^\s\"',]+"
)


def _redact(text: str) -> str:
    return _SECRETS.sub(lambda m: (m.group(2) or m.group(3) or "") + "***", text)


def identity(address: str | None) -> str:
    """Who asked, in #505's namespaces. No address means a local caller."""
    if not address:
        return "local"
    if address.startswith("0x"):
        return f"key:{address}"
    if ":" not in address and "@" in address:
        return f"email:{address}"
    return f"chat:{address}"


def append(co_dir: Path, entry: dict) -> None:
    """Add one line. An agent with no writable .co/ directory keeps no record.

    It runs after the call has had its effects, so it must not be the thing that
    fails: a read-only mount or someone else's .co/ means no record, not a
    broken tool call.
    """
    co_dir = Path(co_dir)
    if not co_dir.is_dir() or not os.access(co_dir, os.W_OK):
        return
    record = co_dir / RECORD
    if record.exists() and not os.access(record, os.W_OK):
        return
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    line = json.dumps({"v": 1, "ts": stamp, **entry}, ensure_ascii=False, default=str) + "\n"
    fd = os.open(record, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def short(args) -> str | None:
    if args is None:
        return None
    text = _redact(json.dumps(args, ensure_ascii=False, default=str) if not isinstance(args, str) else args)
    return text if len(text) <= ARGS_CHARS else text[:ARGS_CHARS] + "…"


def record_tool(agent, trace_entry: dict) -> None:
    """One finished tool call in an agent turn."""
    record_dir = getattr(agent, "record_dir", None)
    if record_dir is None or not trace_entry.get("name"):
        return  # log=False, or a provider event that names no tool
    session = agent.current_session or {}
    requester = session.get("requester") or {}
    status = trace_entry.get("status")
    declined = trace_entry.get("declined", False)
    ran = status not in ("not_found", "interrupted") and not declined
    append(record_dir, {
        "path": "turn",
        "who": identity(requester.get("address")),
        "via": session.get("via"),
        "session": session.get("session_id"),
        "tool": trace_entry.get("name"),
        "args": short(trace_entry.get("args") or {}),
        "decision": "done" if ran else "declined",
        "outcome": status,
        "reason": short(trace_entry.get("error")) if not ran else None,
        "ms": int(trace_entry.get("timing_ms") or 0),
    })


def read(co_dir: Path, who: str | None = None, klass: str | None = None, last: int = 50) -> list[dict]:
    """The newest `last` entries, oldest first, optionally for one identity or class."""
    path = Path(co_dir) / RECORD
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn last line from a crash mid-append
        if who and not {who, identity(who)} & {entry.get("who"), entry.get("subject")}:
            continue
        if klass and entry.get("class") != klass:
            continue
        entries.append(entry)
    return entries[-last:] if last > 0 else []
