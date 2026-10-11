"""
Purpose: The append-only record of what an agent did, and refused, for whom (#2408)
LLM-Note:
  Dependencies: imports from [json, re, datetime, pathlib] | imported by [approval.py check_approval and record_remote_result, network/host/http_router.py exec_handler] | tested by [tests/unit/test_special_classes.py]
  Data flow: record(co_dir, ...) → one JSON line appended to <co_dir>/decisions.jsonl
  State/Effects: appends to .co/decisions.jsonl (a protected control file: the agent's own tools cannot write it)
  Integration: exposes record(), RECORD_FILE
  Errors: lets OSError bubble — a record that silently failed would be worse than a loud one

Context over control means the agent acts, and the owner reads what happened
afterwards. So the record is the safety net, and it has three rules:

- every entry says who asked, at what level, what ran, and how it ended;
- it is appended, never rewritten, and the agent's own file tools may not
  touch it (it is in approval.CONTROL_FILES);
- it holds no secrets: arguments that look like credentials are replaced,
  and long values are cut, so the record is safe to read and share.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

RECORD_FILE = "decisions.jsonl"
_SECRET_NAME = re.compile(r"pass(word|wd)?|secret|token|api_?key|credential|private", re.I)
_MAX_VALUE = 300


def _summary(args: dict) -> dict:
    shown = {}
    for name, value in (args or {}).items():
        if name == "agent":
            continue
        if _SECRET_NAME.search(str(name)):
            shown[name] = "[redacted]"
            continue
        text = value if isinstance(value, (int, float, bool)) or value is None else str(value)
        if isinstance(text, str) and len(text) > _MAX_VALUE:
            text = text[:_MAX_VALUE] + f"… [{len(text) - _MAX_VALUE} more chars]"
        shown[name] = text
    return shown


def record(co_dir, *, path: str, tool: str, args: dict, outcome: str, reason: str = "",
           requester: dict | None = None, special: dict | None = None) -> dict:
    """Append one decision and return it.

    path: where the call came from ("exec" or "turn").
    outcome: "executed", "failed" or "refused".
    """
    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path": path,
        "requester": (requester or {}).get("address"),
        "level": (requester or {}).get("level"),
        "tool": tool,
        "args": _summary(args),
        "outcome": outcome,
        "reason": reason,
    }
    if special:
        entry["special"] = {"class": special["class"], "kind": special["kind"]}
    folder = Path(co_dir)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / RECORD_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
