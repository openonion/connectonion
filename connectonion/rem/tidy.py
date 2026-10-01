"""Tidy a notebook an older version made, by today's rules (#1999, #2008).

Maps get better and the pages an older one made stay. The owner's upgraded
notebook kept services as people (Apple ID, notify@x.com, GitHub's unsub+
reply addresses), two of the owner's own addresses queued as people, three
pairs of pages for one skill, and old pages carrying `web: not searched` and
`investigation:coverage` citations. Every map and every sync calls `tidy`
first, and a map calls it again at its end (#2018). It is idempotent and calls no model. Nothing is deleted: pages move to
`.state/archived/` (folded ones leave an alias, as `merge.merge_into` does),
and every action -- each removed line with its text -- is appended to
`.state/tidy.json`. A page someone investigated is never moved or folded.
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from datetime import date
from pathlib import Path

from .files import Notebook, maintenance_lock, read_json, state_path, write_json

LOG = "tidy.json"
WEB_LINE = re.compile(r"^\s*- web: not searched\b.*$")
COVERAGE = re.compile(r"^\s*- \[(W?\d+)\] investigation:coverage\b.*$")
# The runner's own deterministic citation for a project's empty session window
# (runner._project_window_notice) backs a fact it states; only the model's kept.
RUNNER_COVERAGE = "source-collection record for this investigation"


def tidy(root: Path, *, lock_held: bool = False, own_addresses: bool = True) -> dict:
    """Tidy under the notebook lock; returns {action: [pages]} for what changed."""
    root = Path(root)
    if not (root / ".state").is_dir():
        return {}
    with nullcontext() if lock_held else maintenance_lock(root):
        notebook, actions = Notebook(root), []
        state = read_json(state_path(root, "map.json"), {})
        actions += _services(notebook, state)
        actions += _strangers(notebook, state)
        actions += _empty_orgs(notebook, state)
        actions += _own_addresses(notebook, state) if own_addresses else []
        actions += _skills(notebook)
        actions += _orgs(notebook)
        actions += _lines(notebook)
        actions += _dead_links(notebook)
        if not actions:
            return {}
        log = read_json(state_path(root, LOG), [])
        write_json(state_path(root, LOG), log + [{"date": date.today().isoformat(), **action} for action in actions])
        summary = {}
        for action in actions:
            summary.setdefault(action["action"], []).append(action["page"])
        return {key: sorted(set(pages)) for key, pages in summary.items()}


def _archive(notebook: Notebook, record: str, into: str = "") -> str:
    """Move the page out, and leave no link to it behind.

    Org pages kept `[Airbnb](../people/airbnb-….md)` to a service page tidy had
    archived; the reader showed the name and the click went nowhere (#2054).
    A page folded into another is relinked there, as `merge` does; an archived
    one keeps its name as text."""
    target = notebook.root / ".state" / "archived" / record
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook.path(record).replace(target)
    if into:
        from .merge import _relink
        _relink(notebook, record, into)
    return f".state/archived/{record}"


LINK = re.compile(r"\[([^\]]+)\]\(((?:\.\./|\./)*)([\w./-]+\.md)\)")


def _dead_links(notebook: Notebook) -> list[dict]:
    """Links to a page this tidy (or an earlier one) archived keep their name as text."""
    archived = notebook.root / ".state" / "archived"
    actions = []
    for page in notebook.list():
        text = notebook.read(page)

        def unlink(match):
            # A Markdown link is relative to the page's own folder.
            target = _normal(f"{Path(page).parent.as_posix()}/{match[2]}{match[3]}")
            if (notebook.root / target).is_file() or not (archived / target).is_file():
                return match[0]
            actions.append({"action": "unlinked archived page", "page": page, "target": target})
            return match[1]
        updated = LINK.sub(unlink, text)
        if updated != text:
            notebook.write(page, updated)
    return actions


def _normal(path: str) -> str:
    parts = []
    for part in path.split("/"):
        if part == "..":
            parts = parts[:-1]
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def _services(notebook: Notebook, state: dict) -> list[dict]:
    """People pages for services and automated senders, never investigated: archived."""
    from .census import written
    from .map import service_page
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record") and row.get("address")}
    automated = {row["address"].casefold() for row in state.get("automated_correspondents", []) if row.get("address")}
    owner = (state.get("owner") or {}).get("record")
    moved = []
    for person in notebook.people():
        record = person["path"]
        if record == owner or written(notebook.read(record)):
            continue
        if service_page(person["title"], person["emails"], rows.get(record), automated):
            moved.append({"action": "archived service", "page": record, "archived": _archive(notebook, record)})
    return moved


def _strangers(notebook: Notebook, state: dict) -> list[dict]:
    """People pages the map made for someone the owner never corresponded with, never written: archived.

    One mail either way, or a newsletter that never heard back: 295 of the
    owner's 367 correspondents, and most of 374 empty people pages (#2057).
    A later map makes the page again once mail goes both ways."""
    from .census import written
    from .map import worth_a_page
    owner = (state.get("owner") or {}).get("record")
    moved = []
    # A map that gave no page names the old one it left in `without_page`;
    # an older map's row is judged by its counts.
    rows = [*state.get("people", []), *({**row, "sent": 0, "received": 0} for row in state.get("without_page", []))]
    for row in rows:
        record = row.get("record")
        if (not record or record == owner or "sent" not in row or not notebook.path(record).is_file()
                or written(notebook.read(record))):
            continue
        if row.get("classification") == "automated candidate" or not worth_a_page(row.get("sent", 0),
                                                                                  row.get("received", 0)):
            moved.append({"action": "archived one-way correspondent", "page": record,
                          "archived": _archive(notebook, record)})
    return moved


def _empty_orgs(notebook: Notebook, state: dict) -> list[dict]:
    """Organisation pages the map made whose people all lost their pages, never written: archived."""
    from .census import written
    moved = []
    for row in state.get("orgs", []):
        record = row.get("record")
        if (not record or not row.get("people") or not notebook.path(record).is_file()
                or written(notebook.read(record))
                or any(notebook.path(person).is_file() for person in row["people"])):
            continue
        moved.append({"action": "archived organisation", "page": record, "archived": _archive(notebook, record)})
    return moved


def _orgs(notebook: Notebook) -> list[dict]:
    """Organisation pages for a mailbox provider or an event relay, never investigated: archived (#2018).

    Where someone keeps their mail is not who they work for: orgs/yahoo-com-hk
    and orgs/luma-mail-com were on the 1.9.0a5 acceptance notebook.
    """
    from .census import written
    from .map import RELAY
    from .scan import personal_mailbox
    moved = []
    for record in notebook.list("orgs"):
        text = notebook.read(record)
        section = text.partition("## Domains\n")[2].split("\n## ", 1)[0]
        domains = re.findall(r"^- ([A-Za-z0-9.-]+)\s*$", section, re.M)
        if written(text) or not domains:
            continue
        if all(personal_mailbox(domain) or RELAY.search("x@" + domain) for domain in domains):
            moved.append({"action": "archived organisation", "page": record, "archived": _archive(notebook, record)})
    return moved


def _own_addresses(notebook: Notebook, state: dict) -> list[dict]:
    """The owner's own addresses on pages of their own: folded into the owner's page.

    Own means confirmed (already one of the owner's addresses) or clearly own:
    never replied to, and carrying the owner's name or confirmed address
    (`map.looks_own`). Also narrows the saved "Possibly yours" list the same way.
    """
    from .census import written
    from .map import looks_own, owner_tokens
    owner = state.get("owner") or {}
    record = owner.get("record")
    if not record or not notebook.path(record).is_file():
        return []
    title = notebook.read(record).split("\n", 1)[0].lstrip("# ").strip()
    confirmed = {address.casefold() for address in owner.get("addresses") or []}
    tokens = owner_tokens(confirmed, "" if "@" in title or title == "Account owner" else title)
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record")}
    folded, added = [], []
    for person in notebook.people():
        page, emails = person["path"], {email.casefold() for email in person["emails"]}
        if page == record or not emails or written(notebook.read(page)):
            continue
        row = rows.get(page) or {}
        group = [{"address": email, "name": row.get("name", ""), "sent": row.get("sent", 0),
                  "received": row.get("received", 1)} for email in sorted(emails)]
        if emails <= confirmed or (tokens and len(group) == 1 and looks_own(group, tokens)):
            evidence = ("confirmed as the owner's own address (owner.addresses)" if emails <= confirmed else
                        f"{group[0]['sent']} sent, none received, carrying the owner's name (people)")
            _fold_owner(notebook, record, page, sorted(emails), evidence)
            folded.append({"action": "folded into the owner's page", "page": page, "into": record,
                           "addresses": sorted(emails), "archived": f".state/archived/{page}"})
            added += sorted(emails - confirmed)
    asked = state.get("possible_own_addresses") or []
    kept = [row for row in asked if row.get("address", "").casefold() not in confirmed | set(added)
            and (not tokens or looks_own([{**rows.get(row.get("record"), {}), **row, "received": 0}], tokens))]
    if added or kept != asked:
        owner["addresses"] = sorted(confirmed | set(added))
        state.update(owner=owner, possible_own_addresses=kept)
        write_json(state_path(notebook.root, "map.json"), state)
    own = confirmed | set(added)
    return (folded + _resolved_uncertainties(notebook, record, own)
            + _owner_lines(notebook, record, {row.get("address", "").casefold() for row in kept}))


ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CITED = re.compile(r"(?:\s*\[W?\d+\])+\s*$")


def _resolved_uncertainties(notebook: Notebook, record: str, own: set[str]) -> list[dict]:
    """Uncertainties lines about addresses that are now all the owner's: removed (#2028).

    The 1.9.0a6 acceptance page still said whether two folded addresses were
    his "remains unresolved". A line that also names an address still open
    stays, since it is still true of that one; "Possibly" lines are `_owner_lines`'s.
    """
    from .map import POSSIBLY
    text = notebook.read(record)
    head, found, rest = text.partition("## Uncertainties\n")
    if not found:
        return []
    body, sep, tail = rest.partition("\n## ")
    kept, gone = [], []
    for line in body.split("\n"):
        named = {address.casefold() for address in ADDRESS.findall(line)}
        if line.startswith("- ") and not line.startswith(POSSIBLY) and named and named <= own:
            gone.append(line)
        else:
            kept.append(line)
    if not gone:
        return []
    if not any(line.startswith("- ") for line in kept):
        kept.insert(0, "- Unknown")
    notebook.write(record, head + found + "\n".join(kept) + sep + tail)
    return [{"action": "removed line", "page": record, "line": line} for line in gone]


def _cite(text: str, evidence: str) -> tuple[str, int]:
    """`text` with a new numbered source for `evidence` in its Sources section, and its number."""
    head, found, rest = text.partition("## Sources\n")
    numbers = [int(n) for n in re.findall(r"^- \[(\d+)\]", rest.split("\n## ", 1)[0], re.M)]
    number = max(numbers, default=0) + 1
    line = f"- [{number}] .state/map.json — {evidence}"
    if not found:
        return text.rstrip("\n") + f"\n\n## Sources\n{line}\n", number
    if rest.startswith("- (none yet)"):
        return head + found + line + rest[len("- (none yet)"):], number
    body, sep, tail = rest.partition("\n\n")
    return head + found + body + "\n" + line + sep + tail, number


def _owner_lines(notebook: Notebook, record: str, asked: set[str]) -> list[dict]:
    """The owner's "Possibly also the owner's" lines: one per address still asked, no others (#2017)."""
    from .map import POSSIBLY, owner_possibly
    text, seen, lines, gone = notebook.read(record), set(), [], []
    for line in text.split("\n"):
        if not line.startswith(POSSIBLY):
            continue
        address = line[len(POSSIBLY):].split(" ", 1)[0].casefold()
        if address in asked and address not in seen:
            seen.add(address)
            lines.append(line)
        else:
            gone.append(line)
    if not gone:
        return []
    notebook.write(record, owner_possibly(text, lines))
    return [{"action": "removed line", "page": record, "line": line} for line in gone]


def _fold_owner(notebook: Notebook, owner: str, page: str, emails: list[str], evidence: str) -> None:
    """The addresses join the owner's contact lines, each cited to the map's evidence
    (#2028); the page, map output only, is archived with an alias. Its
    correspondent lines ("classification unassessed", a mail count as someone
    else) would say the wrong thing on the owner's page."""
    from .skill_map import _alias
    text, number = notebook.read(owner), 0
    for label in ("Email", "Handles", "Also known as"):
        match = re.search(rf"^(- {label}: )(.*)$", text, re.M)
        if not match:
            continue
        known = [part.strip() for part in match[2].split(",") if part.strip()
                 and CITED.sub("", part).strip() != "Unknown"]
        bare = {CITED.sub("", part).strip().casefold() for part in known}
        new = [email for email in emails if email not in bare]
        if not new:
            continue
        if not number:
            text, number = _cite(text, evidence)
        line = match[1] + ", ".join([*known, *(f"{email} [{number}]" for email in new)])
        text = re.sub(rf"^- {label}: .*$", lambda _: line, text, count=1, flags=re.M)
    notebook.write(owner, text)
    _archive(notebook, page, into=owner)
    _alias(notebook, page, owner, "the owner's own address")


def _skills(notebook: Notebook) -> list[dict]:
    """Two catalog pages for one skill: the page named by its folder folds into the named one.

    Read from the pages, not from a scan, so it needs no working directory: a
    page titled `changxing-nonfiction-refine` joins `nonfiction-refine` when
    the two describe the skill the same way or list files with the same bytes
    (`skill_map._join_renamed` keeps a fresh map from making the pair).
    """
    from .census import written
    from .merge import merge_into
    from .skill_map import _title
    pages = {record: notebook.read(record) for record in notebook.list("skills")
             if record.startswith("skills/catalog/") and record != "skills/catalog/index.md"}
    titles = {_title(text).casefold(): record for record, text in pages.items()}
    folded = []
    for record, text in pages.items():
        title = _title(text).casefold()
        target = next((titles[name] for name in titles if name != title and title.endswith("-" + name)), None)
        if not target or written(text) or not _same_skill(text, pages[target]):
            continue
        merge_into(notebook, target, record, "same skill, named by its folder")
        folded.append({"action": "folded duplicate skill", "page": record, "into": target,
                       "archived": f".state/archived/{record}"})
    return folded


def _described(text: str) -> str:
    match = re.search(r"^## What it does\n(.+)$", text, re.M)
    value = match.group(1).strip() if match else ""
    return "" if value.startswith("Unknown") else value


def _same_skill(one: str, other: str) -> bool:
    from .skill_map import _listed_files

    def contents(text):
        return {Path(path).read_bytes() for path in _listed_files(text) if Path(path).is_file()}
    return bool(_described(one) and _described(one) == _described(other)) or bool(contents(one) & contents(other))


def _lines(notebook: Notebook) -> list[dict]:
    """Lines about the run rather than the subject, and model-written coverage citations, removed line by line.

    `web: not searched` at first; then any bullet `page_review.TOOL_TEXT`
    recognises above Sources, such as Tamara's "The current collector reports
    50 matching Outlook messages" (#2058). A contact field keeps its label."""
    from .page_review import CONTACT_LINE, TOOL_TEXT
    removed = []
    for record in notebook.list():
        text = notebook.read(record)
        head = text.partition("\n## Sources\n")[0]
        if "investigation:coverage" not in text and not any(
                TOOL_TEXT.search(line) for line in head.split("\n") if line.lstrip().startswith("- ")):
            continue
        keys = [match[1] for match in map(COVERAGE.match, text.split("\n"))
                if match and RUNNER_COVERAGE not in match[0]]
        kept, gone, above = [], [], True
        for line in text.split("\n"):
            above = above and line != "## Sources"
            match = COVERAGE.match(line)
            run_text = above and line.lstrip().startswith("- ") and TOOL_TEXT.search(line)
            if WEB_LINE.match(line) or (match and match[1] in keys) or run_text:
                gone.append(line)
                contact = CONTACT_LINE.match(line) if run_text and record.startswith("people/") else None
                if contact:
                    kept.append(f"- {contact[1]}: Unknown")
                continue
            for key in keys:
                line = re.sub(rf" ?\[{key}\](?!\()", "", line)
            kept.append(line)
        if gone:
            notebook.write(record, "\n".join(kept))
            removed += [{"action": "removed line", "page": record, "line": line} for line in gone]
    return removed
