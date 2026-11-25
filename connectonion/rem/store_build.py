"""Build co rem's SQLite index from the files it indexes (#2067, #3453); docs/cli/rem-store.md.

Every row here is derived: the pages, map.json, the source inventory, the mail
snapshots, the session JSONL and the run records stay what is true. A group of
tables is rebuilt only when one of its input files changed size or mtime, and
markdown pages update incrementally per changed file inside one transaction.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .files import CATEGORIES, CITATION, EMAIL, read_json, state_path

SCHEMA_VERSION = "2"
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
create table records (record text primary key, category text, title text, public_title text,
  summary text, public_summary text, privacy text,
  written integer, listed integer, held integer, open_threads integer, updated_at text,
  tags text, facts text, public_facts text);
create virtual table records_fts using fts5(record unindexed, category unindexed, title, summary, public_body);
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
create index records_listed_updated on records(listed, updated_at desc, title, record);
create index records_cat_listed_updated on records(category, listed, updated_at desc, title, record);
create index edges_person on edges(person);
create index edges_other on edges(other);
create index runs_record on runs(record);
"""
GROUPS = ("pages", "mail", "sessions", "runs")
INDEXED_CATEGORIES = tuple(c for c in CATEGORIES if c not in ("notes", "logs"))
PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)
SUBHEADING = re.compile(r"^(#{2,6})\s+")
BULLET_START = re.compile(r"^([ \t]*)(?:[-*]|\d+[.)])\s+")


def redact_text(text: str, privacy: str = "cover") -> str:
    """Server-side privacy filter (#3435, #3453).

    In `public` mode, any `#{2,6} Heading [personal|sensitive]` subtree (including
    nested subheadings), any list item carrying `[personal]`/`[sensitive]` across
    continuation lines, and any marked line is stripped before leaving the server.
    """
    if privacy != "public" or not text:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    skip_level = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        head = SUBHEADING.match(line)
        if head:
            level = len(head.group(1))
            if skip_level and level <= skip_level:
                skip_level = 0
            if skip_level:
                idx += 1
                continue
            if PRIVATE.search(line):
                skip_level = level
                idx += 1
                continue
            kept.append(line)
            idx += 1
            continue
        if skip_level:
            idx += 1
            continue
        if line.startswith("# "):
            kept.append(" ".join(PRIVATE.sub("", line).split()))
            idx += 1
            continue
        bullet = BULLET_START.match(line)
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            item_lines = [line]
            end = idx + 1
            while end < len(lines):
                nxt = lines[end]
                if not nxt.strip() or SUBHEADING.match(nxt) or nxt.startswith("# ") or BULLET_START.match(nxt):
                    break
                nxt_indent = len(nxt.expandtabs(4)) - len(nxt.expandtabs(4).lstrip(" "))
                if nxt_indent <= indent:
                    break
                item_lines.append(nxt)
                end += 1
            if not any(PRIVATE.search(part) for part in item_lines):
                kept.extend(item_lines)
            idx = end
            continue
        if not PRIVATE.search(line):
            kept.append(line)
        idx += 1
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return (cleaned + "\n") if cleaned else ""


def inputs(root: Path) -> dict:
    """{group: [file]} — what each group of tables is built from."""
    state = root / ".state"
    pages = [
        path
        for category in INDEXED_CATEGORIES
        if (root / category).is_dir()
        for path in sorted((root / category).rglob("*.md"))
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    ]
    return {
        "pages": pages + [state / "map.json"],
        # The snapshot folders' own mtimes move when a body is added.
        "mail": [
            state / "source-inventory.jsonl",
            state / "mail/messages/gmail",
            state / "mail/messages/outlook",
            state / "mail/observed/gmail",
            state / "mail/observed/outlook",
            state / "mail/observed-metadata/gmail",
            state / "mail/observed-metadata/outlook",
        ],
        "sessions": sorted(state.glob("projects/*/messages.jsonl")),
        "runs": sorted(state.glob("runs/*.json")),
    }


def fingerprints(root: Path, group: str, paths: list) -> dict:
    found = {}
    for path in paths:
        if path.exists() and not path.is_symlink():
            stat = path.stat()
            found[path.relative_to(root).as_posix()] = (stat.st_mtime_ns, stat.st_size, group)
    return found


# ---- pages -------------------------------------------------------------------------------------------

LABEL = re.compile(r"^\s*[-*]\s*([^:\[\]`]{1,40}?)\s*[:：]\s*(.*)$")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
LAST_CONTACT = re.compile(r"Last contact:\s*(\d{4}-\d{2}-\d{2})", re.I)
LINK = re.compile(r"\]\(\.\./((?:people|orgs|projects)/[^)\s]+\.md)\)")
PERSONAL_ORG_KIND = re.compile(r"(?mi)^\s*[-*]\s*Kind\s*[:：]\s*personal\b")
# Column ← the page labels that mean it (casefolded).
COLUMNS = {
    "phone": ("phone", "电话"),
    "company": ("company", "公司"),
    "role": ("role", "title"),
    "location": ("location", "based in"),
    "timezone": ("time zone", "timezone"),
    "linkedin": ("linkedin",),
    "website": ("website", "site"),
    "how_known": ("how we know them", "how you know them", "how known", "how the user knows them"),
    "language": ("language",),
    "first_contact": ("first contact",),
    "last_contact": ("last contact",),
}


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


def _summary(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "<!--", "Investigation:", "Masked:", "- ", "* ")):
            continue
        return CITATION.sub("", stripped)[:280]
    return ""


def _privacy_kind(record: str, text: str) -> str:
    first = text.partition("\n")[0]
    if PRIVATE.search(first):
        return "private_page"
    if record.startswith("orgs/") and PERSONAL_ORG_KIND.search(text):
        return "private_page"
    if record.startswith("projects/"):
        from .project_pages import private as is_private_project
        if is_private_project(record, text):
            return "private_page"
    if PRIVATE.search(text):
        return "marked"
    return "public"


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
        db.executemany(
            f"insert or replace into {table} ({', '.join(names)}) "
            f"values ({', '.join(':' + name for name in names)})",
            rows,
        )


def _person(record: str, text: str, entry: dict, row: dict) -> dict:
    found = facts(text)
    known = columns(found)
    addresses = row.get("addresses") or ([row["address"]] if row.get("address") else [])
    page_last = max(LAST_CONTACT.findall(text), default="")
    return {
        **known,
        "record": record,
        "name": title(text, record),
        "emails": dumps(known["emails"] or sorted({a.casefold() for a in addresses})),
        "first_contact": known["first_contact"],
        "last_contact": max(known["last_contact"], page_last, (row.get("last") or "")[:10]),
        "mails": row.get("mails") or 0,
        "sent": row.get("sent") or 0,
        "received": row.get("received") or 0,
        "open_threads": open_threads(text),
        "written": entry["written"],
        "listed": entry["listed"],
        "held": entry["held"],
        "service": entry["service"],
        "classification": row.get("classification", ""),
        "facts": dumps(found),
    }


def _record_row(root: Path, record: str, text: str, entry: dict | None, held_set: set[str]) -> tuple[dict, str]:
    from .census import written as is_written
    from .tags import page_tags

    category = record.split("/", 1)[0]
    privacy = _privacy_kind(record, text)
    public_text = "" if privacy == "private_page" else redact_text(text, "public")
    if entry is not None:
        w, listed_flag, held_flag = int(bool(entry["written"])), int(bool(entry["listed"])), int(bool(entry["held"]))
    else:
        held_flag = int(record in held_set)
        unlisted_skill = category == "skills" and (not record.startswith("skills/catalog/") or record == "skills/catalog/index.md")
        w = 1 if category == "sessions" else int(is_written(text))
        listed_flag = int(not held_flag and not unlisted_skill)
    try:
        mtime = datetime.fromtimestamp((root / record).stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        mtime = ""
    raw_title = title(text, record)
    pub_title = "" if privacy == "private_page" else " ".join(PRIVATE.sub("", raw_title).split())
    pub_summary = "" if privacy == "private_page" else _summary(public_text)
    row = {
        "record": record,
        "category": category,
        "title": raw_title,
        "public_title": pub_title,
        "summary": _summary(text),
        "public_summary": pub_summary,
        "privacy": privacy,
        "written": w,
        "listed": listed_flag,
        "held": held_flag,
        "open_threads": open_threads(text),
        "updated_at": mtime,
        "tags": dumps(page_tags(text)),
        "facts": dumps(facts(text)),
        "public_facts": dumps({} if privacy == "private_page" else facts(public_text)),
    }
    return row, public_text


def _links(texts: dict, people: dict, projects: dict) -> dict:
    """{(person, project): links} from either page to the other."""
    found = collections.Counter()
    for record, text in texts.items():
        for target in LINK.findall(text):
            pair = (record, target) if record in people else (target, record)
            if pair[0] in people and pair[1] in projects:
                found[pair] += 1
    return found


def _org(common: dict, row: dict, people: dict) -> dict:
    members = [people[p] for p in row.get("people", []) if p in people]
    return {
        **common,
        "domain": row.get("domain", ""),
        "domains": dumps(row.get("domains", [])),
        "people": len(members),
        "last_contact": max((p["last_contact"] for p in members), default=""),
    }


def _project(common: dict, row: dict) -> dict:
    return {
        **common,
        "paths": dumps(row.get("paths", [])),
        "sessions": row.get("sessions") or 0,
        "first": (row.get("first") or "")[:10],
        "last": (row.get("last") or "")[:10],
    }


def _edges(rows: dict, orgs: dict, people: dict, links: dict) -> list:
    edges = [
        {
            "kind": "org",
            "person": p,
            "other": org,
            "count": people[p]["mails"],
            "last_contact": people[p]["last_contact"],
            "via": "mail domain",
        }
        for org, row in rows.items()
        if org in orgs
        for p in row.get("people", [])
        if p in people
    ]
    return edges + [
        {"kind": "project", "person": p, "other": project, "count": count, "last_contact": "", "via": "page link"}
        for (p, project), count in sorted(links.items())
    ]


def _sync_fts_for_records(db, public_bodies: dict[str, str]) -> None:
    if not public_bodies:
        return
    placeholders = ", ".join("?" for _ in public_bodies)
    keys = list(public_bodies)
    rows = db.execute(
        f"select rowid, record, category, public_title, public_summary from records where record in ({placeholders})",
        keys,
    ).fetchall()
    db.executemany(
        "insert into records_fts (rowid, record, category, title, summary, public_body) values (?, ?, ?, ?, ?, ?)",
        [(rowid, rec, cat, pub_title, pub_sum, public_bodies[rec]) for rowid, rec, cat, pub_title, pub_sum in rows],
    )


def build_pages(db, root: Path) -> None:
    from .census import listed, pages
    from .files import Notebook
    from .map import needs_review
    from .tags import held

    with held(root):
        state, notebook, held_set = map_state(root), Notebook(root), needs_review(root)
        all_records = [r for category in INDEXED_CATEGORIES for r in notebook.list(category)]
        texts = {record: notebook.read(record) for record in all_records}
        census_all = {
            record: {**entry, "listed": listed(entry)}
            for record, entry in pages(
                root,
                records=[{"path": r, "category": r.split("/", 1)[0], "text": texts[r]} for r in all_records],
            ).items()
        }
        census = {r: e for r, e in census_all.items() if e["category"] in ("people", "orgs", "projects")}
        rows = {
            category: {row["record"]: row for row in state.get(category, []) if row.get("record")}
            for category in ("people", "orgs", "projects")
        }
        tables: dict[str, dict] = {"people": {}, "orgs": {}, "projects": {}}
        for record, entry in sorted(census.items(), key=lambda item: item[1]["category"] != "people"):
            category, row, text = entry["category"], rows[entry["category"]].get(record, {}), texts[record]
            common = {
                "record": record,
                "name": title(text, record),
                "written": entry["written"],
                "listed": entry["listed"],
            }
            tables[category][record] = (
                _person(record, text, entry, row)
                if category == "people"
                else _org(common, row, tables["people"])
                if category == "orgs"
                else _project(common, row)
            )
        crm_texts = {r: texts[r] for r in census}
        links = _links(crm_texts, tables["people"], tables["projects"])
        edge_rows = _edges(rows["orgs"], tables["orgs"], tables["people"], links)
        for table, found in tables.items():
            db.execute(f"delete from {table}")
            insert(db, table, list(found.values()))
        db.execute("delete from edges")
        insert(db, "edges", edge_rows)

        record_rows = []
        public_bodies: dict[str, str] = {}
        for record in all_records:
            r_row, pub_body = _record_row(root, record, texts[record], census_all.get(record), held_set)
            record_rows.append(r_row)
            public_bodies[record] = pub_body
        db.execute("delete from records")
        db.execute("delete from records_fts")
        insert(db, "records", record_rows)
        _sync_fts_for_records(db, public_bodies)


def sync_pages(db, root: Path, known_group: dict, found_group: dict, *, fresh: bool = False) -> None:
    """Update page tables incrementally when leaf Markdown files were added, edited, or deleted.

    Falls back to `build_pages` when `fresh`, when `.state/map.json` changed, or when `people/`,
    `orgs/`, or `skills/` pages changed (since org rollups, assistant classification, and catalog
    parent dedup join across sibling pages).
    """
    state_keys = {".state/map.json"}
    removed = [p for p in (set(known_group) - set(found_group)) if p not in state_keys]
    changed = [path for path, val in found_group.items() if path not in state_keys and known_group.get(path) != val]
    state_changed = any(known_group.get(k) != found_group.get(k) for k in state_keys)
    joined_prefixes = ("people/", "orgs/", "skills/")
    needs_crm_join = any(p.startswith(joined_prefixes) for p in changed) or any(p.startswith((*joined_prefixes, "projects/")) for p in removed)
    if fresh or state_changed or needs_crm_join or (not changed and not removed):
        build_pages(db, root)
        return

    from .census import written as is_written
    from .files import Notebook, RemError
    from .map import needs_review

    notebook, state, held_set = Notebook(root), map_state(root), needs_review(root)
    project_rows = {row["record"]: row for row in state.get("projects", []) if row.get("record")}
    existing_people = {r[0] for r in db.execute("select record from people")}
    for gone in removed:
        db.execute("delete from records_fts where rowid in (select rowid from records where record = ?)", (gone,))
        db.execute("delete from records where record = ?", (gone,))

    record_rows, proj_upserts = [], []
    public_bodies: dict[str, str] = {}
    for record in changed:
        try:
            text = notebook.read(record)
        except RemError:
            continue
        category = record.split("/", 1)[0]
        entry = None
        if category == "projects":
            w = is_written(text)
            h = record in held_set
            entry = {"written": w, "listed": not h, "held": h}
            common = {"record": record, "name": title(text, record), "written": w, "listed": not h}
            proj_upserts.append(_project(common, project_rows.get(record, {})))
            db.execute("delete from edges where kind = 'project' and other = ?", (record,))
            edge_counts = collections.Counter(
                target for target in LINK.findall(text) if target in existing_people
            )
            if edge_counts:
                insert(
                    db,
                    "edges",
                    [
                        {"kind": "project", "person": p, "other": record, "count": count, "last_contact": "", "via": "page link"}
                        for p, count in sorted(edge_counts.items())
                    ],
                )
        db.execute("delete from records_fts where rowid in (select rowid from records where record = ?)", (record,))
        r_row, pub_body = _record_row(root, record, text, entry, held_set)
        record_rows.append(r_row)
        public_bodies[record] = pub_body

    insert(db, "projects", proj_upserts)
    insert(db, "records", record_rows)
    _sync_fts_for_records(db, public_bodies)
