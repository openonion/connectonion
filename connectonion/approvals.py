"""
Purpose: The record, one append-only line per thing the agent did or declined, for whom, and why
LLM-Note:
  Dependencies: imports from [json, os, datetime, pathlib] | imported by [core/agent.py (_record_trace), network/host/server.py (EXEC, Remote Browser), network/trust/tools.py (trust list changes), cli/commands/approvals_commands.py] | tested by [tests/unit/test_the_record.py]
  Data flow: append(co_dir, entry) → one JSON line at <co_dir>/approvals.jsonl | record_tool(agent, trace_entry) turns a finished tool call into an entry | read(co_dir, who, klass, last) → the newest matching entries
  State/Effects: appends to <co_dir>/approvals.jsonl (mode 0600) | never creates co_dir: an agent without a .co/ keeps no record | never rewrites or truncates, and the agent's own write tools refuse the file (CONTROL_FILES)
  Integration: identity(address) names who asked in #505's namespaces: key:0x…, email:…, chat:<provider>:<sender>, local
  Errors: a torn last line is skipped by read()

Design: #2408. Context over control means most things are done rather than
asked about, so this file is how the owner finds out what was done. It is the
safety net, which is why nothing here can edit or remove a line.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

RECORD = "approvals.jsonl"

# Enough to recognise a call, small enough that one line stays a single
# atomic write when two EXECs append at once.
ARGS_CHARS = 300


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
    """Add one line. An agent with no .co/ directory keeps no record."""
    co_dir = Path(co_dir)
    if not co_dir.is_dir():
        return
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    line = json.dumps({"v": 1, "ts": stamp, **entry}, ensure_ascii=False, default=str) + "\n"
    fd = os.open(co_dir / RECORD, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def short(args) -> str:
    text = json.dumps(args, ensure_ascii=False, default=str) if not isinstance(args, str) else args
    return text if len(text) <= ARGS_CHARS else text[:ARGS_CHARS] + "…"


def record_tool(agent, trace_entry: dict) -> None:
    """One finished tool call in an agent turn."""
    session = agent.current_session or {}
    requester = session.get("requester") or {}
    declined = trace_entry.get("declined", False)
    append(agent.co_dir, {
        "path": "turn",
        "who": identity(requester.get("address")),
        "via": session.get("via"),
        "session": session.get("session_id"),
        "tool": trace_entry.get("name"),
        "args": short(trace_entry.get("args") or {}),
        "decision": "declined" if declined else "done",
        "outcome": trace_entry.get("status"),
        "reason": trace_entry.get("error") if declined else None,
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
        if who and entry.get("who") not in (who, identity(who)):
            continue
        if klass and entry.get("class") != klass:
            continue
        entries.append(entry)
    return entries[-last:]
