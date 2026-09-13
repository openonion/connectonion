"""Enumerate what the world already keeps a list of. No model.

A person is discovered by their address, a project by its `cwd`. Both come
with counts and dates for free, and those are what a Skill needs to judge who
matters -- so they are gathered here, once, and handed over. Whether a
correspondent is a person, a company's notices, or an event mailer is a
judgement the Skill makes; this only hands it the signals.
"""

import collections
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import WikiError
from .mail import AUTOMATED_SENDER, _address, _addresses, correspondent
from .source import KINDS, source_files

# Rings a bell on its own; the Skill still decides. Matched anywhere before the
# @, because "no-reply.products@" slipped past a pattern anchored to the @.
AUTOMATED_HINT = re.compile(r"no-?reply|noreply|notification|newsletter|mailer|calendar|invitation|"
                            r"digest|alerts?|updates?|marketing|express@|automated", re.IGNORECASE)


def _display_name(row: dict, address: str) -> str:
    """The other party's name -- from the side of the mail they are on.

    For mail the user sent, the correspondent is a recipient, so reading the
    From header returns the user's own display name; a real census filed
    Ody, Dora and the user's private Gmail all under "openonion ai".
    """
    for header in ([row.get("from", "")] + list(row.get("to") or []) + list(row.get("cc") or [])):
        header = str(header)
        if address in header.lower():
            name = re.sub(r"<[^>]*>", "", header).strip(' "')
            if name and "@" not in name:
                return name
    return ""


def scan_people(clients: dict, days: int, own_addresses: set, progress=None) -> list[dict]:
    """Every correspondent across every mailbox, with the signals a Skill ranks by."""
    mine = {a.lower() for a in own_addresses}
    for client in clients.values():
        mine |= {a.lower() for a in client.my_addresses()}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    people = collections.defaultdict(lambda: {"names": collections.Counter(), "mails": 0, "sent": 0,
                                              "received": 0, "first": "", "last": "", "boxes": set(),
                                              "subjects": collections.Counter()})
    for kind, client in clients.items():
        cursor = start
        while cursor < end:
            stop = min(cursor + timedelta(days=7), end)
            for row in client.list_between(cursor.isoformat(), stop.isoformat(), 200) or []:
                who = correspondent(row, mine)
                if "@" not in who or who in mine:
                    continue
                entry = people[who]
                entry["mails"] += 1
                entry["boxes"].add(kind)
                own = _address(row.get("from", "")) in mine or "@" not in _address(row.get("from", ""))
                entry["sent" if own else "received"] += 1
                name = _display_name(row, who)
                if name:
                    entry["names"][name] += 1
                day = str(row.get("date", ""))[:10]
                entry["first"] = min(entry["first"] or day, day)
                entry["last"] = max(entry["last"] or day, day)
                subject = re.sub(r"^(re|fw|fwd|回复|转发)\s*:\s*", "", str(row.get("subject", "")), flags=re.I)[:80]
                if subject:
                    entry["subjects"][subject] += 1
            if progress:
                progress(kind, stop, len(people))
            cursor = stop
    out = []
    for address, e in people.items():
        out.append({"address": address,
                    "name": e["names"].most_common(1)[0][0] if e["names"] else "",
                    "mails": e["mails"], "sent": e["sent"], "received": e["received"],
                    "first": e["first"], "last": e["last"], "boxes": sorted(e["boxes"]),
                    "subjects": [s for s, _ in e["subjects"].most_common(3)],
                    # signals, not verdicts: the Skill classifies
                    "automated_hint": bool(AUTOMATED_HINT.search(address)),
                    "one_way": e["sent"] == 0 or e["received"] == 0,
                    "days_since_last": (end.date() - datetime.fromisoformat(e["last"]).date()).days if e["last"] else None})
    return sorted(out, key=lambda p: (-p["mails"], p["address"]))


def scan_projects(subscriptions: dict, days: int) -> list[dict]:
    """Every `cwd` a coding session ran in, with how often and how recently."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    projects = collections.defaultdict(lambda: {"sessions": 0, "first": "", "last": "", "tools": set()})
    for name, sub in subscriptions.items():
        kind = sub.get("kind")
        if kind not in KINDS or not Path(sub.get("root", "")).is_dir():
            continue
        for path in source_files(sub):
            stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if stamp < since:
                continue
            try:
                with path.open("rb") as handle:
                    first = json.loads(handle.readline(1_000_000))
                meta = KINDS[kind]["meta"](first) if isinstance(first, dict) else {}
            except (ValueError, UnicodeError, WikiError):
                continue
            cwd = (meta or {}).get("cwd") or ""
            if not cwd or meta.get("skip"):
                continue
            entry = projects[cwd]
            entry["sessions"] += 1
            entry["tools"].add(kind)
            day = stamp.date().isoformat()
            entry["first"] = min(entry["first"] or day, day)
            entry["last"] = max(entry["last"] or day, day)
    out = []
    for cwd, e in projects.items():
        repo = _repo_identity(Path(cwd))
        out.append({"path": cwd, "name": Path(cwd).name or cwd, "sessions": e["sessions"],
                    "first": e["first"], "last": e["last"], "tools": sorted(e["tools"]),
                    # A worktree is not a second project. 33 paths on one machine
                    # were about a dozen repositories once collapsed by origin.
                    "repo": repo.get("toplevel", ""), "origin": repo.get("origin", ""),
                    "is_worktree": bool(repo.get("toplevel")) and repo["toplevel"] != cwd})
    return sorted(out, key=lambda p: (-p["sessions"], p["path"]))


def _repo_identity(path: Path) -> dict:
    """The repository a directory belongs to, and its origin -- what makes two paths one project."""
    import subprocess
    if not path.is_dir():
        return {}
    try:
        top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if top.returncode:
            return {}
        origin = subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"],
                                capture_output=True, text=True, timeout=5)
        common = subprocess.run(["git", "-C", str(path), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, timeout=5)
        # A linked worktree's common dir is the main checkout's .git; that is the project.
        toplevel = top.stdout.strip()
        if common.returncode == 0 and common.stdout.strip() not in (".git", f"{toplevel}/.git"):
            toplevel = str(Path(common.stdout.strip()).resolve().parent)
        return {"toplevel": toplevel, "origin": origin.stdout.strip() if origin.returncode == 0 else ""}
    except (OSError, subprocess.TimeoutExpired):
        return {}
