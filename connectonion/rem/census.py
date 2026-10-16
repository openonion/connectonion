"""What is in the notebook, counted once for every screen (#2008).

The reader said "174 with findings" when three pages had been written -- a
mapped skill page shows its description, a mapped project page its paths, and
the page's own JavaScript took both for findings. People were 76 on one screen
and 82 on another, skills 159 and 152, because each screen chose for itself
which pages to leave out. `co rem status` and the reader now both ask here:

- counted: people, projects, organisations and skill catalog pages; not the
  pages held for review, not services still on a people page, not the skills
  index, and one page per skill title;
- written: the page's status line no longer says "not investigated yet" (a
  merge keeps the investigated page's status, so a merged page is written
  exactly when what it kept was);
- last activity: the page's own dates (last contact, last session, last
  investigation), never the file's mtime, which is when the last map rewrote it.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from posixpath import normpath

from .files import Notebook, read_json, state_path

CATEGORIES = ("people", "projects", "orgs", "skills", "sessions")
DAY = r"(\d{4}-\d{2}-\d{2})"
# Dates that say when something happened, as each kind of page writes them.
ACTIVITY = re.compile(
    rf"\bLast contact:\s*{DAY}"                       # an investigated person's lead
    rf"|\blast:\s*{DAY}"                              # a mapped person's History
    rf"|^- Last seen:\s*{DAY}"                        # a project's last session
    rf"|\blast on\s*{DAY}", re.I | re.M)               # a skill's last invocation
# When the notebook last worked on the page: the date to show only when the page names no activity.
WORKED = re.compile(rf"^Investigation:.*?\b(?:investigated|written|updated)\s+{DAY}", re.M)
PROJECT_ACTIVITY = re.compile(rf"^- Last activity:\s*{DAY}", re.I | re.M)


def written(page: str) -> bool:
    """Someone or a model wrote it: not map output alone."""
    from .merge import mapped_only
    return not mapped_only(page)


def last_activity(page: str) -> str:
    """The latest date the page itself gives for activity, else its last investigation, or ''."""
    explicit = PROJECT_ACTIVITY.findall(page)
    if explicit:
        return max(explicit)
    days = [day for match in ACTIVITY.finditer(page) for day in match.groups() if day]
    return max(days, default="") or max(WORKED.findall(page), default="")


def _counted(record: str) -> bool:
    category = record.split("/")[0]
    if category == "skills":
        return record.startswith("skills/catalog/") and record != "skills/catalog/index.md"
    return category in CATEGORIES


def pages(root: Path) -> dict:
    """{record: {category, written, last, held, service, duplicate}} for every counted page."""
    from .map import needs_review, service_page
    notebook = Notebook(root)
    state = read_json(state_path(root, "map.json"), {})
    # Rows with an address: the owner's row names only the record.
    rows = {row.get("record"): row for row in state.get("people", []) if row.get("record") and row.get("address")}
    automated = {row["address"].casefold() for row in state.get("automated_correspondents", [])
                 if row.get("address")}
    owner = (state.get("owner") or {}).get("record")
    people = {person["path"]: person for person in notebook.people()}
    held, titles, found = needs_review(root), set(), {}
    for record in notebook.list():
        if not _counted(record):
            continue
        text = notebook.read(record)
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), record)
        category = record.split("/")[0]
        person = people.get(record)
        duplicate = category == "skills" and title.casefold() in titles
        if category == "skills":
            titles.add(title.casefold())
        session_day = re.search(rf"^- Date:\s*{DAY}$", text, re.M) if category == "sessions" else None
        found[record] = {
            "category": category, "written": category == "sessions" or written(text),
            "last": (session_day[1] if session_day else "") if category == "sessions" else last_activity(text),
            "held": record in held, "duplicate": duplicate,
            "service": bool(person) and record != owner and not written(text)
            and service_page(title, person["emails"], rows.get(record), automated)}
    return found


def listed(entry: dict) -> bool:
    return not (entry["held"] or entry["service"] or entry["duplicate"])


def counts(root: Path, found: dict | None = None) -> dict:
    """Pages per category: mapped (every listed page) and written."""
    found = pages(root) if found is None else found
    result = {category: {"mapped": 0, "written": 0} for category in CATEGORIES}
    for entry in found.values():
        if listed(entry):
            result[entry["category"]]["mapped"] += 1
            result[entry["category"]]["written"] += entry["written"]
    return result


# Open threads, read the way the reader reads them (reader.html owing(),
# isCalm() and threads()), so `co rem status` says the number the reader's
# home shows as "waiting on you". The earliest phrase that says who must act
# decides a thread's direction; a page names the owner as "the user", "you"
# or by first name.
CALM = re.compile(r"^(?:nothing (?:open|owed|outstanding|pending)|none(?:\s+(?:identified|open|outstanding|known|as of))?"
                  r"\b(?![-\w])|no (?:explicit |known |confirmed |current )?(?:open|outstanding|pending)\b"
                  r"|no work is (?:confirmed )?pending\b)", re.I)
NOT_A_THREAD = re.compile(r"^(?:unknown\b|no (?:confirmed|known) pending work\b)", re.I)
# What known() drops from a section before anything reads it: unknown answers and mapping's placeholders.
UNKNOWN_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:[^:\n]{1,40}:\s*)?(?:unknown|not known)(?:\s*(?:[—(:.;-]|\[\d+\]).*)?\s*$", re.I)
EXPLAINED = re.compile(r"^\s*(?:[-*]\s*)?Unknown\s*[—:.()]\s*\S", re.I)
UNFILLED_LINE = re.compile(r"^Unknown\s*—\s*(?:not investigated yet|not verified)[.;]?\s*(?:\[W?\d+\]\s*)*$", re.I)
PLACEHOLDER = re.compile(r"identity unverified|classification unassessed|^\s*[-*]\s*\(none yet\)\s*$", re.I)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
THREAD_KINDS = ("people", "orgs", "projects")


def _directions(first_name: str) -> tuple:
    me = "(?:the user|user|you" + (f"|{re.escape(first_name)}" if first_name else "") + ")"
    chasing = (rf"\b{me}\s+(?:asked|asks|requested|requests|reminded|chased|is awaiting|awaits|awaited|"
               rf"is waiting (?:on|for)|was waiting (?:on|for))\s+(?!{me}\b)")
    mine = re.compile(
        rf"\b{me}(?:['’]s)?\s+(?:has |have |had |still )?(?:owes?|owed|promised|offered to|agreed|needs? to|must|"
        rf"should|said (?:he|she|they) would|to (?:send|reply|sign|confirm|pay|review|decide)|has not|have not|"
        rf"hasn't|haven't)\b|^\s*{me}\s*:|\b(?:asks?|asked|requests?|requested|wants|invited)\s+{me}\s+to\b|"
        rf"\b(?:requested|asked for|awaits?|awaiting|waiting (?:on|for))\s+(?:{me}(?:['’]s)?|your)\b|"
        rf"\brequested (?:confirmation|approval|a reply|an answer)\b|\byou owe\b", re.I)
    theirs = re.compile(
        chasing + r"|\b(?:owes?|owed) (?:the user|you)\b|\bwaiting (?:on|for) (?:them|him|her|their)\b|\bunanswered\b"
        r"|\b(?:he|she|they) (?:has|have) not (?:replied|answered|sent|confirmed)\b|\bno reply\b"
        r"|\b[A-Z][\w-]+(?:['’]s)? (?:promised|is expected to|agreed to|owes|said (?:he|she|they) would)\b|\bpromised\b")
    return mine, theirs


def direction(text: str, first_name: str = "") -> str:
    """Who must act: the owner, their counterpart, a third party, or unspecified."""
    # Keep structured prefixes in step with reader.html direction() (UI audit #4).
    me = r"(?:the user|user|you" + (f"|{re.escape(first_name)}" if first_name else "") + ")"
    prefix = re.sub(r"^\s*(?:[-*+]\s+)?", "", text).replace("**", "")
    owner = re.match(rf"^{me}\s+(owes?|asked)\b", prefix, re.I)
    if owner:
        return "theirs" if owner[1].lower() == "asked" else "mine"
    debt = re.match(r"^([^:;!?]+?)\s+owes?\s+(.+)", prefix, re.I)
    if debt and re.match(r"^[A-Z]", debt[1]) and 1 <= len(debt[1].split()) <= 6 \
            and not re.search(r",|\b(?:said|would|that|what)\b", debt[1], re.I):
        return "theirs" if re.match(rf"^{me}\b", debt[2], re.I) else "third"
    mine, theirs = (pattern.search(text) for pattern in _directions(first_name))
    if not (mine or theirs):
        return "plain"
    if mine and theirs:
        return "mine" if mine.start() <= theirs.start() else "theirs"
    return "mine" if mine else "theirs"


def _kept(line: str) -> bool:
    explained = EXPLAINED.match(line) and not UNFILLED_LINE.match(re.sub(r"^\s*[-*]\s*", "", line))
    return (not UNKNOWN_LINE.match(line) or bool(explained)) and not PLACEHOLDER.search(line)


def threads(page: str) -> list[str]:
    """A page's open threads, one item per list entry, without calm lines."""
    section = re.split(r"^## ", page.partition("\n## Open threads\n")[2], flags=re.M)[0]
    lines = [line for line in re.sub(r"<!--.*?-->", "", section, flags=re.S).splitlines()
             if not line.startswith("Investigation:") and _kept(line)]
    items = []
    for line in lines:
        if LIST_ITEM.match(line) and not re.match(r"^\s{2,}", line):
            items.append(LIST_ITEM.sub("", line, count=1))
        elif line.strip() and items:
            items[-1] += " " + line.strip()
        elif line.strip():
            items.append(line.strip())
    return [item for item in items if not CALM.match(item.replace("*", "").strip())
            and not NOT_A_THREAD.match(item)]


def _thread_dates(text: str, today: date) -> tuple[str, str]:
    # Dates and the 60-day boundary mirror reader.html threads().
    days = re.findall(DAY, text)
    due = re.search(rf"\b(?:due(?:\s+(?:on|is))?|deadline(?:\s+is)?|by)\s*:?\s*{DAY}", text, re.I)
    due = due[1] if due else ""
    since = re.search(rf"\b(?:since|requested(?:\s+on)?|asked(?:\s+on)?)\s*:?\s*{DAY}", text, re.I)
    moved = re.search(rf"\blast moved(?:\s+on)?\s*:?\s*{DAY}", text, re.I)
    since = moved[1] if moved else since[1] if since else next((day for day in days if day != due and day <= today.isoformat()), "")
    return since, due


def _quiet(text: str, today: date) -> bool:
    since, due = _thread_dates(text, today)
    return bool(since and (today - date.fromisoformat(since)).days > 60
                and (not due or due <= today.isoformat()))


# Source numbers belong to their page; copied promises share the resolved id.
QUOTED_WORDS = re.compile(r'“([^”\n]{6,})”|"([^"\n]{6,})"')
CITATION = re.compile(r"\[(W?\d+)\]")


def _obligation_words(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def _obligation_evidence(item: tuple) -> tuple:
    _, text, sources = item
    ids = {sources[n] for n in CITATION.findall(text) if n in sources}
    quotes = [_obligation_words(a or b) for a, b in QUOTED_WORDS.findall(text)]
    words = _obligation_words(CITATION.sub("", QUOTED_WORDS.sub("", text)))
    return ids, [q for q in quotes if q], words


def _same_obligation(a: tuple, b: tuple) -> bool:
    return bool(a[0] & b[0]) and (a[2] == b[2] or
                                 any(x in y or y in x for x in a[1] for y in b[1]))


def _thread_groups(items: list) -> list:
    """Connected obligations, preserving the reader's existing sort order."""
    groups, evidence = [], [_obligation_evidence(item) for item in items]
    for i in range(len(items)):
        matches = [group for group in groups if any(_same_obligation(evidence[i], evidence[j]) for j in group)]
        if not matches:
            groups.append([i])
            continue
        matches[0].extend([i] + [j for group in matches[1:] for j in group])
        for group in matches[1:]:
            groups.remove(group)
    return [[items[i] for i in sorted(group)] for group in groups]


def _thread_counterpart(item: tuple, person: dict, owner: str, first: str) -> bool:
    if person["path"] == owner:
        return False
    record, text, _ = item
    me = "(?:the user|user|you" + (f"|{re.escape(first)}" if first else "") + ")"
    text = text.replace("**", "")
    named = re.match(rf"^{me}\s+(?:owes?|asked)\s+(.+)", text, re.I) or re.match(
        rf"^(.+?)\s+owes?\s+{me}\b", text, re.I)
    named = named[1] if named else ""
    link = re.match(r"\s*\[[^\]]+\]\(([^)]+\.md)\)", named)
    if link and normpath(str(Path(record["path"]).parent / link[1])) == person["path"]:
        return True
    words = _obligation_words(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", named))
    title = _obligation_words(person["title"])
    return bool(title) and (words == title or words.startswith(title + " "))


def _thread_sources(page: str) -> dict:
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    section = re.search(r"^## Sources[^\n]*\n([\s\S]*?)(?=^## |^Investigation:|\Z)", page, re.I | re.M)
    return dict(re.findall(r"^\s*- \[(W?\d+)\]\s+(\S+)", section[1], re.M)) if section else {}


def _thread_items(notebook: Notebook, found: dict, first: str) -> list:
    items = []
    for path, entry in found.items():
        if not listed(entry) or entry["category"] not in THREAD_KINDS:
            continue
        page = notebook.read(path)
        title = next((line[2:].strip() for line in page.splitlines() if line.startswith("# ")), path)
        record = {"path": path, "title": title}
        sources = _thread_sources(page)
        items.extend((record, item, sources) for item in threads(page) if direction(item, first) != "third")
    return items


def open_threads(root: Path, found: dict | None = None, *, as_of: date | None = None) -> dict:
    """Active directions and quiet threads on listed people, orgs and projects."""
    found = pages(root) if found is None else found
    notebook = Notebook(root)
    owner = (read_json(state_path(root, "map.json"), {}).get("owner") or {}).get("record")
    title = next((line[2:] for line in notebook.read(owner).splitlines() if line.startswith("# ")), "") \
        if owner and notebook.path(owner).is_file() else ""
    first = (title.split() or [""])[0]
    items = _thread_items(notebook, found, first)
    from .config import read_config
    from .service import notebook_zone
    today = as_of or datetime.now(notebook_zone(read_config(root))).date()
    # Keep the census identical to reader.html threadCounts(), including quiet context.
    items.sort(key=lambda item: _thread_dates(item[1], today)[0], reverse=True)
    items.sort(key=lambda item: _thread_dates(item[1], today)[1] or "9999")
    result = dict.fromkeys(("mine", "theirs", "other", "quiet", "open"), 0)
    for group in _thread_groups(items):
        representative = next((item for item in group if any(
            _thread_counterpart(other, item[0], owner, first) for other in group)), group[0])
        item = representative[1]
        who = direction(item, first)
        if _quiet(item, today):
            result["quiet"] += 1
        else:
            result["other" if who == "plain" else who] += 1
            result["open"] += 1
    return result
