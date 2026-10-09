"""Enumerate what the world already keeps a list of. No model.

A person is discovered by their address, a project by its `cwd`. Both come
with counts and dates for free, and those are what a Skill needs to judge who
matters -- so they are gathered here, once, and handed over. Whether a
correspondent is a person, a company's notices, or an event mailer is a
judgement the Skill makes; this only hands it the signals.
"""

import collections
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from pathlib import Path

from .files import RemError
from .mail import _address, _addresses, _list_all, correspondent
from .source import KINDS, source_files

# Rings a bell on its own; the Skill still decides. Matched anywhere before the
# @, because "no-reply.products@" slipped past a pattern anchored to the @.
AUTOMATED_HINT = re.compile(r"no-?reply|noreply|notification|newsletter|mailer|calendar|invitation|"
                            r"digest|alerts?|updates?|marketing|express@|automated|changelog|announce|"
                            r"news@|billing|receipts?@|invoice@|bounce|support@|team@|hello@|info@|"
                            # Account and notice desks the 1.9.0a5 notebook still kept as people (#2008):
                            # donotreply@dunsnumberlookup.dnb.com, notify@x.com, unsub+…@reply.github.com.
                            r"do-?not-?reply|notify@|^unsub\+|"
                            # Role desks that only ever wrote in on the 1.9.0a5 acceptance map (#2018):
                            # portal@telnyx.com, discover@telnyx.com, booking@singaporeair.com.
                            r"^(?:portal|bookings?|reservations?|discover|otp|verify|verification|security"
                            r"|accounts?|orders?|welcome|members?)@",
                            re.IGNORECASE)

INSTITUTIONAL_NAME = re.compile(
    r"(?:Centre|Center|Institute|Foundation|Hub|Labs?|Department|Society|Association|"
    r"Initiative|Council|Office|Team|Club)(?![A-Za-z])|中心|会议|学院|学会|委员会", re.I)


def institutional_name(name: str) -> bool:
    """A display name for an institution or desk rather than a person."""
    return bool(INSTITUTIONAL_NAME.search(name))

# Mailbox providers, not employers. A domain here says where someone keeps their
# mail; every other domain says who they answer to, which is why 168 of 182 real
# correspondents over 180 days carried one.
PERSONAL_MAILBOX = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "outlook.com.au", "hotmail.com", "hotmail.com.au",
    "hotmail.co.uk", "live.com", "live.com.au", "msn.com", "yahoo.com", "yahoo.com.au", "yahoo.co.jp",
    "icloud.com", "me.com", "mac.com", "aol.com", "protonmail.com", "proton.me", "gmx.com",
    "qq.com", "163.com", "126.com", "foxmail.com", "sina.com", "bigpond.com", "optusnet.com.au",
    # Short provider addresses and home-internet mail: orgs/pm-me and orgs/xtra-co-nz on 1.9.2b1.
    "pm.me", "xtra.co.nz", "bigpond.net.au", "tpg.com.au", "iinet.net.au", "internode.on.net", "ozemail.com.au",
    "dodo.com.au", "comcast.net", "verizon.net", "att.net", "btinternet.com", "sky.com", "virginmedia.com",
})
# A provider's name under any country suffix is the same provider: yahoo.com.hk
# became an organisation on the 1.9.0a5 acceptance map (#2018).
_PROVIDER = re.compile(r"^(?:gmail|googlemail|outlook|hotmail|live|msn|yahoo|ymail|icloud|aol|gmx|proton|protonmail"
                       r"|yandex|mail|qq|163|126|139|yeah|foxmail|sina|sohu|naver|daum|hanmail|rediffmail|zoho)"
                       r"\.(?:(?:com?|net)\.)?[a-z]{2,3}$")


def personal_mailbox(domain: str) -> bool:
    """A mailbox provider's domain: it says where someone keeps their mail, not who they work for."""
    domain = domain.casefold().rstrip(".")
    return domain in PERSONAL_MAILBOX or bool(_PROVIDER.match(domain))


# A display name that is a header word is not a name: the owner's test mail,
# sent by a CLI, put "From gws" in the To line and a page was titled so (#1974).
_HEADER_WORD = re.compile(r"^(?:from|to|cc|bcc|re|fwd?|via|sent)\b[\s:]", re.I)


def _display_name(row: dict, address: str) -> str:
    name = _raw_display_name(row, address)
    return "" if _HEADER_WORD.match(name) else name


def _raw_display_name(row: dict, address: str) -> str:
    """The other party's name -- from the side of the mail they are on.

    For mail the user sent, the correspondent is a recipient, so reading the
    From header returns the user's own display name; a real census filed
    Ody, Dora and the user's private Gmail all under "openonion ai".
    """
    # The providers split the sender into a bare `from` and a `from_name`; for
    # mail the correspondent sent, the name is there and nowhere else.
    if _address(str(row.get("from", ""))) == address and row.get("from_name"):
        name = str(row["from_name"]).strip(' "')
        return "" if "@" in name else name
    # Each recipient is parsed on its own: stripping every <...> out of
    # '"Ody Zhou" <o@g>, "Dora" <d@g>' once named both of them 'Ody Zhou", "Dora'.
    headers = [str(h) for h in [row.get("from", "")] + list(row.get("to") or []) + list(row.get("cc") or [])]
    for name, found in getaddresses(headers):
        if found.lower() == address and name.strip() and "@" not in name:
            return name.strip()
    return ""


# The owner's greeting is where the name of someone they only ever wrote to
# lives. On the owner's map 190 of 195 nameless people were recipients whose To
# line the owner typed as a bare address, and nearly every one of those mails
# opened "Hi Larry," or "Larry 你好，" or "子明，".
_GREETING = re.compile(
    r"^\s*(?:(?:hi|hello|hey|dear|morning|g'day)\s+([A-Za-z][A-Za-z'-]{1,20}(?:\s[A-Z][A-Za-z'-]{1,20})?)\s*[,，!！]"
    r"|([A-Za-z][A-Za-z'-]{1,20}|[\u4e00-\u9fff]{2,3})\s*(?:你好|您好)?\s*[,，])", re.IGNORECASE)
_NOT_A_NAME = {"everyone", "all", "team", "there", "guys", "folks", "both", "again", "sir", "madam",
               "friends", "hi", "hello", "dear", "您好", "你好", "大家", "各位", "大家好", "各位好"}


def _greeting_name(row: dict, address: str, mine: set) -> str:
    """The name the owner greeted the one person a mail went to, or ''.

    Only the owner's own mail to a single recipient: "Hi Larry," to three
    people names one of them, and nobody can say which.
    """
    if _address(str(row.get("from", ""))) not in mine:
        return ""
    recipients = [a for _, a in getaddresses([str(h) for h in list(row.get("to") or []) + list(row.get("cc") or [])])
                  if a and a.lower() not in mine]
    # An agent's address (0x…@) is greeted by its owner's name; that name is the
    # person's, not the agent's.
    if [a.lower() for a in recipients] != [address] or re.match(r"0x[0-9a-f]{6,}@", address):
        return ""
    match = _GREETING.match(html.unescape(str(row.get("snippet") or "")))
    name = (match.group(1) or match.group(2)) if match else ""
    # "hi" above a quote: "hi On Fri, May 8, 2026 at 5:06 PM … wrote:" (1.9.2b1).
    if not name or name.casefold() in _NOT_A_NAME or re.search(r"(?i)\b(?:mon|tue|wed|thu|fri|sat|sun)\b", name):
        return ""
    return name[0].upper() + name[1:] if name.islower() else name


def _contact_names(clients: dict) -> dict:
    """Names the owner saved, by address, from every mailbox that can list them.

    A saved contact is the owner's own word for who someone is, so it outranks a
    greeting; it does not outrank the name a person writes under. Contacts are
    optional: a mailbox without the permission maps from its mail alone.
    """
    names = {}
    for client in clients.values():
        try:
            listed = client.contact_names() if hasattr(client, "contact_names") else {}
        except Exception:  # noqa: BLE001 - a missing contacts permission must not stop the map
            continue
        for address, name in (listed or {}).items():
            if name and "@" not in name:
                names.setdefault(address.lower(), name.strip())
    return names


def _count_owner_names(row: dict, own: bool, mine: set, names: dict) -> None:
    """Add what this mail calls the owner to `names` (see scan_people)."""
    if own:
        sender = _display_name(row, _address(row.get("from", "")))
        if sender:
            names["sent"][sender] += 1
        return
    headers = [str(h) for h in list(row.get("to") or []) + list(row.get("cc") or [])]
    for name, address in getaddresses(headers):
        name = name.strip(' "')
        local = address.lower().split("@")[0]
        # "xietianle <xietianle@...>" is the address again, not a name.
        if (address.lower() in mine and name and "@" not in name and not _HEADER_WORD.match(name)
                and name.casefold().replace(" ", "").replace(".", "") != local.replace(".", "")):
            names["addressed"][name] += 1


def scan_people(clients: dict, days: int, own_addresses: set, progress=None,
                on_row=None, on_window=None, own_names=None, *, all_history: bool = False,
                on_error=None, own_addresses_complete: bool = False) -> list[dict]:
    """Every correspondent across every mailbox, with the signals a Skill ranks by.

    `own_names`, {"addressed": Counter, "sent": Counter}, is given what the
    owner is called (#2008): the display name others put on the owner's address
    in the To and Cc of mail they sent, and the From name of mail the owner
    sent. A real account's configured name was "Aaron x", and Outlook stamps
    it on every sent mail; correspondents wrote "Aaron Xie".
    """
    mine = {a.lower() for a in own_addresses}
    if not own_addresses_complete:
        for client in clients.values():
            mine |= {a.lower() for a in client.my_addresses()}
    end = datetime.now(timezone.utc)
    start = datetime(1970, 1, 1, tzinfo=timezone.utc) if all_history else end - timedelta(days=days)
    # A year at a time keeps a lifetime scan observable. The provider's 200
    # item cap is still split recursively by _list_all.
    window = timedelta(days=366 if all_history else 7)
    people = collections.defaultdict(lambda: {"names": collections.Counter(), "greetings": collections.Counter(),
                                              "mails": 0, "sent": 0,
                                              "received": 0, "first": "", "last": "", "boxes": set(),
                                              "subjects": collections.Counter()})
    # Co-recipient headers can name an existing contact without being mail from them.
    recipient_names = collections.defaultdict(collections.Counter)
    for kind, client in clients.items():
        cursor = start
        while cursor < end:
            stop = min(cursor + window, end)
            # Both providers cap a listing at 200, but at opposite ends of the
            # window. Reuse the importer that bisects a full window until every
            # message in this interval has been enumerated.
            failed = []
            def error_window(since, until, error):
                failed.append((since, until))
                if on_error is not None:
                    on_error(kind, since, until, error)
            try:
                rows = _list_all(client, cursor, stop,
                                 on_error=error_window if all_history and on_error is not None else None)
            except Exception as error:
                if not all_history or on_error is None:
                    raise
                # Completed years are already mapped. A timeout can be local to
                # one year; a broken connection may affect everything after it.
                timed_out = 'timeout' in type(error).__name__.lower()
                failed_until = stop if timed_out else end
                on_error(kind, cursor, failed_until, error)
                if on_window:
                    on_window(kind, cursor.isoformat(), failed_until.isoformat(), 0, 200, False)
                if not timed_out:
                    break
                cursor = stop
                continue
            for row in rows:
                if on_row:
                    on_row(kind, row)
                own = _address(row.get("from", "")) in mine or "@" not in _address(row.get("from", ""))
                if own_names is not None:
                    _count_owner_names(row, own, mine, own_names)
                # One sent message can be relevant to several people. Map each
                # recipient, while the body archive still stores it only once.
                recipients = _addresses(row.get("to")) + _addresses(row.get("cc"))
                for address in dict.fromkeys(recipients):
                    name = _display_name(row, address)
                    if name and address not in mine:
                        recipient_names[address][name] += 1
                whos = dict.fromkeys(recipients if own and recipients else [correspondent(row, mine)])
                for who in whos:
                    if "@" not in who or who in mine:
                        continue
                    entry = people[who]
                    entry["mails"] += 1
                    entry["boxes"].add(kind)
                    entry["sent" if own else "received"] += 1
                    name = _display_name(row, who)
                    if name:
                        entry["names"][name] += 1
                    greeting = _greeting_name(row, who, mine)
                    if greeting:
                        entry["greetings"][greeting] += 1
                    day = str(row.get("date", ""))[:10]
                    entry["first"] = min(entry["first"] or day, day)
                    entry["last"] = max(entry["last"] or day, day)
                    subject = re.sub(r"^(re|fw|fwd|回复|转发)\s*:\s*", "", str(row.get("subject", "")), flags=re.I)[:80]
                    if subject:
                        entry["subjects"][subject] += 1
            if progress:
                progress(kind, stop, len(people))
            if on_window:
                on_window(kind, cursor.isoformat(), stop.isoformat(), len(rows), 200, not failed)
            cursor = stop
    saved = _contact_names(clients)
    out = []
    for address, e in people.items():
        # Direct header name, saved contact, co-recipient header, then greeting.
        name = (e["names"].most_common(1)[0][0] if e["names"] else "") or saved.get(address, "") \
            or (recipient_names[address].most_common(1)[0][0] if recipient_names[address] else "") \
            or (e["greetings"].most_common(1)[0][0] if e["greetings"] else "")
        out.append({"address": address,
                    "name": name,
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
    parts = Path(normalized).parts
    if any(parts[i:i + 2] == (".state", "tasks") for i in range(len(parts) - 1)):
        return "co rem task workspace copy"
    if path.name == "notebook" and any(parent.name.endswith("-fixture") for parent in path.parents):
        return "test fixture notebook"
    # A workspace says so in its agent instructions; Claude Code reads CLAUDE.md,
    # Codex AGENTS.md, and the owner's ~/projects had both.
    if path.is_dir() and not (path / ".git").exists() and any(
            (path / marker).is_file() for marker in ("AGENTS.md", "CLAUDE.md")):
        repositories = 0
        try:
            for child in path.iterdir():
                if child.is_dir() and (child / ".git").exists():
                    repositories += 1
                    if repositories >= 2:
                        return "multi-repository workspace container"
        except OSError:
            pass
    if (normalized.rstrip('/') + '/').startswith(("/private/tmp/", "/tmp/", "/private/var/folders/", "/var/folders/")):
        return "temporary execution directory"
    if not path.is_dir() and "/.codex/worktrees/" in normalized:
        return "removed Codex worktree"
    return ""


CLAUDE_WORKTREE = re.compile(r"^(/.+?)/\.claude/worktrees/[^/]+(/.*)?$")


def main_checkout(path: str) -> str:
    """The repository checkout a worktree belongs to, or "" for anything else.

    Every coding session's `cwd` became a project path, so one real page listed
    about 70 `.claude/worktrees/agent-*` folders and no main checkout, and
    investigation read a stale agent's copy as the project's state (#1955). A
    live worktree says where home is in its `.git` file; one Claude Code has
    removed still says so in its path.
    """
    git = Path(path) / ".git"
    if git.is_file():
        home = re.fullmatch(r"gitdir:\s*(.+?)/\.git/worktrees/[^/]+/?\s*", git.read_text(errors="replace"))
        if home:
            return os.path.normpath(os.path.join(path, home[1]))
    layout = CLAUDE_WORKTREE.match(path)
    if layout:
        return layout[1] + (layout[2] or "")
    # `~/projects/.worktree/browser-139`, `repo/.worktrees/fix`: a removed one no
    # longer says where home is, so the folder beside it whose name starts its
    # own is home (#1974). With none, it is not guessed.
    folder = WORKTREE_FOLDER.match(path)
    if folder and not git.exists():
        home = _beside(folder[1], folder[2])
        return home + (folder[3] or "") if home else ""
    return ""


WORKTREE_FOLDER = re.compile(r"^(/.+?)/\.worktrees?/([^/]+)(/.*)?$")


def _beside(parent: str, name: str) -> str:
    """The repository a `.worktree(s)/<name>` folder was made from: the folder
    holding `.worktrees/` when it is a repository, else the repository next to
    `.worktree/` whose name starts `<name>` (the longest such name)."""
    if (Path(parent) / ".git").exists():
        return parent
    try:
        names = [child.name for child in Path(parent).iterdir()
                 if not child.name.startswith(".") and (child / ".git").exists()]
    except OSError:
        return ""
    fits = [repo for repo in names if name == repo or re.match(re.escape(repo) + r"[-_.]", name)]
    return os.path.join(parent, max(fits, key=len)) if fits else ""


# A turn of one short session: a one-off chat, not a project (#1974).
SHORT_SESSION_TURNS = 3
SHORT_SESSION = "one short session outside a repository"
ONE_OFF_TASK = "a one-off scratch task folder without a project manifest"
DATED_SCRATCH = re.compile(r"(?:^|/)(?:Documents/Codex|[Ss]cratchpad|[Ss]cratch)/\d{4}-\d{2}-\d{2}/")
PROJECT_MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Makefile")
PROMPT_FRAGMENT = re.compile(r"(?:create|make|install|set-up|fix|add|update|write|build|please|pls)(?:-[a-z0-9]+)+", re.I)


def scratch_without_manifest(path: Path) -> bool:
    """A dated scratch task has no project file in its folder or dated parent."""
    match = DATED_SCRATCH.search(path.as_posix())
    if not match:
        return False
    dated = Path(path.as_posix()[:match.end() - 1])
    return not any((folder / manifest).is_file()
                   for folder in (path, *path.parents) if folder.is_relative_to(dated)
                   for manifest in PROJECT_MANIFESTS)


def home_or_above(path: Path) -> bool:
    """The home folder or one of its parents: it holds every session there is (#1944)."""
    try:
        home = Path.home().resolve()
        return home == path.resolve() or home.is_relative_to(path.resolve())
    except OSError:
        return False


def not_a_project(row: dict) -> str:
    """Why a folder a session ran in is not a project, or "" when it is one (#1974).

    On the owner's machine the map made pages for a Codex chat named after its
    first prompt ("create-a-scheduled-task-called-weekday"), for plugin-install
    folders, and for build output under a hidden folder -- each with one session
    and no repository. A repository is always a project; so is a folder the user
    came back to, or talked in for more than a few turns. Dated scratch task
    folders also need a project manifest. `row` is a
    `scan_projects` row: `path`, `repo`, `sessions`, and `turns` when counted.
    """
    path = Path(row["path"])
    if home_or_above(path):
        return "home directory"
    if row.get("repo") or main_checkout(row["path"]) or (path / ".git").exists():
        return ""
    if DATED_SCRATCH.search(path.as_posix()):
        return ONE_OFF_TASK if scratch_without_manifest(path) else ""
    if PROMPT_FRAGMENT.fullmatch(path.name) and not any((path / name).is_file() for name in PROJECT_MANIFESTS):
        return "prompt-fragment folder without a project manifest"
    parts = path.parts
    if any(part in ("scheduled-tasks", "scheduled_tasks") for part in parts):
        return "scheduled-task folder"
    if any(part.startswith(".") for part in parts[1:]):
        return "hidden folder outside a repository (a cache, a plugin or build output)"
    turns = row.get("turns")
    if row.get("sessions", 0) <= 1 and turns is not None and turns <= SHORT_SESSION_TURNS:
        return SHORT_SESSION
    return ""


def session_turns(path: Path, kind: str, limit: int = SHORT_SESSION_TURNS + 1) -> int:
    """How many turns the user started in one session file, counted up to `limit`.

    Claude Code: messages the user typed (the same reading `sync` does). Codex:
    `turn_context` records, one per turn -- a desktop Codex message carries
    metadata the typed-message reader does not take as typed.
    """
    from .source import KINDS
    since = datetime(1970, 1, 1, tzinfo=timezone.utc)
    turns = 0
    try:
        with path.open("rb") as handle:
            for line in handle:
                if kind == "codex":
                    turns += b'"turn_context"' in line[:200]
                elif b'"user"' in line:
                    try:
                        item = KINDS[kind]["message"](json.loads(line), since)
                    except (ValueError, UnicodeError, RemError, AttributeError, TypeError):
                        continue
                    turns += isinstance(item, dict)
                if turns >= limit:
                    break
    except OSError:
        return limit
    return turns


def scan_projects(subscriptions: dict, days: int, rem_root: Path | None = None,
                  on_session=None, progress=None) -> list[dict]:
    """Every `cwd` a coding session ran in, with how often and how recently.

    `progress(message, "i/N")` every 25 session files, so init can draw a bar.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    projects = collections.defaultdict(lambda: {"sessions": 0, "first": "", "last": "", "tools": set(),
                                                "files": []})
    for name, sub in subscriptions.items():
        kind = sub.get("kind")
        if sub.get("enabled") is False or kind not in KINDS or not Path(sub.get("root", "")).is_dir():
            continue
        files = source_files(sub)
        for number, path in enumerate(files, 1):
            if progress and (number == 1 or number % 25 == 0 or number == len(files)):
                progress(f"scanning local projects ({name} sessions)", f"{number}/{len(files)}")
            stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if stamp < since:
                continue
            try:
                with path.open("rb") as handle:
                    first = json.loads(handle.readline(1_000_000))
                meta = KINDS[kind]["meta"](first) if isinstance(first, dict) else {}
            except (ValueError, UnicodeError, RemError):
                continue
            cwd = (meta or {}).get("cwd") or ""
            if sub.get("project") and cwd != sub["project"]:
                continue
            if not cwd or meta.get("skip") or project_exclusion(Path(cwd)):
                continue
            if rem_root and Path(cwd).resolve().is_relative_to(rem_root.resolve()):
                continue
            if on_session:
                on_session(name, path, stamp, cwd)
            entry = projects[cwd]
            entry["files"].append((kind, path))
            entry["sessions"] += 1
            entry["tools"].add(kind)
            day = stamp.date().isoformat()
            entry["first"] = min(entry["first"] or day, day)
            entry["last"] = max(entry["last"] or day, day)
    out = []
    for cwd, e in projects.items():
        repo = _repo_identity(Path(cwd))
        # Only a lone session outside a repository can be a one-off chat, so only
        # its file is read past the first line.
        turns = session_turns(e["files"][0][1], e["files"][0][0]) \
            if e["sessions"] == 1 and not repo.get("toplevel") else None
        out.append({"path": cwd, "name": Path(cwd).name or cwd, "sessions": e["sessions"], "turns": turns,
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
        if not domain or personal_mailbox(domain) or domain in own:
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
