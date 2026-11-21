"""A person's organisations are pages, linked both ways (#3141).

Owner, 2026-11-19, after investigating a person whose own consultancy had no page: "为什么上面没有建 One 这个
组织？为什么没有把 One 双向链接到一块？" The model writes the organisation as a link to its page
(`[One](../orgs/one.md)`) in `Company` and in each career line of `Who they are`; the program checks that
it did (a repairable error, only for lines this run wrote) and, once the page is saved, creates the
organisation pages that do not exist yet and adds the person to each organisation's `People here`.
A created page is a stub "not investigated yet", which the night's investigation picks up like any other.
"""

import re

ORG_LINK = re.compile(r'\[([^\]\n]+)\]\((?:\.\./)?(orgs/[a-z0-9][a-z0-9-]*\.md)\)')
# A career line: a list line under `Who they are` that starts with a year or a span of years.
CAREER = re.compile(r'^- (?:(?:c\.\s*|since\s+|until\s+)?(?:19|20)\d{2})', re.I)
PLACEHOLDER = "- Unknown — not investigated yet"


def _section(text: str, heading: str) -> str:
    found = re.search(rf'(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)', text)
    return found[1] if found else ""


def _company(text: str) -> str:
    found = re.search(r'^- Company:\s*(.*)$', _section(text, "Facts"), re.M)
    return found[1].strip() if found else ""


def _career(text: str) -> list[str]:
    return [line.strip() for line in _section(text, "Who they are").splitlines() if CAREER.match(line.strip())]


def org_errors(record: str, candidate: str, original: str) -> list[str]:
    """A Company value or a career line this run wrote that names its organisation without the page's link."""
    if not record.startswith("people/"):
        return []
    errors = []
    company = _company(candidate)
    if company and company != _company(original) and not re.match(r'Unknown\b', company) and not ORG_LINK.search(company):
        errors.append(f"Company names an organisation without its page: {company[:120]} -- write it as "
                      "[Name](../orgs/<slug>.md) [n]; the program creates the page when it does not exist")
    carried = set(_career(original))
    errors += [f"Career line names no organisation page: {line[:160]} -- link the organisation as "
               "[Name](../orgs/<slug>.md); the program creates the page when it does not exist"
               for line in _career(candidate) if line not in carried and not ORG_LINK.search(line)]
    return errors


def _links(text: str) -> dict[str, str]:
    """{orgs/<slug>.md: name} for the organisations a person page links in Company and its career lines."""
    found = {}
    for line in [_company(text), *_career(text)]:
        for name, record in ORG_LINK.findall(line):
            found.setdefault(record, name.strip())
    return found


SUFFIX = re.compile(r'\b(pty|ltd|limited|inc|llc|gmbh|co|corp|corporation|company|group|the)\b')


def _key(name: str) -> str:
    """An organisation's name compared loosely: case, punctuation and legal suffixes aside."""
    return " ".join(SUFFIX.sub(" ", re.sub(r'[^\w\s]', ' ', name.lower())).split())


def _existing(notebook) -> dict[str, str]:
    """{loose name: orgs/<page>.md} for the organisation pages the notebook has."""
    found = {}
    folder = notebook.root / "orgs"
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        title = re.search(r'^# (.+)$', path.read_text(encoding="utf-8"), re.M)
        if title:
            found.setdefault(_key(title[1]), f"orgs/{path.name}")
    return found


def link_orgs(notebook, record: str, text: str) -> list[dict]:
    """Create the linked organisation pages that do not exist and put the person in each one's People here.

    A link to a new slug for an organisation the notebook already has (the same name, loosely) is pointed
    at that page instead: on a notebook copy, 2 of 4 new pages duplicated one (2026-11-19)."""
    if not record.startswith("people/"):
        return []
    title = re.search(r'^# (.+)$', text, re.M)
    person = f"[{title[1].strip() if title else record}](../{record})"
    existing, links = _existing(notebook), _links(text)
    for org, name in list(links.items()):
        same = existing.get(_key(name))
        if not notebook.exists(org) and same and same != org:
            text = text.replace(f"](../{org})", f"](../{same})").replace(f"]({org})", f"]({same})")
            links.setdefault(same, links.pop(org))
    if links != _links(notebook.read(record)) and notebook.exists(record):
        notebook.write(record, text)
    done = []
    for org, name in links.items():
        created = notebook.stub_org(org, name, people=[record])
        page = notebook.read(org)
        if created:
            page = page.replace(f"[{record.rsplit('/', 1)[-1][:-3]}](../{record})", person)
        elif f"](../{record})" not in _section(page, "People here"):
            body = _section(page, "People here")
            kept = "\n".join(line for line in body.rstrip("\n").splitlines() if line.strip() != PLACEHOLDER)
            page = page.replace("## People here\n" + body, "## People here\n" + (kept + "\n" if kept else "") + f"- {person}\n\n", 1)
        notebook.write(org, page)
        done.append({"record": org, "title": name, "created": created})
    return done


def new_org_links(before: str, after: str) -> list[dict]:
    """The organisations a run linked that the page did not link before: 'What changed' names them."""
    old = _links(before)
    return [{"title": name, "record": org} for org, name in _links(after).items() if org not in old]
