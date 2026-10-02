"""One subject, every source at once: the first-run stage, and the daily deep pass.

Identity is the input. The subject arrives with its handles, every handle is
searched in every source, and a handle that finds nothing is reported rather
than passed over -- "searched Gmail for X, none" and "did not mention Gmail"
read alike on a page and mean different things.
"""

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

from .config import read_config
from ..provider_credentials import ProviderCredentialError
from .files import SECRET_SHAPES, Notebook, RemError, is_address, maintenance_lock, read_json, state_path, write_json
from .mail import _address, _list_all, correspondent, on_domains, participants, RELATED_ORG_SCOPE, strip_noise, strip_quoted
from .source import KINDS, collect, timestamp

MAIL_KINDS = ("outlook", "gmail")
DOMAIN_HANDLE = re.compile(r"^@?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})$")
DOMAIN_RESULTS = 10_000


class NothingFound(RemError):
    """The gather found nothing about the subject, so no model turn runs and no page is stamped (#1974).

    1.9.0a2 stamped a mailbox page "investigated" after a 919k-token turn whose
    only material was the page and the coverage note. `usage` is what the digest
    calls cost before it was known that nothing was there.
    """

    def __init__(self, message, usage=None):
        super().__init__(message)
        self.usage = usage


class NothingNew(NothingFound):
    """A page investigated before whose window since then gathered nothing: no model turn (#1984).

    1.9.0a3 made a 92k-token turn for a person whose since-window held 0 mails
    and 0 sessions; its only change was deleting one Uncertainties line. For a
    project the file list is always there, so it alone does not count as new.
    """


def _searched(coverage: list[str]) -> str:
    searched = "; ".join(line for line in coverage
                         if not line.startswith(("Requested investigation window", "Quick first pass",
                                                 "Page last updated from its sources")))
    return searched if len(searched) <= 400 else searched[:400] + "…"


def _nothing_new(record: str, subject: str, coverage: list[str], last) -> NothingNew:
    return NothingNew(f"Nothing new since {last.isoformat()} for {subject} ({_searched(coverage) or 'no source searched'}). "
                      f"No model was called; {record} is unchanged and keeps its status line.")


# A refused turn's material, by source id, per page (#2041). Without it the
# page stayed first in the queue with the same window, and the next run
# re-read the same mail: 643k tokens refused, then 933k on the same 113k chars.
REFUSED = "refused-investigations.json"


def refused_for(root: Path, record: str) -> dict:
    return read_json(state_path(root, REFUSED), {}).get(record) or {}


def _remember_refusal(root: Path, record: str, sources: list[str], why: str) -> None:
    path = state_path(root, REFUSED)
    refused = read_json(path, {})
    refused[record] = {"sources": sorted(set(sources)), "at": datetime.now(timezone.utc).isoformat(),
                       "why": why[:300]}
    write_json(path, refused)


def _forget_refusal(root: Path, record: str) -> None:
    path = state_path(root, REFUSED)
    refused = read_json(path, {})
    if refused.pop(record, None) is not None:
        write_json(path, refused)


def _refused_again(record: str, subject: str, refusal: dict) -> NothingNew:
    return NothingNew(f"Nothing new since this material was refused on {refusal['at'][:10]} for {subject} "
                      f"({refusal.get('why', '')}). No model was called; {record} is unchanged and waits for "
                      "newer material.")


def _nothing_found(record: str, subject: str, coverage: list[str], *, me: bool = False,
                   digested: bool = False, usage=None) -> NothingFound:
    searched = _searched(coverage)
    why = ("every digest of the material came back empty" if digested
           else "no mail, attachment, session or chat message about them was found")
    target = "me" if me else record
    handle = "NAME" if record.startswith("projects/") else "ADDRESS"
    return NothingFound(f"Not written: {why} for {subject} ({searched or 'no source searched'}). {record} "
                        f"was not changed and is not marked investigated. Name another address or name with "
                        f"`co rem investigate {target} --handle {handle}`.", usage)


def org_domains(text: str) -> list[str]:
    """Mail domains from the page, even after its title becomes a company name."""
    section = text.partition("## Domains\n")[2].split("\n## ", 1)[0]
    values = [line[2:].split()[0].casefold() for line in section.splitlines() if line.startswith("- ") and line[2:].strip()]
    return sorted({match[1] for value in values if (match := DOMAIN_HANDLE.fullmatch(value))})


def org_pages(notebook: Notebook, record: str, handles: list[str], *, limit: int = 40) -> list[str]:
    """Organisation pages the subject's Company (a project's Organisation) can link to (#1974).

    The page Skills say to link them, but the turn was never told which org
    pages exist: 0 of 4 person pages linked one that did. For a person, the
    pages whose Domains hold one of their mail domains (or a parent of it);
    for a project, the notebook's organisations. Context, never evidence.
    """
    if not record.startswith(("people/", "projects/")):
        return []
    mine = {handle.rpartition("@")[2].casefold() for handle in handles if is_address(handle)}
    found = []
    for org in notebook.list("orgs"):
        text = notebook.read(org)
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), org)
        domains = org_domains(text)
        if record.startswith("projects/"):
            found.append(f"{org} — {title}")
            continue
        matched = [domain for domain in domains
                   if any(own == domain or own.endswith("." + domain) for own in mine)]
        if matched:
            found.append(f"{org} — {title} ({', '.join(matched)})")
    return found[:limit]


def org_contact_context(notebook: Notebook, record: str) -> dict:
    """Other domain pages sharing a canonical contact: leads to verify, not identity proof."""
    if not record.startswith("orgs/"):
        return {"domains": [], "addresses": [], "candidates": []}
    rows = read_json(state_path(notebook.root, "map.json"), {}).get("orgs", [])
    own = next((row for row in rows if row.get("record") == record), {})
    people = set(own.get("people", []))
    roster = {person["path"]: person for person in notebook.people()} if people else {}
    candidates, addresses = [], set()
    for row in rows:
        shared = people.intersection(row.get("people", []))
        other = row.get("record")
        if not shared or not other or other == record or not notebook.path(other).is_file():
            continue
        domains = row.get("domains") or [row.get("domain", "")]
        contacts = [{"record": person, "addresses": [email for email in roster.get(person, {}).get("emails", [])
                     if on_domains({"from": email}, domains)]} for person in sorted(shared)]
        found = {email for contact in contacts for email in contact["addresses"]}
        if found:
            addresses.update(found)
            candidates.append({"record": other, "domains": domains, "shared_contacts": contacts})
    return {"domains": own.get("domains") or ([own["domain"]] if own.get("domain") else []),
            "addresses": sorted(addresses), "candidates": candidates}


def quick_evidence(items: list[dict], *, max_items: int = 24,
                   chars_per_item: int = 2500) -> list[dict]:
    """A bounded first look, with source diversity and recent items.

    This is explicitly partial evidence. A quick onboarding turn should not
    quietly spawn a sequence of expensive extraction agents for the owner.
    """
    latest = list(reversed(items))
    chosen, seen = [], set()
    for item in latest:
        source = item.get("source", "").split(":", 1)[0]
        if source not in seen:
            chosen.append(item)
            seen.add(source)
    for item in latest:
        if len(chosen) >= max_items:
            break
        if item not in chosen:
            chosen.append(item)
    selected = []
    for item in sorted(chosen[:max_items], key=lambda row: row["timestamp"]):
        copy = dict(item)
        body = copy.get("text", "")
        if len(body) > chars_per_item:
            copy["text"] = body[:chars_per_item] + "\n[truncated for quick first-pass review]"
        selected.append(copy)
    return selected


def project_paths(page: str) -> list[str]:
    """Recover mapped project directories after a cited investigation page.

    Citation markers belong to Markdown, not to the path used for local reads
    or session matching on the next run.
    """
    section = page.partition("## Paths\n")[2].split("\n## ", 1)[0]
    return [_listed_path(line) for line in section.splitlines() if _listed_path(line)]


def _listed_path(line: str) -> str:
    quoted = re.match(r"^- `(/[^`]+)`(?:\s|$)", line)
    if quoted:
        return quoted[1]
    return re.sub(r"\s+\[\d+\](?:\s*\[\d+\])*\s*$", "", line[2:].strip().split(" — ", 1)[0]) if line.startswith("- /") else ""


def collapse_worktree_paths(page: str) -> str:
    """The page with each worktree under Paths replaced by its main checkout, listed first.

    Pages mapped before #1955 list agent worktrees and read one as the project.
    Only a line `main_checkout` recognises goes; a folder the owner wrote, and
    Sessions / First seen / Last seen, stay as they are.
    """
    from .scan import main_checkout
    section = re.search(r"(?ms)^## Paths\n(.*?)(?=^## |\Z)", page)
    if not section:
        return page
    kept, checkouts = [], []
    for line in section.group(1).splitlines(keepends=True):
        checkout = main_checkout(_listed_path(line)) if _listed_path(line) else ""
        (checkouts if checkout else kept).append(checkout or line)
    listed = {_listed_path(line) for line in kept}
    body = "".join(f"- {path}\n" for path in dict.fromkeys(checkouts) if path not in listed) + "".join(kept)
    return page[:section.start(1)] + body + page[section.end(1):]


def project_file_inventory(page: str, *, max_files: int = 60) -> list[str]:
    """Give a project investigation bounded file leads, never file contents.

    Session metadata can name a project with no user messages. A short inventory
    lets the model pick evidence from the recorded path without repeatedly
    searching the user's home directory. File names alone prove no project fact.
    """
    roots = [Path(path).expanduser() for path in project_paths(collapse_worktree_paths(page))]
    leads = []
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".state"}
    suffixes = {".md", ".txt", ".toml", ".py", ".js", ".ts", ".tsx", ".html", ".css", ".swift", ".go", ".rs"}
    for root in roots[:4]:
        resolved = root.resolve()
        if (not root.is_dir() or root.is_symlink() or resolved == Path.home()
                or resolved in Path.home().parents or len(resolved.parts) < 3):
            continue
        seen = 0
        for current, dirs, files in os.walk(root, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".")
                             and not (Path(current) / d).is_symlink()) if depth < 4 else []
            for name in sorted(files):
                if name.startswith(".") or (Path(name).suffix.lower() not in suffixes and name != "package.json"):
                    continue
                if any(word in name.lower() for word in ("secret", "password", "credential", "private", "token")):
                    continue
                path = Path(current) / name
                if path.is_symlink():
                    continue
                leads.append(str(path))
                seen += 1
                if seen >= 1000:
                    break
            if seen >= 1000:
                break
    def priority(path):
        name = Path(path).name.lower()
        return (0 if name.startswith("readme") else
                1 if name in ("pyproject.toml", "package.json") else
                2 if "rem" in path.lower() else 3, len(Path(path).parts), path)
    return sorted(set(leads), key=priority)[:max_files]


def project_file_texts(paths: list[str], *, max_files: int = 12, chars_per_file: int = 2000) -> list[dict]:
    """Bounded file snapshots; capture time is separate from file modification time."""
    items = []
    for name in paths[:max_files]:
        path = Path(name)
        with path.open(encoding="utf-8", errors="replace") as handle:
            raw = handle.read(chars_per_file + 1)
        text = SECRET_SHAPES.sub("[secret-shaped text removed by co rem]", raw[:chars_per_file])
        truncated = len(raw) > chars_per_file or len(text) > chars_per_file
        captured = datetime.now(timezone.utc).isoformat()
        items.append({"role": "project-file", "source": "file:" + name, "file": name,
                      "snapshot_kind": "local-file", "captured_at": captured,
                      "timestamp": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                      "timestamp_scope": "File modification time, not project activity or release time.",
                      "input_scope": ("Local file snapshot, " + ("bounded prefix" if truncated else "complete supplied file")
                                      + "; files do not verify tests, publication or deployment."),
                      "text": text[:chars_per_file] + ("\n[truncated]" if truncated else "")})
    return items


# Where a repository's current line is, in the order it is looked for.
CURRENT_REFS = ("origin/HEAD", "origin/main", "origin/master", "main", "master")
# A checkout whose HEAD is this much older than the newest session is not what is being worked on.
STALE_CHECKOUT_DAYS = 14


def _git(path: str, *args: str) -> str:
    import subprocess
    try:
        done = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _version_at(path: str, ref: str) -> str:
    for name, pattern in (("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
                          ("package.json", r'"version"\s*:\s*"([^"]+)"')):
        found = re.search(pattern, _git(path, "show", f"{ref}:{name}"))
        if found:
            return f"{found[1]} ({name})"
    return ""


def checkout_state(path: str, newest_session: str = "") -> str:
    """Which branch a checkout is on, how old its HEAD is, and where the project's current line is (#1982).

    After #1965 a project page read the main checkout, which on the owner's
    machine was on an August branch: the page said 1.8.0a3 the week 1.9.0a3
    shipped. The working tree is one branch's state; the version and state
    come from origin/main (else main, else the most recently committed branch),
    and a HEAD weeks older than the project's newest session is named as stale.
    """
    if not (Path(path) / ".git").exists():
        return ""
    head = _git(path, "log", "-1", "--format=%cI", "HEAD")
    if not head:
        return ""
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD") or "detached"
    ref = next((r for r in CURRENT_REFS if _git(path, "rev-parse", "--verify", "--quiet", r + "^{commit}")), "") \
        or _git(path, "for-each-ref", "--sort=-committerdate", "--count=1", "--format=%(refname:short)", "refs/heads")
    lines = [f"Checkout {path}: branch {branch}, HEAD committed {head[:10]}."]
    line_date = _git(path, "log", "-1", "--format=%cI", ref) if ref else ""
    if ref and line_date:
        version = _version_at(path, ref)
        lines.append(f"The project's current line is {ref}, last committed {line_date[:10]}"
                     + (f"; version {version} there." if version else "."))
    newest = newest_session[:10]
    if newest and re.fullmatch(r"\d{4}-\d{2}-\d{2}", newest):
        # Dates only: git writes UTC as `Z`, which Python 3.10's fromisoformat refuses.
        behind = (datetime.fromisoformat(newest).date() - datetime.fromisoformat(head[:10]).date()).days
        if behind > STALE_CHECKOUT_DAYS:
            lines.append(f"This checkout's HEAD is {behind} days older than the newest session ({newest}): its "
                         f"files are not the project's current state. Take the version and state from "
                         f"{ref or 'the newest session'}, not from files read in this checkout.")
    return " ".join(lines)


def _newest_session(root: Path, record: str, page: str) -> str:
    from .project_material import page_state
    seen = re.findall(r"(?m)^- Last seen: (\d{4}-\d{2}-\d{2})", page)
    return max([*seen, str(page_state(root, record).get("last_activity") or "")[:10]])


def _patient(call, *args, attempts: int = 4):
    """One transient timeout must not end a ten-minute gather.

    The owner's first investigation died on the 300th body fetch with a
    ReadTimeout from Graph -- one slow response, and everything gathered
    before it was thrown away. Retried with a short backoff; a provider that
    is really down still fails, after four tries rather than one.
    """
    import time
    for attempt in range(attempts):
        try:
            return call(*args)
        except Exception as error:  # noqa: BLE001 -- the providers raise their own timeout types
            name = type(error).__name__.lower()
            transient = any(part in name for part in ("timeout", "connecterror", "connectionerror")) \
                or "timed out" in str(error).lower()
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def _download(client, email_id: str, folder: str):
    """The two mailboxes save attachments through different doors.

    Outlook: `download_attachments(email_id, out_dir)` -> list of paths.
    Gmail (its mailbox mixin): `download_attachments(email_id, directory, *,
    all_attachments=...)` -> a result dict, because it also reports partial
    saves and budget stops. Both are asked the way they expect.
    """
    import inspect
    parameters = inspect.signature(client.download_attachments).parameters
    if "all_attachments" in parameters:
        return client.download_attachments(email_id, folder, all_attachments=True)
    return client.download_attachments(email_id, folder)


def _saved_paths(result) -> list[str]:
    """Whatever a download returned, the files that are now on disk."""
    if isinstance(result, dict):
        # Gmail's mixin: {'items': [{'status': 'saved', 'path': ...} | {'status': 'failed', ...}],
        # 'complete': bool}. A row without a path was not saved; it is not a file.
        return [str(row["path"]) for row in result.get("items") or []
                if isinstance(row, dict) and row.get("path") and row.get("status", "saved") == "saved"]
    return [str(f) for f in (result or [])]


def _matches(row: dict, handles: list[str], mine: set) -> bool:
    haystack = " ".join([correspondent(row, mine), str(row.get("from", "")), str(row.get("to", "")),
                         str(row.get("subject", ""))]).lower()
    return any(handle in haystack for handle in handles)


def _server_term(kind: str, domain: str) -> str:
    """What each mail server is asked for an organisation's domain.

    Gmail's from:/to:/cc: take a bare domain. Graph's KQL `participants:` does
    not: `participants:unsw.edu.au` answers HTTP 500, which made every org
    investigation in 1.9.0a3 fail (#1981), while `participants:unsw` answers.
    The label is looser; `_matches` keeps only mail on the domain itself.
    """
    return domain.split(".")[0] if kind == "outlook" else domain


def gather(subject: str, handles: list[str], *, days: int, clients: dict, subscriptions: dict,
           progress=None, attachments_dir: Path | None = None,
           sent_only: bool = False, mail_skipped: str = "", stage_progress=None,
           quick: bool = False, archive_root: Path | None = None,
           record: str = "") -> tuple[list[dict], list[str]]:
    """Everything every source holds about the subject, oldest first, plus what was searched.

    `sent_only` is the owner's own page: every message in a mailbox involves
    the owner, so "mail about the owner" is the whole mailbox. What the owner
    wrote is what describes them; what others sent them describes the others.
    """
    handles = [h.strip().lower() for h in handles if h.strip()]
    if days < 1 or not handles:
        raise RemError("Investigation needs a positive day window and at least one subject handle")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    items, coverage = [], []
    own_addresses = set()
    # An org is its domain: "unsw.edu.au" or "@unsw.edu.au" on the page. Only
    # for org pages -- a person's "vern.chan" alias is shaped like a domain too.
    domains = sorted({match[1] for h in handles if (match := DOMAIN_HANDLE.match(h))}) \
        if record.startswith("orgs/") else []
    archived = None
    if archive_root is not None and record.startswith("people/"):
        from .mail_archive import person_material
        archived = person_material(archive_root, record)
    elif archive_root is not None and domains:
        from .mail_archive import domain_material
        archived = domain_material(archive_root, domains, contact_addresses=[h for h in handles if is_address(h)])
    cached_by_provider, cached_start, cached_end = archived if archived else ({}, None, None)
    # A mailbox the user unsubscribed after init stays out, archive or not.
    cached_by_provider = {kind: rows for kind, rows in cached_by_provider.items()
                          if not subscriptions.get(kind, {}).get("unsubscribed")}
    covered_kinds = set()
    # Only a finished archive covers its window. An unfinished one is read for
    # the bodies it holds and the mailbox is still listed, but nothing saved is
    # fetched again: 2,693 of 3,152 were saved and went unread (#2042).
    complete, share = True, ""
    if archived and archive_root is not None:
        from .files import read_json, state_path
        from .mail_archive import saved_share
        manifest = read_json(state_path(archive_root, "mail/archive.json"), {})
        own_addresses.update(address.casefold() for address in manifest.get("owner_addresses", []))
        complete = manifest.get("phase") == "complete"
        if not complete:
            on_disk, target = saved_share(archive_root, manifest)
            share = f" ({on_disk:,} of {target:,} bodies saved so far)"
    for kind in dict.fromkeys([*clients, *cached_by_provider]):
        client = clients.get(kind)
        mine = {a.lower() for a in client.my_addresses()} if client else set()
        if sent_only:
            # Each mailbox knows only its own login. The owner's other addresses
            # are the owner too, not correspondents to search the server for: a
            # first `investigate me` searched for them and found 6 of ~150 mails.
            mine |= {h for h in handles if is_address(h)}
        own_addresses.update(mine)
        local, undated = [], 0
        for item in cached_by_provider.get(kind, []):
            # A saved mail with an unreadable date is that mail's gap, not the
            # run's: one naive Gmail Date stopped `investigate me` (#2013).
            try:
                when = timestamp(item["timestamp"])
            except RemError:
                undated += 1
                continue
            if start <= when < end and (not sent_only or item["role"] == "user"):
                local.append(item)
        if undated:
            coverage.append(f"{kind}: {undated} saved message(s) skipped for an unreadable date")
        if quick:
            local = sorted(local, key=lambda item: item["timestamp"])[-12:]
        items.extend(local)
        attached = 0

        def add_attachments(message_id: str, sender: str, stamp: str, subject: str, scope: str = "") -> None:
            nonlocal attached
            if attachments_dir is None or not hasattr(client, "download_attachments"):
                return
            from .attachments import extract_text
            short = hashlib.sha256(message_id.encode()).hexdigest()[:12]
            folder = attachments_dir / kind / short
            try:
                folder.mkdir(parents=True, exist_ok=True)
                paths = _saved_paths(_patient(_download, client, message_id, str(folder)))
            except Exception as error:  # noqa: BLE001 -- one bad attachment is not the run
                paths = []
                coverage.append(f"{kind}:{short}: attachments could not be saved ({type(error).__name__})")
            for saved in paths or []:
                attached += 1
                items.append({"role": "attachment", "speaker": sender, "timestamp": stamp,
                              "subject": f"{subject} — {Path(saved).name}",
                              "text": extract_text(Path(saved), limit=None), "file": saved,
                              "source": f"{kind}:{short}:{Path(saved).name}",
                              **({"relationship_scope": scope} if scope else {})})

        seen = {item["_mail_id"] for item in local}
        intervals = [(start, end)]
        if archived and kind in cached_by_provider and complete:
            intervals = ([(start, min(end, cached_start))] if start < cached_start else [])
            intervals += ([(max(start, cached_end), end)] if cached_end < end else [])
            intervals = [(begin, finish) for begin, finish in intervals if begin < finish]
        if archived and kind in cached_by_provider:
            covered_kinds.add(kind)
        hit, taken = [], set(seen)
        searched = f"{len(local)} loaded from private init archive{share}"
        if client is None:
            if intervals:
                coverage.append(f"{kind}: {searched}; {len(intervals)} uncovered interval(s), provider unavailable")
            else:
                coverage.append(f"{kind}: {searched}; requested body interval covered by local archive; "
                                "attachments unavailable without provider")
            continue
        for item in local:
            add_attachments(item["_mail_id"], item["speaker"], item["timestamp"], item.get("subject", ""), item.get("relationship_scope", ""))
        # Only a whole address goes to the server: a page line with prose or a
        # citation in it made Gmail match 677 unrelated mails (#1954). A bare
        # domain is not an address; org pages search it through `domains` above.
        emails = sorted({h.strip() for h in handles if is_address(h) and h not in mine})
        unavailable = None
        for begin, finish in intervals:
            if domains and hasattr(client, "list_with"):
                # One server query per domain rather than every header in the
                # window. The server may match loosely; the handles still decide
                # what is kept. A university's mail runs past list_with's
                # 1,000-row default.
                terms = [_server_term(kind, domain) for domain in domains] + emails
                try:
                    rows = [r for term in terms
                            for r in (_patient(partial(client.list_with, max_results=DOMAIN_RESULTS),
                                               term, begin.isoformat(), finish.isoformat()) or [])
                            if on_domains(r, domains) or set(participants(r)).intersection(emails)]
                except ProviderCredentialError as error:
                    # One mailbox failing is that mailbox's gap, not the page's:
                    # a Graph 500 used to end the whole investigation before
                    # Gmail was asked (#1981). Auth failures still stop the run.
                    if error.code != "provider_unavailable":
                        raise
                    unavailable = f"server search failed (HTTP {error.status or '?'})"
                    break
                searched += f"; searched on the server for {', '.join(terms)}"
            elif emails and hasattr(client, "list_with"):
                # A verified address is server-searchable; the local archive
                # supplies the older interval so only gaps need a query.
                rows = [r for address in emails
                        for r in (_patient(client.list_with, address, begin.isoformat(), finish.isoformat()) or [])]
                searched += f"; searched on the server for {', '.join(emails)}"
            else:
                rows, cursor = [], begin
                while cursor < finish:
                    stop = min(cursor + timedelta(days=7), finish)
                    rows += _patient(_list_all, client, cursor, stop)
                    if progress:
                        progress(kind, stop, len(rows))
                    cursor = stop
                rows = [r for r in rows if (on_domains(r, domains) or set(participants(r)).intersection(emails)
                        if domains else _matches(r, handles, mine))]
                searched += f"; scanned {len(rows)} matched mails"
            for row in rows:
                if row["id"] not in taken and (not sent_only or _address(row["from"]) in mine):
                    taken.add(row["id"])
                    hit.append(row)
        if unavailable:
            coverage.append(f"{kind}: {searched}; {unavailable}; not searched")
            continue
        if progress:
            progress(kind, end, len(local) + len(hit))
        if sent_only:
            searched += ", kept the owner's own sent mail"
        mail_to_read = sorted(hit, key=lambda r: str(r["date"]))
        if quick:
            mail_to_read = mail_to_read[-12:]
        for number, r in enumerate(mail_to_read, 1):
            body = _patient(client.get_email_body, r["id"])
            if archive_root is not None:
                from .mail_archive import retain_message
                saved = retain_message(archive_root, kind, r, body, fetched_at=datetime.now(timezone.utc).isoformat())
                body = saved["body"]
                r = {**r, **{key: saved[key] if key in saved else r.get(key)
                            for key in ("date", "from", "to", "cc", "subject")}}
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
            own = _address(r["from"]) in mine or "@" not in _address(r["from"])
            short = hashlib.sha256(r["id"].encode()).hexdigest()[:12]
            scope = RELATED_ORG_SCOPE if domains and not on_domains(r, domains) else ""
            items.append({"role": "user" if own else "other", "speaker": r["from"],
                          "text": body, "timestamp": str(r["date"]),
                          "participants": {key: r.get(key) or ([] if key in ("to", "cc") else "")
                                           for key in ("from", "to", "cc")},
                          "subject": r.get("subject", ""), "source": f"{kind}:{short}",
                          **({"relationship_scope": scope} if scope else {})})
            add_attachments(r["id"], r["from"], str(r["date"]), r.get("subject", ""), scope)
            if stage_progress and (number % 10 == 0 or number == len(mail_to_read)):
                stage_progress(f"gathering {kind} mail", number, len(mail_to_read))
        coverage.append(f"{kind} ({', '.join(sorted(mine))}): {searched} over {days} days, "
                        f"{len(local) + len(hit)} matched, {len(local) + len(mail_to_read)} bodies read"
                        + (" (recent quick sample)" if quick else "")
                        + (f", {len(local)} of them from the private init archive" if local else "")
                        + f", {attached} attachments read")
    for kind in ("outlook", "gmail"):
        if kind not in clients and kind not in covered_kinds:
            # Say it. A mailbox left out used to vanish from coverage, so the model
            # and the reader could not tell "no mail with this person" from "not asked".
            # A mailbox left out on purpose says why; "not connected" sent a user
            # to log in again for a project page that simply does not read mail.
            why = (mail_skipped or ("unsubscribed by the user" if subscriptions.get(kind, {}).get("unsubscribed")
                   else f"not connected (co auth {'google' if kind == 'gmail' else 'microsoft'})"))
            coverage.append(f"{kind}: {why}; not searched")
    from .chat import CHAT_KINDS, collect_chat
    for name, sub in subscriptions.items():
        chat = sub.get("kind") in CHAT_KINDS
        if sub.get("kind") not in KINDS and not chat:
            continue
        if chat and not sub.get("chats"):
            # Chats are read only when the user named them (a linked device sees
            # every group the number is in); none named is a choice, said so.
            coverage.append(f"{name}: no chats chosen, not searched")
            continue
        if sub.get("enabled") is False:
            coverage.append(f"{name}: disabled, not searched")
            continue
        if not Path(sub.get("root", "")).is_dir():
            coverage.append(f"{name}: source directory unavailable, not searched")
            continue
        scoped = {**sub, "enabled": True, "consented": True, "since": start.isoformat()}
        scanned, picked = 0, []
        is_owner = bool(own_addresses.intersection(handles))
        read = collect_chat if chat else collect

        def related(item):
            # A chat line says who said it; mail's rule for the owner applies:
            # what the owner wrote describes them, the whole chat does not.
            # sent_only is the owner's page even when no mailbox is connected
            # to tell us their addresses; a chat knows which lines are theirs.
            if is_owner or (chat and sent_only):
                return not chat or item["role"] == "user"
            said = item["text"] + " " + item.get("project", "")
            if chat:
                said += " " + item.get("speaker", "") + " " + item.get("correspondent", "")
            return any(h in said.lower() for h in handles)
        try:
            window, unfamiliar = _window_items(read, scoped, f"{name} {'chats' if chat else 'sessions'}", stage_progress)
            scanned, picked = len(window), [i for i in window if related(i)]
            if unfamiliar:
                coverage.append(f"{name}: {unfamiliar} user-slot message(s) in an unfamiliar format were not read")
        except RemError as error:
            coverage.append(f"{name}: unreadable ({error})")
        related = len(picked)
        legacy = sum(bool(item.get("timestamp_scope")) for item in picked)
        if legacy:
            coverage.append(f"{name}: {legacy} related legacy message(s) have only a session-start date; "
                            "individual message times were not recorded")
        if quick:
            picked = picked[-12:]
        coverage.append(f"{name}: {scanned} messages in window, {related} related to subject, "
                        f"{len(picked)} read"
                        + (" (recent quick sample)" if quick else "")
                        + (" (account owner's own messages)" if is_owner or (chat and sent_only)
                           else " (handle, sender or chat match)" if chat else " (handle or project match)"))
        items += picked
    items.sort(key=lambda i: i["timestamp"])
    for item in items:
        item.pop("_mail_id", None)
    return items, coverage


# Every item of a session source's window, read once and shared by the
# subjects investigated after it (2026-10-01). A real first run re-read 1,300
# session files for every person, and six threads under one GIL took 13 minutes
# a person. Kept for SESSION_REUSE_SECONDS: a long-lived host sees new sessions.
_WINDOWS: dict = {}
_WINDOWS_LOCK = threading.Lock()
SESSION_REUSE_SECONDS = 600


def _window_items(read, scoped: dict, label: str, stage_progress=None) -> tuple[list[dict], int]:
    """All items `read` returns for `scoped`; one thread reads, the others wait for it."""
    key = (read, json.dumps({**scoped, "since": scoped["since"][:10]}, sort_keys=True, default=str))
    with _WINDOWS_LOCK:
        kept = _WINDOWS.get(key)
        if kept and time.monotonic() - kept[0] < SESSION_REUSE_SECONDS:
            return kept[1]
        items, cursor, told, unfamiliar = [], {}, 0, 0
        while True:
            # This is a full-window gather, not a model input batch. Tiny batches
            # repeatedly re-hash large rollout prefixes while retaining the same
            # eventual window in memory.
            batch = read(scoped, cursor, 4_000, 20_000_000)
            items.extend(batch.items)
            unfamiliar += getattr(batch, 'unrecognised', 0)
            if batch.progress == cursor:
                break
            cursor = batch.progress
            # The count goes in the line itself: the CLI prints a count only
            # beside a total, and sessions have none, so a real run printed
            # 24 identical lines. A batch that added nothing is not news.
            if stage_progress and len(items) > told:
                told = len(items)
                stage_progress(f"gathering {label}: {told:,} scanned", told)
        result = items, unfamiliar
        _WINDOWS[key] = (time.monotonic(), result)
        return result


SEARCH_RESULTS = 20


def mail_search(clients: dict):
    """Read-only mail searches the model may ask for after its first turn (2026-10-01).

    The owner asked that a gap the gathered mail leaves (how two people met, a
    role) can be searched for. The model has no network; this runs its queries
    with `list_search`, reads up to SEARCH_RESULTS bodies, and returns them in
    the gathered mail's shape and source ids, so they cite like the rest.
    """
    def search(queries: list[str]) -> list[dict]:
        found, seen = [], set()
        for query in queries:
            for kind, client in clients.items():
                mine = {a.lower() for a in client.my_addresses()}
                for row in _patient(client.list_search, query, 10) or []:
                    if row["id"] in seen or len(found) >= SEARCH_RESULTS:
                        continue
                    seen.add(row["id"])
                    body = _patient(client.get_email_body, row["id"])
                    head, _, rest = body.partition("--- Email Body ---")
                    body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
                    own = _address(row["from"]) in mine or "@" not in _address(row["from"])
                    found.append({"role": "user" if own else "other", "speaker": row["from"], "text": body,
                                  "timestamp": str(row["date"]), "subject": row.get("subject", ""), "query": query,
                                  "source": f"{kind}:{hashlib.sha256(row['id'].encode()).hexdigest()[:12]}"})
        return found
    return search


def _split_item(item: dict, limit_chars: int, measure=None):
    """Split a long document without losing its text, source or date.

    `measure` is how big a list of parts is; by default its JSON length.
    """
    measure = measure or (lambda parts: len(json.dumps(parts, ensure_ascii=False)))
    if measure([item]) <= limit_chars:
        yield item
        return
    if measure([{**item, "text": ""}]) >= limit_chars:
        raise RemError("Extraction character limit is too small for source metadata; "
                        "increase limits.extract_chars_per_batch")
    remaining = item["text"]
    while remaining:
        low, high = 0, min(len(remaining), limit_chars)
        while low < high:
            middle = (low + high + 1) // 2
            if measure([{**item, "text": remaining[:middle]}]) <= limit_chars:
                low = middle
            else:
                high = middle - 1
        if not low:
            raise RemError("Extraction character limit cannot fit source text; "
                            "increase limits.extract_chars_per_batch")
        yield {**item, "text": remaining[:low]}
        remaining = remaining[low:]


def digest_in_chunks(items: list[dict], config: dict, extractor=None, *, root: Path | None = None,
                     max_calls=None, progress=None) -> tuple[list[dict], dict]:
    """Oldest first, each chunk within the extract limits, one digest item per chunk."""
    from .extract import NOTHING, extraction_instructions, extraction_item, run_extract
    from .files import read_json, state_path, write_json
    limits = config["limits"]
    if extractor is None:
        if root is None:
            raise RemError("co rem root is required for model extraction")
        extractor = lambda chunk, settings, kind: run_extract(chunk, settings, kind, root=root)
    from .runner import INLINE_LIMIT, readable_material
    # Each piece travels in the prompt, beside the extraction Skill. 150k
    # characters never did, so every piece was read from files instead: about
    # 1M input tokens a piece on the owner's notebook, 15 pieces for one person.
    kinds = {str(item.get("source", "")).split(":")[0] for item in items}
    widest = max(len(extraction_instructions(kind).encode("utf-8")) for kind in kinds | {""})
    room = min(limits["extract_chars_per_batch"], INLINE_LIMIT - widest - 2000)
    measure = lambda parts: len(readable_material(parts).encode("utf-8"))
    chunks, current = [], []
    for item in items:
        for part in _split_item(item, room, measure):
            if current and (len(current) >= limits["extract_items_per_batch"]
                            or measure(current + [part]) > room):
                chunks.append(current)
                current = []
            current.append(part)
    if current:
        chunks.append(current)
    if max_calls is not None and len(chunks) > max_calls:
        raise RemError("Extraction exceeds remaining call budget; page preserved")
    digests, usage = [], {}
    for number, chunk in enumerate(chunks, 1):
        kinds = {i["source"].split(":")[0] for i in chunk}
        kind = kinds.pop() if len(kinds) == 1 else ""
        checkpoint = None
        if root is not None:
            # A cancelled page investigation must not pay for every completed
            # digest again. Hash the material, model settings and Skill text so
            # a changed source or prompt cannot reuse stale conclusions.
            fingerprint = hashlib.sha256(json.dumps(
                [chunk, config.get("runner"), config.get("model"), extraction_instructions(kind)],
                ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            checkpoint = state_path(root, f"extracts/investigate/{fingerprint}.json")
        saved = read_json(checkpoint, {}) if checkpoint else {}
        if isinstance(saved, dict) and isinstance(saved.get("notes"), str) and saved["notes"].strip():
            out = {"notes": saved["notes"], "usage": None}
        else:
            out = extractor(chunk, config, kind)
            if checkpoint and isinstance(out.get("notes"), str) and out["notes"].strip():
                write_json(checkpoint, {"notes": out["notes"]})
        for key, value in (out.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + value
        if (out.get("notes") or "").strip() != NOTHING:
            digests.append(extraction_item(out["notes"].strip(), chunk))
        if progress:
            progress("extracting long evidence", number, len(chunks), dict(usage))
    return digests, usage


def searched_sources(coverage: list[str]) -> list[str]:
    """The sources this code searched, for the page's status line.

    Not every coverage line is a source: `evidence:` says how the material was
    laid out, and the 1.9.0a1 run stamped `(…, evidence)` on real pages (#1962).
    A source searched with nothing found stays: the daily round reads the line
    to know which sources a page has already been checked against.
    """
    notes = ("budget", "digest", "evidence:")
    labels = (line.split(" (")[0].split(":")[0] for line in coverage
              if not line.startswith(notes) and "not searched" not in line and ": unreadable" not in line)
    # A source is one word (outlook, gmail, claude-code); every note is a
    # phrase. Ody Zhou's line read "(outlook, gmail, codex, claude-code,
    # Requested investigation window)" (#2045).
    return list(dict.fromkeys(label for label in labels if re.fullmatch(r"[a-z][a-z0-9-]*", label)))


def drop_map_count(page: str) -> str:
    """The map's "Observed mail count" History bullet, once the mail itself was read.

    The map writes it from a window-limited count; after an investigation read
    32 of Jiexuan Deng's mails the page still said "Observed mail count: 2"
    (#2045). Kept while it is History's only entry."""
    head, marker, rest = page.partition("\n## History\n")
    if not marker:
        return page
    section, sep, tail = rest.partition("\n## ")
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    kept = [line for line in section.splitlines() if not line.startswith("- Observed mail count:")]
    if len(bullets) < 2 or len(kept) == len(section.splitlines()):
        return page
    return head + marker + "\n".join(kept) + ("\n" if section.endswith("\n") else "") + sep + tail


def last_investigated(page: str):
    """The last pass that read this page's sources: `investigated` or `written`.

    `co rem projects write` stamps `written <date>`; counted only as
    "investigated", the next investigation of that project re-read 150 days,
    397 items and 1.58M tokens after a write the same day (#1983)."""
    from datetime import date
    line = next((l for l in page.splitlines() if l.startswith("Investigation:")), "")
    days = re.findall(r"(?<!not )(?:investigated|written) (\d{4}-\d{2}-\d{2})", line)
    return max(date.fromisoformat(d) for d in days) if days else None


def window_since(page: str, default: int = 730) -> int:
    """Days to gather for a page: since its last investigation, else `default`.

    The script already read everything before that date into the page; asking
    again re-read months of mail to add a week (owner, 2026-09-30)."""
    last = last_investigated(page)
    if not last:
        return default
    return max(1, (datetime.now(timezone.utc).date() - last).days + 1)


RECENT_PROJECT_DAYS = 28
RECENT_PROJECT_LIMIT = 8


def recent_projects(root: Path) -> str:
    """The owner's projects of the last four weeks, from the map, for the owner's turn (#2027).

    The owner page named no project of the last weeks although its Skill asks
    for them: the turn had 1,477 session messages and cited 3. The map already
    holds each project's sessions and dates; the window ends at the map's own
    date, so the list does not move with the clock. Newest first.
    """
    from datetime import date
    from .files import read_json, state_path
    state = read_json(state_path(root, "map.json"), {})
    rows = [row for row in state.get("projects") or [] if row.get("last") and row.get("record")]
    if not rows:
        return ""
    end = str(state.get("started") or max(row["last"] for row in rows))[:10]
    since = (date.fromisoformat(end) - timedelta(days=RECENT_PROJECT_DAYS)).isoformat()
    rows = sorted((row for row in rows if row["last"][:10] >= since),
                  key=lambda row: (row["last"], row.get("sessions") or 0), reverse=True)[:RECENT_PROJECT_LIMIT]
    lines = [f"- {row.get('name') or row['record']} ({row['record']}): {row.get('sessions') or 0} sessions, "
             f"{str(row.get('first') or '?')[:10]} to {row['last'][:10]}" for row in rows]
    return ("The owner's coding projects from " + since + " to " + end + ", from the map's sessions, newest "
            "first. The lead's \"working on now\" and `Who they are` name the busiest of these, dated, with what "
            "the user did there from the session messages; cite those messages. Context, not evidence:\n"
            + ("\n".join(lines) if lines else "- none in these four weeks"))


def _keep_facts(notebook: Notebook, root: Path, record: str, rows: list[dict]) -> None:
    """Nothing new to read, but a fact the material holds is missing from the page:
    put it in its field with its source, no model needed (#2068)."""
    from . import facts
    with maintenance_lock(root):
        page = notebook.read(record)
        kept, restored = facts.keep_extracted(record, facts.upgrade(record, page), rows)
        if restored:
            notebook.write(record, kept)


def investigate(root: Path, record: str, subject: str, handles: list[str], *, days: int,
                clients: dict, subscriptions: dict, runner=None, extractor=None, progress=None, max_calls=None,
                sent_only: bool = False, mail_skipped: str = "", stage_progress=None,
                quick: bool = False) -> dict:
    """Fill the page's gaps from everything gathered; the page itself is the first input."""
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise RemError(f"{record} does not exist; create it with `co rem stub` first")
    if runner is None:
        # Seconds now, not after the gather: the model's co ai once could not
        # find this Skill, and said so only after minutes of fetching mail.
        from . import runner as runner_module
        runner_module.check_skill(root, "investigate")
    if stage_progress:
        stage_progress("gathering sources")
    related = org_contact_context(notebook, record)
    own_domains = (related["domains"] or org_domains(notebook.read(record))) if record.startswith("orgs/") else []
    search_handles = list(dict.fromkeys([*handles, *own_domains, *related["addresses"]]))
    items, coverage = gather(subject, search_handles, days=days, clients=clients, subscriptions=subscriptions,
                             progress=progress, attachments_dir=root / ".state" / "attachments",
                             sent_only=sent_only, mail_skipped=mail_skipped, stage_progress=stage_progress,
                             quick=quick, archive_root=root, record=record)
    coverage.append(f"Requested investigation window: {days} days ending "
                    f"{datetime.now(timezone.utc).date().isoformat()}")
    last = last_investigated(notebook.read(record))
    # Read from everything gathered, before anything is filtered, laid out in
    # files or sampled: the turn searches files for what it thinks to look for,
    # and Ody's phone sat in a signature it never opened (#2068). A mail the
    # page already cites still has its signature. On a page investigated
    # before, the window is not the whole history, so its first date is not
    # the first contact.
    from . import facts
    from .fact_extract import extract, facts_item
    config = read_config(root)
    fact_rows = [] if record.startswith("projects/") else [
        row for row in extract([item for item in items if not item.get("relationship_scope")], handles,
                               owner=sent_only, timezone=config["schedule"]["timezone"])
        if not (last and row["field"] == "First contact")
        and not (related["candidates"] and row["field"] in ("First contact", "Last contact"))]
    facts_before = facts.coverage(notebook.read(record), record)
    if last:
        # The window is whole days, so an investigation straight after another
        # re-gathers the mail the page already cites: 102k tokens to be told
        # it was "already represented as source [21]" (#2015). What the page
        # cites, it has read.
        cited = notebook.read(record).partition("\n## Sources\n")[2]
        fresh = [item for item in items if not item.get("source") or item["source"] not in cited]
        if related["candidates"] and any(item.get("relationship_scope") for item in fresh):
            coverage.append("Related-domain comparison: previously cited primary correspondence retained "
                            "to check offer dates and terms against the newly gathered contact context")
        else:
            if len(fresh) < len(items):
                coverage.append(f"{len(items) - len(fresh)} gathered item(s) already cited on the page, not re-read")
            items = fresh
    if last and not items and not record.startswith("projects/"):
        _keep_facts(notebook, root, record, fact_rows)
        raise _nothing_new(record, subject, coverage, last)
    gathered_sources = {item["source"] for item in items if item.get("source")}
    refusal = refused_for(root, record)
    if last:
        # The page already reflects what came before; say so where the turn
        # reads it, so it adds the new material instead of rewriting the page.
        coverage.append(f"Page last updated from its sources {last.isoformat()}: it already reflects "
                        "material before that date; add only what this material says that is new.")
    available_items = len(items)
    if quick:
        items = quick_evidence(items)
        coverage.append(f"Quick first pass: reviewed {len(items)} of {available_items} gathered items; "
                        "individual texts capped at 2,500 characters. Other material was not evaluated; "
                        "do not claim comprehensive coverage or resolve unsupported conflicts.")
    gathered_items = len(items)
    leads = []
    if record.startswith("projects/"):
        # The model reads the page's Paths too; a worktree left there is the
        # stale copy it would otherwise quote as current (#1955).
        corrected = collapse_worktree_paths(notebook.read(record))
        if corrected != notebook.read(record):
            notebook.write(record, corrected)
        leads = project_file_inventory(corrected)
        if leads:
            items.append({"role": "project-inventory", "source": "investigation:project-inventory",
                          "text": "Candidate local evidence files, not proof of their contents:\n" +
                                  "\n".join(leads),
                          "timestamp": datetime.now(timezone.utc).isoformat()})
        newest = _newest_session(root, record, corrected)
        for path in project_paths(corrected)[:4]:
            state = checkout_state(path, newest)
            if state:
                items.append({"role": "checkout-state", "source": f"git:{path}:checkout-state", "text": state,
                              "timestamp": datetime.now(timezone.utc).isoformat()})
    if not gathered_items and not leads:
        # Nothing about the subject, so nothing to write from: the page and the
        # coverage note are not material (#1974).
        raise _nothing_found(record, subject, coverage, me=sent_only)
    if stage_progress:
        stage_progress("preparing evidence", len(items))
    from .inquiry import routing
    original_material = None
    if routing(root):
        import uuid

        original_material = state_path(root, f"evidence/{uuid.uuid4().hex}.json")
    # Room for the material after the page, the coverage and the Skill itself.
    from .runner import instructions, page_kind_of, run_stage
    # The instructions this page's turn is actually given (task_prompt), not
    # the no-page-kind worst case, which carries every page shape and the CLI
    # reference and left ~33k characters less room for material.
    overhead = (len(instructions("investigate", page_kind=page_kind_of(record), owner=sent_only))
                + len(notebook.read(record)) + 4000)
    room = config["limits"]["input_chars_per_batch"] - overhead
    from .tier import current
    summary = current(root, config) == "summary"
    if summary:
        # A plain model reads nothing it is not handed: the page's whole
        # material travels in the one prompt, so it must fit there (#1847).
        from .runner import INLINE_LIMIT
        room = min(room, INLINE_LIMIT - overhead)
    repository_items = []
    if record.startswith("projects/"):
        from .project_pages import FILE_SNAPSHOT_CHARS, repository_snapshots
        states = [item for item in items if item.get("role") == "checkout-state"]
        items = [item for item in items if item.get("role") != "checkout-state"]
        files = project_file_texts(leads) if summary else project_file_texts(
            leads, max_files=len(leads), chars_per_file=FILE_SNAPSHOT_CHARS)
        repository_items = repository_snapshots(states + files)
        if last and not gathered_items:
            supplied = read_json(state_path(root, f"projects/{Path(record).stem}/file-inventory.json"), {})
            previous = supplied.get("provided_sources")
            same = (set(previous) == {item["source"] for item in repository_items}) if previous is not None else all(
                item["source"] in cited for item in repository_items)
            if same:
                raise _nothing_new(record, subject, coverage, last)
        items += repository_items
    gathered_sources.update(item["source"] for item in repository_items)
    if refusal and gathered_sources and gathered_sources <= set(refusal["sources"]):
        raise _refused_again(record, subject, refusal)
    if room <= 0:
        raise RemError("Configured input limit cannot fit the current page and investigation Skill")
    gathered_chars = sum(len(json.dumps(i, ensure_ascii=False)) for i in items)
    usage_by_stage = {}
    synthesis_calls = 3 if routing(root) else 1
    if max_calls is not None and max_calls < synthesis_calls:
        raise RemError("Insufficient call budget for investigation; page preserved")
    now = datetime.now(timezone.utc).isoformat()
    original_items = items
    evidence_dir = None
    if gathered_chars > room and summary:
        # A summary-tier model cannot search files (#1847), so it is handed
        # digests of the material in order, the shape investigation had before #1850.
        from .inquiry import stage_config
        items, usage_by_stage["extract"] = digest_in_chunks(
            items, stage_config(root, config, "extract"), extractor, root=root,
            max_calls=None if max_calls is None else max_calls - synthesis_calls, progress=stage_progress)
        coverage.append(f"digest: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one summary-tier turn; summarised in {len(items)} chunk(s) first")
        if not items:
            # Every digest said there was nothing worth keeping: the page turn
            # would have only the page and this note to write from.
            raise _nothing_found(record, subject, coverage, me=sent_only, digested=True,
                                 usage=usage_by_stage["extract"] or None)
    elif gathered_chars > room:
        if stage_progress:
            stage_progress("writing evidence files")
        # Too much for one turn. Not "keep the newest and drop the rest": the
        # oldest mail is where a relationship's terms were set. And not
        # "summarise it all first" either: that was 39 digest calls and 75
        # minutes for the owner's page (#1850). The material goes into files
        # and the one investigate turn searches them for what the page needs.
        import shutil
        import uuid

        from .evidence import write_evidence
        evidence_dir = state_path(root, f"evidence/{uuid.uuid4().hex}")
        shutil.rmtree(evidence_dir, ignore_errors=True)
        laid_out = write_evidence(evidence_dir, items)
        index_text = laid_out["index"].read_text(encoding="utf-8")
        shown = index_text if len(index_text) <= room // 2 else (
            index_text[:room // 2] + f"\n[Index continues in {laid_out['index']}; read the rest there.]\n")
        items = [{"role": "evidence-index", "source": "investigation:evidence", "timestamp": now,
                  "file": str(laid_out["index"]), "sources": laid_out["sources"],
                  "text": (f"The gathered evidence ({len(laid_out['sources'])} items, {laid_out['chars']:,} "
                           f"characters) did not fit one turn and has NOT been summarised. It is in files under "
                           f"{evidence_dir}. Each file is a month of one mailbox, an attachment, a session or "
                           "a chat, normally grouped near 40k characters (one large source may be longer): read the files that matter whole, newest first, rather "
                           "than many small pieces (every tool call re-sends this whole turn); use rg to find "
                           "which files. Cite the source id from the `###` heading of each entry you rely on. "
                           "In your final reply, list the files you read and the questions left open.\n\n"
                           + shown)}]
        coverage.append(f"evidence: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one turn; written to {laid_out['files']} files and searched, "
                        "not summarised first")
    from .page_review import normalize
    if original_material:
        write_json(original_material, original_items)
    # `sent_only` is `investigate me`: the owner's own page, with its own spec (#2008).
    current_page = normalize(record, notebook.read(record), owner=sent_only)
    prompt_items = [
        {"role": "page", "record": record, **({"owner": True} if sent_only else {}),
         "text": f"The page as it stands, at {record}. Fill its Unknowns, update what "
                 f"has moved, keep what is right:\n\n{current_page}",
         "timestamp": now, "source": "investigation:page"},
        {"role": "coverage", "text": "Sources searched for handles " + ", ".join(search_handles) + ":\n"
                                     + "\n".join(coverage), "timestamp": now, "source": "investigation:coverage"},
    ] + ([{"role": "org-contact-context", "source": "investigation:org-contact-context", "timestamp": now,
           "candidates": related["candidates"], "text": "These domain pages share a canonical contact candidate. "
           "The map may have grouped addresses by display name; this is not proof of common person, company "
           "or legal identity. Compare the dated primary messages before using cross-domain terms or closing "
           "threads. Notebook links are context, not evidence; keep distinct offers and unresolved identity explicit."}]
         if related["candidates"] else []) + ([{"role": "org-pages", "source": "investigation:org-pages", "timestamp": now,
           "text": "Organisation pages this notebook already has"
                   + (" for the subject's mail domains" if record.startswith("people/") else "")
                   + ". Where the material shows the subject belongs to one, write its field (Company, or "
                     "Organisation on a project page) as a link, [Name](../orgs/<file>.md). Context, not "
                     "evidence:\n" + "\n".join(f"- {line}" for line in linkable)}]
         if (linkable := org_pages(notebook, record, handles)) else []) + (
        [{"role": "recent-projects", "source": "investigation:recent-projects", "timestamp": now, "text": recent}]
         if sent_only and (recent := recent_projects(root)) else []) + (
        [{"role": "quick-first-pass", "source": "investigation:quick-scope",
           "timestamp": now, "text": "This is a bounded, partial first pass. Use only the supplied sample; "
                                     "state the sampling limit in your final reply, not on the page."}]
         if quick else []) + ([facts_item(fact_rows, config["schedule"]["timezone"])] if fact_rows else []) + items
    if original_material:
        prompt_items.append({"role": "original_evidence", "source": "investigation:original-evidence",
                             "text": f"Original uncompressed evidence is retained at {original_material}. Read it to check summaries and counterevidence.",
                             "file": str(original_material), "timestamp": now})
    # Both runners are `co ai`: it is the orchestrator, and the runner setting
    # only picks which harness answers the Skill -- our own loop, or Codex
    # delegated through `co ai --harness codex`. Either one can reach the web.
    if runner is None:
        runner = partial(run_stage, search=mail_search(clients)) if clients else run_stage
    if stage_progress:
        stage_progress("writing investigation")
    try:
        result = runner(notebook, prompt_items, config, stage="investigate")
    except RemError as error:
        if "rejected" in str(error):
            _remember_refusal(root, record, list(gathered_sources), str(error))
        raise
    else:
        _forget_refusal(root, record)
    finally:
        # Copies of private mail do not accumulate under .state, run after run;
        # the report keeps which files were read. The routed run's uncompressed
        # copy is one too, and was left behind every time.
        if evidence_dir is not None:
            import shutil
            shutil.rmtree(evidence_dir, ignore_errors=True)
        if original_material is not None:
            original_material.unlink(missing_ok=True)
    if stage_progress:
        stage_progress("recording result")
    usage_by_stage["investigate"] = result.get("usage")
    total = {}
    for stage_usage in usage_by_stage.values():
        for key, value in (stage_usage or {}).items():
            total[key] = total.get(key, 0) + value
    # The status line names the sources this code searched. Whether the web
    # was reached is the Skill's to report, on the page: a real run (2026-09-14)
    # had `co browser` fail inside the thread while this line still said "web".
    record_result(root, notebook, record, result.get("review_candidates", []),
                  searched_sources(coverage), changed=record in result.get("changed", []),
                  repository_items=repository_items)
    return {"record": record, "items": len(items), "items_available": available_items,
            "quick": quick, "chars_gathered": gathered_chars,
            "tokens_estimated_in": gathered_chars // 4, "coverage": coverage,
            "changed": result.get("changed", []), "usage": total or None,
            "usage_by_stage": usage_by_stage, "report": result.get("report", ""),
            "facts": {"before": facts_before, "after": facts.coverage(notebook.read(record), record),
                      "extracted": sum(1 for row in fact_rows if row["field"] in facts.fields(record))},
            "instructions_chars": {"investigate": result.get("instructions_chars")}}


def record_result(root, notebook, record: str, review_candidates: list, searched: list[str],
                  *, changed: bool = False, repository_items=(), skill_records=()) -> None:
    """Keep what a finished investigation proposed and mark its page investigated.

    It waits for the lock: the model turn is already paid for, and with several
    pages in flight (the first run writes four at once) two finish together.
    """
    with maintenance_lock(root, wait=60):
        from .reviews import ingest
        ingest(root, review_candidates)
        if changed:
            from .project_pages import retain_repository_context
            from .reader_model import _source_ids
            retain_repository_context(root, repository_items, _source_ids([{"text": notebook.read(record)}]))
            from .skill_runs import retain_skill_records
            retain_skill_records(root, skill_records, _source_ids([{"text": notebook.read(record)}]))
            page = notebook.read(record)
            if drop_map_count(page) != page:
                notebook.write(record, drop_map_count(page))
        notebook.note_investigation(record, ", ".join(searched))
        if repository_items and record.startswith("projects/"):
            write_json(state_path(root, f"projects/{Path(record).stem}/file-inventory.json"), {
                "provided_sources": sorted({item["source"] for item in repository_items}),
                "scope": "Material supplied in the completed investigation; not proof every file was read."})
        from .store import refresh_safely
        refresh_safely(root)
