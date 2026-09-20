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
from .mail import _address, correspondent
from .source import KINDS, source_files

# Rings a bell on its own; the Skill still decides. Matched anywhere before the
# @, because "no-reply.products@" slipped past a pattern anchored to the @.
AUTOMATED_HINT = re.compile(r"no-?reply|noreply|notification|newsletter|mailer|calendar|invitation|"
                            r"digest|alerts?|updates?|marketing|express@|automated", re.IGNORECASE)

# Mailbox providers, not employers. A domain here says where someone keeps their
# mail; every other domain says who they answer to, which is why 168 of 182 real
# correspondents over 180 days carried one.
PERSONAL_MAILBOX = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "outlook.com.au", "hotmail.com", "hotmail.com.au",
    "hotmail.co.uk", "live.com", "live.com.au", "msn.com", "yahoo.com", "yahoo.com.au", "yahoo.co.jp",
    "icloud.com", "me.com", "mac.com", "aol.com", "protonmail.com", "proton.me", "gmx.com",
    "qq.com", "163.com", "126.com", "foxmail.com", "sina.com", "bigpond.com", "optusnet.com.au",
})


def _display_name(row: dict, address: str) -> str:
    """The other party's name -- from the side of the mail they are on.

    For mail the user sent, the correspondent is a recipient, so reading the
    From header returns the user's own display name; a real census filed
    Ody, Dora and the user's private Gmail all under "openonion ai".
    """
    # The providers split the sender into a bare `from` and a `from_name`; for
    # mail the correspondent sent, the name is there and nowhere else.
    if _address(str(row.get("from", ""))) == address and row.get("from_name"):
        return str(row["from_name"]).strip(' "')
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


def canonical_origin(origin: str) -> str:
    """Normalize transport spelling, retaining case-sensitive repository paths."""
    from urllib.parse import urlsplit
    if not origin:
        return ""
    if "://" in origin:
        parts = urlsplit(origin)
        if parts.hostname and parts.scheme in ("http", "https", "ssh", "git"):
            host = parts.hostname.lower()
            port = parts.port
            if port and port not in ({"https": 443, "http": 80, "ssh": 22, "git": 9418}[parts.scheme],):
                host += f":{port}"
            return host + "/" + parts.path.strip("/").removesuffix(".git")
    match = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", origin)
    if match:
        return match[1].lower() + "/" + match[2].strip("/").removesuffix(".git")
    return origin


def project_exclusion(path: Path) -> str:
    """Ignore execution sandboxes, not legitimate projects sharing a display name."""
    normalized = str(path.resolve())
    if normalized.startswith(("/private/tmp/", "/tmp/", "/private/var/folders/", "/var/folders/")):
        return "temporary execution directory"
    if not path.is_dir() and "/.codex/worktrees/" in normalized:
        return "removed Codex worktree"
    return ""


def scan_projects(subscriptions: dict, days: int) -> list[dict]:
    """Every `cwd` a coding session ran in, with how often and how recently."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    projects = collections.defaultdict(lambda: {"sessions": 0, "first": "", "last": "", "tools": set()})
    for name, sub in subscriptions.items():
        kind = sub.get("kind")
        if sub.get("enabled") is False or kind not in KINDS or not Path(sub.get("root", "")).is_dir():
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
            if sub.get("project") and cwd != sub["project"]:
                continue
            if not cwd or meta.get("skip") or project_exclusion(Path(cwd)):
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
            toplevel = str((path / common.stdout.strip()).resolve().parent)
        return {"toplevel": toplevel, "origin": origin.stdout.strip() if origin.returncode == 0 else ""}
    except (OSError, subprocess.TimeoutExpired):
        return {}


def scan_orgs(people: list[dict], min_people: int = 2, own_addresses=()) -> list[dict]:
    """The domains several people write from, which is where an organisation page earns
    its place.

    A company is not a person, and the difference is not that it has a different shape:
    it is that its facts belong to it rather than to whoever happened to send the mail.
    Over 180 real days one domain held 24 correspondents, and every institutional fact
    about it -- the programme, the agreement, who handles contracts and who handles
    dates -- would otherwise be copied onto 24 pages and drift 24 ways.

    The threshold is what keeps this from becoming the one-line-person failure at
    company scale: 111 of the 122 work domains in that window held exactly one person,
    and a page each would have doubled the notebook with empty pages. One person on a
    work domain stays a `Company:` field. `min_people=1` lowers it deliberately, for
    the one-person client who signed a contract.
    """
    # A domain the user sends from is the user, not a counterparty: on the real
    # census `mail.openonion.ai` came third with 18 of their own agent addresses.
    own = {str(a).rsplit("@", 1)[-1].lower() for a in own_addresses if "@" in str(a)}
    domains = collections.defaultdict(lambda: {"people": [], "notices": [], "mails": 0, "last": ""})
    for person in people:
        domain = str(person.get("address", "")).rsplit("@", 1)[-1].lower()
        if not domain or domain in PERSONAL_MAILBOX or domain in own:
            continue
        entry = domains[domain]
        # A notice sender is not someone we deal with. Run over 180 real days the
        # first version proposed 53 organisations led by google.com (29 "people":
        # Google Analytics, Google Play), an event platform's per-event senders and
        # the user's own agent domain -- all one-way. Only correspondents decide the
        # threshold; the notices stay on the row, because a domain holds both and a
        # university's alert sender does not make the university less real.
        which = "notices" if person.get("automated_hint") and person.get("one_way") else "people"
        entry[which].append(person)
        entry["mails"] += person.get("mails", 0)
        entry["last"] = max(entry["last"], str(person.get("last") or ""))
    out = []
    for domain, entry in domains.items():
        if len(entry["people"]) < min_people:
            continue
        rows = sorted(entry["people"], key=lambda p: (-p.get("mails", 0), p.get("address", "")))
        # Two-way correspondence is the strongest sign of a counterparty, and it is
        # not a filter: a reply sent from the user's other mailbox leaves `sent` at
        # zero, so a real client can read one-way. Both numbers go over; the Skill
        # judges. Brand names that only ever send are a vendor.
        out.append({"domain": domain, "people": len(rows), "notices": len(entry["notices"]),
                    "two_way": sum(1 for r in rows if not r.get("one_way")),
                    "mails": entry["mails"], "last": entry["last"],
                    "addresses": [r["address"] for r in rows],
                    "names": [r["name"] for r in rows if r.get("name")]})
    # Counterparties first. Sorting by headcount alone put an event platform's 22
    # per-event senders above the university the user actually works with.
    return sorted(out, key=lambda o: (-o["two_way"], -o["people"], -o["mails"], o["domain"]))
