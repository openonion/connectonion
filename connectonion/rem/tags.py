"""Tags: the `- Tags:` line on a page, the one vocabulary, and how a query finds a tag (#3093).

The page is the source of truth: the last line of its `## Facts` section,
`- Tags: 9900 [3], student [3], harbour-university [1]`, the format session pages
already carry. `.state/tags.json` holds only what a page cannot: each slug's
label, kind and aliases. Counts are read off the pages every time, so they never
disagree with them. docs/cli/rem-tags.md is the contract.
"""

import re
from collections import Counter

from .files import read_json, state_path, write_json

TAG_KINDS = ("course", "team", "organisation", "project", "role", "topic", "place")
# Kinds that name something: their evidence must contain the name.
NAMED_KINDS = ("course", "team", "organisation", "project", "place")
CATCH_ALL = {"misc", "general", "other", "workflow", "platform", "tools", "automation", "people", "contact", "work"}
TAGGED_KINDS = ("people", "orgs", "projects")
# Roles every notebook starts with, so a person's commonest tag needs no new word.
ROLES = ("student", "tutor", "lecturer", "colleague", "client", "investor", "partner", "supplier",
         "candidate", "recruiter", "mentor", "founder", "advisor")
VOCABULARY = "tags.json"
LINE = re.compile(r"(?m)^- Tags:[ \t]*(.*)$")
CITE = re.compile(r"\[(W?\d+)\]")
SLUG = re.compile(r"[^\W_](?:[\w-]{0,38}[^\W_])?")


def normalise(text: str) -> str:
    """`Capstone 9900` -> `capstone-9900`; `tag:COMP9900` -> `comp9900`. The session rule."""
    text = re.sub(r"^tag:", "", str(text).strip().lower())
    return re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", re.sub(r"[^\w\s-]", "", text))).strip("-")


def parse_line(value: str) -> list[dict]:
    """`9900 [3], student` -> [{"tag": "9900", "citation": "3"}, {"tag": "student", "citation": ""}]."""
    rows = []
    for part in value.split(","):
        cites = CITE.findall(part)
        slug = normalise(CITE.sub("", part))
        if slug and slug.casefold() != "unknown" and slug not in [row["tag"] for row in rows]:
            rows.append({"tag": slug, "citation": cites[0] if cites else ""})
    return rows


def page_tags(text: str) -> list[str]:
    """The slugs on a page, in page order; [] when it has no Tags line."""
    match = LINE.search(text)
    return [row["tag"] for row in parse_line(match[1])] if match else []


def format_line(rows: list[dict]) -> str:
    return "- Tags: " + ", ".join(row["tag"] + (f" [{row['citation']}]" if row.get("citation") else "") for row in rows)


def without_tags(text: str) -> str:
    """The page as it would be with no Tags line: what a page is hashed by."""
    return LINE.sub("", text).replace("\n\n\n", "\n\n") if LINE.search(text) else text


def with_tags(text: str, rows: list[dict]) -> str:
    """The page with its Tags line set to `rows` (none: no line), at the end of `## Facts`."""
    text = re.sub(r"(?m)^- Tags:[^\n]*\n?", "", text)
    if not rows:
        return text
    facts = re.search(r"(?m)^## Facts[ \t]*\n", text)
    if not facts:
        raise ValueError("A page needs a ## Facts section to hold its Tags line")
    following = re.search(r"(?m)^#{1,2} ", text[facts.end():])
    end = facts.end() + following.start() if following else len(text)
    body = text[facts.end():end].rstrip("\n")
    return text[:facts.end()] + (body + "\n" if body else "") + format_line(rows) + "\n" + (
        "\n" + text[end:] if following else "")


def only_tags_changed(before: str, after: str) -> bool:
    """True when the two pages differ in their Tags line alone (blank lines around it aside)."""
    def bare(text):
        return re.sub(r"\n{2,}", "\n\n", without_tags(text)).strip()
    return bare(before) == bare(after)


def _saved(root) -> dict:
    return read_json(state_path(root, VOCABULARY), {}).get("tags", {})


def save(root, entries: dict) -> None:
    write_json(state_path(root, VOCABULARY), {"tags": {slug: {key: entry[key] for key in ("label", "kind", "aliases")}
                                                       for slug, entry in sorted(entries.items())}})


def entries(root) -> dict:
    """tags.json, with session tags it lacks read as topics (sessions are not rewritten)."""
    found = {slug: {"label": entry.get("label") or slug, "kind": entry.get("kind", "topic"),
                    "aliases": list(entry.get("aliases", []))} for slug, entry in _saved(root).items()}
    for slug in ROLES:
        found.setdefault(slug, {"label": slug, "kind": "role", "aliases": []})
    for slug in read_json(state_path(root, "session-tags.json"), {}):
        slug = normalise(slug)
        if slug and resolve(found, slug) is None:
            found[slug] = {"label": slug, "kind": "topic", "aliases": []}
    return found


def counts(texts) -> Counter:
    return Counter(tag for text in texts for tag in page_tags(text))


def vocabulary(root, records=None) -> dict:
    """Every tag with its count over the pages: {slug: {label, kind, aliases, count}}."""
    from .files import Notebook
    if records is None:
        book = Notebook(root)
        records = [{"path": path, "text": book.read(path)} for path in book.list()]
    found, counted = entries(root), counts(record["text"] for record in records)
    for slug in counted:
        found.setdefault(slug, {"label": slug, "kind": "topic", "aliases": []})
    return {slug: {**entry, "count": counted[slug]} for slug, entry in found.items()}


def resolve(vocabulary: dict, text: str):
    """The slug `text` names, through slug, label or alias; None when it names none."""
    wanted = normalise(text)
    if not wanted:
        return None
    if wanted in vocabulary:
        return wanted
    for slug, entry in vocabulary.items():
        if wanted == normalise(entry.get("label", "")) or wanted in map(normalise, entry.get("aliases", [])):
            return slug
    return None


def matching(records: list[dict], vocabulary: dict, query: str) -> list[str]:
    """The records `tag:QUERY` finds, in the order given."""
    slug = resolve(vocabulary, query)
    return [record["path"] for record in records if slug and slug in page_tags(record["text"])]


def item_tags(texts: dict, record: str, text: str) -> list[str]:
    """An open item's tags: its record's, then those of each person and organisation page it links to."""
    linked = re.findall(r"\]\((?:\.\./)?((?:people|orgs)/[^)#\s]+\.md)\)", text)
    found = [tag for path in [record, *linked] for tag in page_tags(texts.get(path, ""))]
    return list(dict.fromkeys(found))
