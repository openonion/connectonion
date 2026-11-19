"""The reader's Investigate button (#3105): a page's state, and the one run it starts.

The button's label follows the page: Investigate (never investigated), Update ·
N new mails or sessions (material since its last investigation), Dig deeper ·
N leads (the last enrich left open leads), Up to date. A click runs the public
CLI, `co rem investigate PAGE --enrich`, in a detached worker, never an agent
turn of its own; the reader follows it through this module, which reads the
same run records `co rem logs` shows. One run per page at a time.
"""

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from .files import Notebook, RemError, read_json, state_path, write_json
from .service import now

# The ⋯ menu's levels, as CLI flags: 完整调查 (default) · 快速更新 · 整页重写.
MODES = {"full": ["--enrich"], "quick": [], "rewrite": ["--rewrite"]}
KINDS = ("people/", "orgs/", "projects/")
OPEN_LEAD = re.compile(r"(?m)^\s*[-*]\s*open\s*\|")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def receipt_path(root, record: str) -> Path:
    if not record.startswith(KINDS) or ".." in Path(record).parts:
        raise RemError(f"{record}: the Investigate button is for people, orgs and projects pages")
    return state_path(Path(root), f"page-runs/{Path(record).with_suffix('.json')}")


def command(root, record: str, mode: str) -> list[str]:
    if mode not in MODES:
        raise RemError(f"Unknown investigation level {mode!r}; expected full, quick or rewrite")
    return [sys.executable, "-m", "connectonion.cli.main", "rem", "--root", str(root), "--json",
            "investigate", record, *MODES[mode]]


def _alive(receipt: dict) -> bool:
    """The worker still runs: its PID still shows our command. A finished worker the Host has not
    reaped is a zombie that answers kill(pid, 0); its command line is gone, so it reads as ended."""
    from .live_host import _alive as command_alive
    return command_alive(receipt)


def start(root, record: str, mode: str = "full") -> dict:
    """Start the run, or return the one already running for this page."""
    from .investigate import last_investigated
    root = Path(root).resolve()
    command(root, record, mode)  # validates the level
    path, book = receipt_path(root, record), Notebook(root)
    if not book.exists(record):
        raise RemError(f"{record} is no longer in your notebook. Reload the page")
    if record == _owner(root):
        raise RemError("Your own page is written from what you sent: run co rem investigate me")
    saved = read_json(path, {})
    if saved.get("result") == "running" and _alive(saved):
        return status(root, record)
    text = book.read(record)
    first = "append" if last_investigated(text) and mode != "rewrite" else "rewrite" if mode == "rewrite" else "write"
    receipt = {"record": record, "mode": mode, "steps": [first, *(["enrich"] if mode == "full" else [])],
               "result": "running", "started_at": now().isoformat(), "before_sha256": _sha(text),
               "before_chars": len(text), "log": str(path.with_suffix(".log"))}
    path.parent.mkdir(parents=True, exist_ok=True)
    from .runner import child_env
    worker = [sys.executable, "-m", "connectonion.rem.page_runs", "--root", str(root), "--record", record, "--mode", mode]
    with open(receipt["log"], "ab") as output:
        process = subprocess.Popen(worker, cwd=str(root), env=child_env(), stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    receipt.update(pid=process.pid, command=" ".join(worker[1:]))
    write_json(path, receipt)
    return status(root, record)


def _owner(root) -> str:
    return (read_json(state_path(Path(root), "map.json"), {}).get("owner") or {}).get("record", "")


def _work(root: Path, record: str, mode: str) -> None:
    """The worker: run the CLI, then write how it ended. The receipt is its only output."""
    path = receipt_path(root, record)
    from .runner import child_env
    done = subprocess.run(command(root, record, mode), cwd=str(root), env=child_env(), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    receipt = read_json(path, {})
    reply = {}
    try:
        reply = json.loads((done.stdout or "{}").strip().splitlines()[-1] if (done.stdout or "").strip() else "{}")
    except ValueError:
        pass
    receipt.update(result="completed" if done.returncode == 0 else "failed", exit_code=done.returncode,
                   finished_at=now().isoformat())
    if done.returncode:
        receipt.update(explain(_message(reply) or _last_line(done.stderr)))
    write_json(path, receipt)


def _message(reply) -> str:
    """The error the CLI printed with --json: {"ok": false, "data": <words or a result>} (rem_commands._emit)."""
    if not isinstance(reply, dict) or reply.get("ok", True):
        return ""
    data = reply.get("data")
    if isinstance(data, dict):
        data = data.get("error") or data.get("reason") or data.get("message") or ""
    return data if isinstance(data, str) else ""


def _last_line(stderr: str) -> str:
    """The last line on stderr that is not a progress line ("Investigation: writing investigation")."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    said = [line for line in lines if not line.startswith("Investigation: ")]
    return (said or lines or [""])[-1]


# Why a run stopped, in words the reader can show: a kind it says in the owner's language, and a plain
# sentence. It once showed "['Investigation: writing investigation']", a Python list of a progress line.
REASONS = [
    ("too_long", re.compile(r"Page is ([\d,]+) characters \(was ([\d,]+)\)"),
     "The page is too long to add to ({0} characters); the draft is kept and nothing on the page changed."),
    ("changed", re.compile(r"Page changed during investigation"),
     "The page changed while it was being investigated; nothing was written. Run it again."),
    ("dropped", re.compile(r"Dropped (?:claim line|quote|source id) the page had"),
     "The draft left out lines the page had, so it was not saved; nothing on the page changed."),
]


def explain(message: str) -> dict:
    """{"reason": a plain sentence, "reason_kind": what kind}: never a list or a traceback."""
    message = " ".join(str(message or "").split())
    for kind, pattern, sentence in REASONS:
        if match := pattern.search(message):
            return {"reason": sentence.format(*match.groups()), "reason_kind": kind}
    return {"reason": (message[:300] or "The investigation stopped without saying why."), "reason_kind": "other"}


def _unlisted(reason: str) -> str:
    """A reason an older worker stored as str(list) ("['Investigation: writing investigation']"), as its words,
    without the progress lines; anything else as it is."""
    text = str(reason or "").strip()
    if text.startswith("[") and text.endswith("]"):
        import ast
        try:
            items = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
        if isinstance(items, list):
            return " ".join(str(item) for item in items if not str(item).startswith("Investigation: "))
    return text


def _readable(receipt: dict, progress: list[dict]) -> dict:
    """A failed receipt's reason as a sentence and a kind (#3155): receipts written before rc28 kept the raw text.
    The run's own recorded error is preferred when the stored reason says nothing (a progress line)."""
    if receipt.get("result") != "failed" or receipt.get("reason_kind"):
        return {}
    for error in [row["error"] for row in progress if row.get("error")] + [_unlisted(receipt.get("reason"))]:
        said = explain(error)
        if said["reason_kind"] != "other" or (error and not error.startswith("Investigation: ")):
            return said
    return explain("")


def _progress(root: Path, receipt: dict, logs: list[dict]) -> list[dict]:
    """Each step of this click, from the run records it made: write/append (or rewrite), then enrich."""
    runs = sorted((run for run in logs if run.get("record") == receipt["record"]
                   and run.get("started_at", "") >= receipt["started_at"]), key=lambda run: run["started_at"])
    rows = []
    for step in receipt["steps"]:
        phase = "enrich" if step == "enrich" else "investigate"
        run = next((run for run in runs if run.get("phase") == phase), None)
        state = ("waiting" if run is None else "running" if run.get("outcome") == "running"
                 else "done" if run.get("outcome") in ("completed", "nothing_new") else "failed")
        rows.append({"step": step, "state": state, "stage": (run or {}).get("stage", ""),
                     "outcome": (run or {}).get("outcome", ""), "error": str((run or {}).get("error", ""))[:300]})
    if receipt["result"] != "running":
        for row in rows:
            row["state"] = "skipped" if row["state"] in ("waiting", "running") else row["state"]
    return rows


def _added(before: str, after: str) -> list[str]:
    """The lines the run added or changed, compared without citation numbers: renumbering is not a change.

    The first live run (2026-11-18) said "30 lines added" for 25: five lines differed only in their [n]."""
    from .page_review import _line_key
    old = {_line_key(line) for line in before.splitlines()}
    lines = [line for line in after.splitlines() if line.strip() and _line_key(line) not in old
             and not line.startswith(("Investigation:", "- [", "## "))]
    return [re.sub(r"\s*(?:\[W?\d+\](?!\()\s*)+", " ", line).strip() for line in lines]


def status(root, record: str, *, logs=None) -> dict:
    from . import page_versions
    from .service import run_logs
    root = Path(root)
    path = receipt_path(root, record)
    receipt = read_json(path, {})
    if not receipt:
        raise RemError(f"No investigation was started from the reader for {record}")
    if receipt["result"] == "running" and not _alive(receipt):
        receipt = read_json(path, {})  # the worker may have finished between the reads
        if receipt["result"] == "running":
            receipt.update(result="failed", reason="The investigation stopped without saying how it ended; "
                                                   "see co rem logs", finished_at=now().isoformat())
            write_json(path, receipt)
    progress = _progress(root, receipt, run_logs(root) if logs is None else logs)
    value = {**receipt, **_readable(receipt, progress), "progress": progress}
    if receipt["result"] != "running":
        book = Notebook(root)
        after = book.read(record) if book.exists(record) else ""
        previous = page_versions.previous(root, record)
        added = _added(previous["text"], after) if previous and _sha(after) != receipt["before_sha256"] else []
        # The organisations this run linked, and whether it made their pages (#3141).
        from .org_links import new_org_links
        orgs = [{**org, "created": book.exists(org["record"]) and "not investigated yet" in book.read(org["record"])}
                for org in (new_org_links(previous["text"], after) if previous and _sha(after) != receipt["before_sha256"] else [])]
        value.update(changed=_sha(after) != receipt["before_sha256"], added_lines=added[:40], added_count=len(added), orgs=orgs,
                     undo=page_versions.can_undo(root, record),
                     rewrite=_draft(root, record))
    return value


def _draft(root, record):
    from . import page_versions
    saved = page_versions.waiting_rewrite(root, record)
    return {"drafted_at": saved["drafted_at"], "chars": saved.get("chars")} if saved else None


def undo(root, record: str) -> dict:
    from . import page_versions
    return page_versions.undo(root, record)


def accept(root, record: str) -> dict:
    from . import page_versions
    return page_versions.accept_rewrite(root, record)


def discard(root, record: str) -> dict:
    from . import page_versions
    return page_versions.discard_rewrite(root, record)


def _mail_days(root: Path, records: list[str], book: Notebook) -> dict[str, list[str]]:
    """{record: [day of each mail exchanged]} for people (their addresses) and orgs (their domains)."""
    from .investigate import org_domains
    from .relationship_stats import contact_messages
    from .store import _rows
    from .store_messages import owner_addresses
    owner = owner_addresses(root)
    if not owner:
        return {}
    rows = _rows(root, "select json_group_array(json_array(id, thread, sender, json(recipients), substr(time, 1, 10))) "
                       "as mail from (select id, thread, sender, recipients, time from messages "
                       "where thread like 'mail:%' and time != '')")
    messages = json.loads(rows[0]["mail"]) if rows and rows[0].get("mail") else []
    wanted = set(records)
    people = [{"record": p["path"], "emails": p["emails"]} for p in book.people() if p["path"] in wanted]
    days = {record: [m[4] for m in found] for record, found in contact_messages(messages, people, owner).items()}
    domains = {record: org_domains(book.read(record)) for record in records if record.startswith("orgs/")}
    for record, names in domains.items():
        if not names:
            continue
        suffixes = tuple("@" + name.casefold() for name in names)
        days[record] = [m[4] for m in messages
                        if any(address.casefold().endswith(suffixes)
                               for address in ({*m[3]} - owner if m[2].casefold() in owner else {m[2]}))]
    return days


def _points(run: dict | None) -> float | None:
    if not run:
        return None
    from .quota import group_points
    points = group_points([run])
    return round(points, 1) if points else None


def states(root, records: list[str], *, mail_days=None) -> dict[str, dict]:
    """What the Investigate button says for each page; no model, no network."""
    from .investigate import last_investigated
    from .service import run_logs
    root, book = Path(root), Notebook(root)
    # Your own page has its own pass (investigate me), not this button.
    records = [record for record in records if record.startswith(KINDS) and book.exists(record) and record != _owner(root)]
    logs = run_logs(root)
    mail_days = _mail_days(root, records, book) if mail_days is None else mail_days
    found = {}
    for record in records:
        last = last_investigated(book.read(record))
        mine = [run for run in logs if run.get("record") == record and run.get("outcome") == "completed"]
        enrich = next((run for run in mine if run.get("phase") == "enrich" and run.get("report")), None)
        investigate = next((run for run in mine if run.get("phase") == "investigate"), None)
        new_mails = sum(day > last.isoformat() for day in mail_days.get(record, [])) if last else 0
        new_sessions = _new_sessions(root, record) if last and record.startswith("projects/") else 0
        leads = len(OPEN_LEAD.findall(enrich["report"])) if enrich else 0
        label = ("investigate" if not last else "update" if new_mails or new_sessions
                 else "deeper" if leads else "current")
        quick = _points(investigate)
        full = round((quick or 0) + (_points(enrich) or 0), 1) if quick or _points(enrich) else None
        found[record] = {"last": last.isoformat() if last else None, "new_mails": new_mails,
                         "new_sessions": new_sessions, "leads": leads, "label": label,
                         "cost": {"quick": quick, "full": full}, **_run_state(root, record, logs)}
    return found


def _changed_since(root: Path, record: str, moment) -> bool:
    from datetime import datetime
    if not moment:
        return False
    page = Path(root) / record
    return page.is_file() and page.stat().st_mtime > datetime.fromisoformat(str(moment).replace("Z", "+00:00")).timestamp()


def _new_sessions(root: Path, record: str) -> int:
    from .project_pages import pending
    messages, kind = pending(root, record)
    return len(messages) if kind == "update" else 0


def _run_state(root: Path, record: str, logs) -> dict:
    from . import page_versions
    run = None
    if receipt_path(root, record).is_file():
        run = status(root, record, logs=logs)
        # A failed run the page has changed since (a later night, a later run) is history, not news (#3155).
        if run["result"] == "failed" and _changed_since(root, record, run.get("finished_at")):
            run = None
    return {"run": run, "undo": page_versions.can_undo(root, record), "rewrite": _draft(root, record)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--record", required=True)
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    arguments = parser.parse_args()
    _work(arguments.root, arguments.record, arguments.mode)
