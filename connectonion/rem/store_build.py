"""Build co rem's SQLite index from the files it indexes (#2067); docs/cli/rem-store.md.

Every row here is derived: the pages, map.json, the source inventory, the mail
snapshots, the session JSONL and the run records stay what is true. A group of
tables is rebuilt only when one of its input files changed size or mtime, and
each group in one transaction, so a reader sees the old rows or the new ones.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .files import CITATION, EMAIL, read_json, state_path

SCHEMA_VERSION = "1"
SCHEMA = """
create table meta (key text primary key, value text);
create table sources (path text primary key, mtime_ns integer, size integer, grp text);
create table people (record text primary key, name text, emails text, phone text, company text, role text,
  location text, timezone text, linkedin text, website text, how_known text, language text,
  first_contact text, last_contact text, mails integer, sent integer, received integer,
  open_threads integer, written integer, listed integer, held integer, service integer,
  classification text, facts text);
create table orgs (record text primary key, name text, domain text, domains text, people integer,
  last_contact text, written integer, listed integer);
create table projects (record text primary key, name text, paths text, sessions integer, first text,
  last text, written integer, listed integer);
create table messages (id text primary key, source text, thread text, sender text, recipients text,
  time text, subject text, body_path text, body_line integer);
create table edges (kind text, person text, other text, count integer, last_contact text, via text,
  primary key (kind, person, other));
create table runs (id text primary key, record text, stage text, outcome text, model text, started_at text,
  finished_at text, seconds real, input_tokens integer, cached_input_tokens integer, output_tokens integer);
create index messages_thread on messages(thread, time);
create index messages_sender on messages(sender);
create index people_company on people(company);
create index people_last on people(last_contact);
create index edges_person on edges(person);
create index edges_other on edges(other);
create index runs_record on runs(record);
"""
GROUPS = ("pages", "mail", "sessions", "runs")


def inputs(root: Path) -> dict:
    """{group: [file]} — what each group of tables is built from."""
    state = root / ".state"
    pages = [path for category in ("people", "orgs", "projects") for path in sorted((root / category).glob("*.md"))]
    return {
        "pages": pages + [state / "map.json"],
        # The snapshot folders' own mtimes move when a body is added.
        "mail": [state / "source-inventory.jsonl", state / "mail/messages/gmail", state / "mail/messages/outlook"],
        "sessions": sorted(state.glob("projects/*/messages.jsonl")),
        "runs": sorted(state.glob("runs/*.json")),
    }


def fingerprints(root: Path, group: str, paths: list) -> dict:
    found = {}
    for path in paths:
        if path.exists() and not path.is_symlink():
            stat = path.stat()
            found[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size, group)
    return found


# ---- pages -------------------------------------------------------------------------------------------

LABEL = re.compile(r"^\s*[-*]\s*([^:\[\]`]{1,40}?)\s*[:：]\s*(.*)$")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
LAST_CONTACT = re.compile(r"Last contact:\s*(\d{4}-\d{2}-\d{2})", re.I)
LINK = re.compile(r"\]\(\.\./((?:people|orgs|projects)/[^)\s]+\.md)\)")
# Column ← the page labels that mean it (casefolded).
COLUMNS = {"phone": ("phone", "电话"), "company": ("company", "公司"), "role": ("role", "title"),
           "location": ("location", "based in"), "timezone": ("time zone", "timezone"),
           "linkedin": ("linkedin",), "website": ("website", "site"),
           "how_known": ("how we know them", "how you know them", "how known", "how the user knows them"),
           "language": ("language",), "first_contact": ("first contact",),
           "last_contact": ("last contact",)}


def _sections(text: str) -> dict:
    found, name = {}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            found.setdefault(name, [])
        elif name:
            found[name].append(line)
    return found


def _value(raw: str) -> str:
    value = CITATION.sub("", raw).strip().strip("`").strip()
    return "" if value.casefold().startswith(("unknown", "(none")) else value


def facts(text: str) -> dict:
    """Every `- Label: value` in Contact, then Facts (#2068) over it; Unknown is absent."""
    sections, found = _sections(text), {}
    for section in ("Contact", "Facts"):
        for line in sections.get(section, []):
            match = LABEL.match(line)
            if match and (value := _value(match.group(2))):
                found[match.group(1).strip()] = value
    return found


def _linkedin(link: str) -> bool:
    """By host, not by substring: `evil.example/?u=linkedin.com` is a website."""
    markdown = re.match(r"\[[^\]]*\]\(([^\s)]+)\)", link)
    url = markdown[1] if markdown else link.split()[0] if link.split() else ""
    return bool(re.match(r"^(?:https?://)?(?:[a-z0-9-]+\.)*linkedin\.com(?::\d+)?(?:[/?#]|$)", url, re.I))


def columns(found: dict) -> dict:
    by_label = {label.casefold(): value for label, value in found.items()}
    row = {column: next((by_label[label] for label in labels if label in by_label), "")
           for column, labels in COLUMNS.items()}
    emails = by_label.get("email", "") + " " + by_label.get("emails", "") + " " + by_label.get("邮箱", "")
    row["emails"] = sorted({address.casefold() for address in EMAIL.findall(emails)})
    # #2068's `Links` holds both, `; `-separated: a LinkedIn URL is linkedin, the rest website.
    links = [part.strip() for part in by_label.get("links", "").split(";") if part.strip()]
    row["linkedin"] = row["linkedin"] or next((l for l in links if _linkedin(l)), "")
    row["website"] = row["website"] or "; ".join(l for l in links if not _linkedin(l))
    for column in ("first_contact", "last_contact"):
        row[column] = (DAY.search(row[column]) or [""])[0] if row[column] else ""
    return row


def open_threads(text: str) -> int:
    lines = [line.strip().lstrip("-*").strip() for line in _sections(text).get("Open threads", [])]
    return sum(1 for line in lines if line and _value(line))


def title(text: str, record: str) -> str:
    return next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), Path(record).stem)


def utc(stamp: str) -> str:
    """One spelling for every time, so they order as text; '' when it cannot be read."""
    try:
        parsed = datetime.fromisoformat((stamp or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def thread_key(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def map_state(root: Path) -> dict:
    return read_json(state_path(root, "map.json"), {})


# ---- pages group --------------------------------------------------------------------------------------

def insert(db, table: str, rows: list) -> None:
    if rows:
        names = list(rows[0])
        db.executemany(f"insert or replace into {table} ({', '.join(names)}) "
                       f"values ({', '.join(':' + name for name in names)})", rows)


def _person(record: str, text: str, entry: dict, row: dict) -> dict:
    found = facts(text)
    known = columns(found)
    addresses = row.get("addresses") or ([row["address"]] if row.get("address") else [])
    page_last = max(LAST_CONTACT.findall(text), default="")
    return {**known, "record": record, "name": title(text, record),
            "emails": dumps(known["emails"] or sorted({a.casefold() for a in addresses})),
            "first_contact": known["first_contact"] or (row.get("first") or "")[:10],
            "last_contact": max(known["last_contact"], page_last, (row.get("last") or "")[:10]),
            "mails": row.get("mails") or 0, "sent": row.get("sent") or 0, "received": row.get("received") or 0,
            "open_threads": open_threads(text), "written": entry["written"], "listed": entry["listed"],
            "held": entry["held"], "service": entry["service"],
            "classification": row.get("classification", ""), "facts": dumps(found)}


def _links(texts: dict, people: dict, projects: dict) -> dict:
    """{(person, project): links} from either page to the other."""
    import collections
    found = collections.Counter()
    for record, text in texts.items():
        for target in LINK.findall(text):
            pair = (record, target) if record in people else (target, record)
            if pair[0] in people and pair[1] in projects:
                found[pair] += 1
    return found


def _org(common: dict, row: dict, people: dict) -> dict:
    members = [people[p] for p in row.get("people", []) if p in people]
    return {**common, "domain": row.get("domain", ""), "domains": dumps(row.get("domains", [])),
            "people": len(members), "last_contact": max((p["last_contact"] for p in members), default="")}


def _project(common: dict, row: dict) -> dict:
    return {**common, "paths": dumps(row.get("paths", [])), "sessions": row.get("sessions") or 0,
            "first": (row.get("first") or "")[:10], "last": (row.get("last") or "")[:10]}


def _edges(rows: dict, orgs: dict, people: dict, links: dict) -> list:
    edges = [{"kind": "org", "person": p, "other": org, "count": people[p]["mails"],
              "last_contact": people[p]["last_contact"], "via": "mail domain"}
             for org, row in rows.items() if org in orgs for p in row.get("people", []) if p in people]
    return edges + [{"kind": "project", "person": p, "other": project, "count": count,
                     "last_contact": "", "via": "page link"} for (p, project), count in sorted(links.items())]


def build_pages(db, root: Path) -> None:
    from .census import listed, pages
    from .files import Notebook
    state, notebook = map_state(root), Notebook(root)
    census = {record: {**entry, "listed": listed(entry)} for record, entry in pages(root).items()
              if entry["category"] in ("people", "orgs", "projects")}
    texts = {record: notebook.read(record) for record in census}
    rows = {category: {row["record"]: row for row in state.get(category, []) if row.get("record")}
            for category in ("people", "orgs", "projects")}
    tables = {"people": {}, "orgs": {}, "projects": {}}
    for record, entry in sorted(census.items(), key=lambda item: item[1]["category"] != "people"):
        category, row, text = entry["category"], rows[entry["category"]].get(record, {}), texts[record]
        common = {"record": record, "name": title(text, record), "written": entry["written"], "listed": entry["listed"]}
        tables[category][record] = (_person(record, text, entry, row) if category == "people" else
                                    _org(common, row, tables["people"]) if category == "orgs" else _project(common, row))
    links = _links(texts, tables["people"], tables["projects"])
    tables["edges"] = _edges(rows["orgs"], tables["orgs"], tables["people"], links)
    for table, found in tables.items():
        db.execute(f"delete from {table}")
        insert(db, table, list(found.values()) if isinstance(found, dict) else found)
