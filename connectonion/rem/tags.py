"""Tags: the `- Tags:` line on a page, the one vocabulary, and how a query finds a tag (#3093).

The page is the source of truth: the last line of its `## Facts` section,
`- Tags: 9900 [3], student [3], harbour-university [1]`, the format session pages
already carry. `.state/tags.json` holds only what a page cannot: each slug's
label, kind and aliases. Counts are read off the pages every time, so they never
disagree with them. docs/cli/rem-tags.md is the contract.
"""

import re
import threading
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from .files import read_json, state_path, write_json

TAG_KINDS = ("course", "team", "organisation", "project", "role", "topic", "place")
# Kinds that name something: their evidence must contain the name.
NAMED_KINDS = ("course", "team", "organisation", "project", "place")
CATCH_ALL = {"misc", "general", "other", "workflow", "platform", "tools", "automation", "people", "contact", "work"}
# Every page kind carries tags (#3093; owner, 2026-11-19: «所有的内容里面应该都有 tag 吧»). The first three keep the
# line at the end of `## Facts`; the rest have no Facts and keep it directly under the title.
FACT_KINDS = ("people", "orgs", "projects")
TAGGED_KINDS = FACT_KINDS + ("skills", "decisions", "knowledge", "principles")
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
    """The page with its Tags line set to `rows` (none: no line): at the end of `## Facts`, or directly under the
    title on a page with no Facts (decisions, knowledge, principles, skills)."""
    under_title = re.search(r"\A# [^\n]*\n\n- Tags:[^\n]*\n\n", text)
    text = text[:under_title.start()] + text[under_title.start():under_title.end()].rsplit("\n- Tags:", 1)[0] + "\n" + text[under_title.end():] \
        if under_title else re.sub(r"(?m)^- Tags:[^\n]*\n?", "", text)
    if not rows:
        return text
    facts = re.search(r"(?m)^## Facts[ \t]*\n", text)
    if not facts:
        title = re.match(r"# [^\n]*\n", text)
        if not title:
            raise ValueError("A page needs a title or a ## Facts section to hold its Tags line")
        rest = text[title.end():].lstrip("\n")
        return text[:title.end()] + "\n" + format_line(rows) + "\n\n" + rest
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


def organisations(root) -> dict:
    """Every organisation page is a tag, {slug: {label, kind, aliases}}.

    The notebook keeps courses and teams as organisation pages too (`- Kind: course`,
    `- Kind: team`, titled `9900` and `9900-F13F-CAKE`, file names with a hash): those are
    course and team tags named by their title. Any other is an organisation named by its
    file name. The file name is always an alias, so a link to the page finds its tag."""
    from pathlib import PurePosixPath
    from .files import Notebook
    book, found = Notebook(root), {}
    for record in book.list("orgs"):
        text, stem = book.read(record), normalise(PurePosixPath(record).stem)
        title = text.partition("\n")[0].lstrip("# ").strip()
        kind = re.search(r"(?m)^- Kind:[ \t]*(\w+)", text)
        unit = kind[1] if kind and kind[1] in ("course", "team") else ""
        slug = normalise(title) if unit and normalise(title) else stem
        found[slug] = {"label": title or stem, "kind": unit or "organisation",
                       "aliases": [stem] if stem != slug else []}
    return found


def org_links(text: str) -> list[str]:
    """The organisation pages a page's Facts link to, as file-name slugs (Markdown or [[wiki]] links)."""
    facts = re.search(r"(?ms)^## Facts[ \t]*\n(.*?)(?=^#{1,2} |\Z)", text)
    found = re.findall(r"(?:\]\(|\[\[)(?:\.\./)?orgs/([^)\]#\s/]+)\.md", facts[1] if facts else "")
    return list(dict.fromkeys(normalise(stem) for stem in found))


def entries(root) -> dict:
    """tags.json, every organisation page, the starter roles, and session tags read as topics
    (sessions are not rewritten)."""
    found = {slug: {"label": entry.get("label") or slug, "kind": entry.get("kind", "topic"),
                    "aliases": list(entry.get("aliases", []))} for slug, entry in _saved(root).items()}
    for slug in ROLES:
        found.setdefault(slug, {"label": slug, "kind": "role", "aliases": []})
    for slug, entry in organisations(root).items():
        kept = [alias for alias in found.get(slug, {}).get("aliases", []) if alias not in entry["aliases"]]
        found[slug] = {**entry, "aliases": entry["aliases"] + kept}
    for slug in read_json(state_path(root, "session-tags.json"), {}):
        slug = normalise(slug)
        if slug and resolve(found, slug) is None:
            found[slug] = {"label": slug, "kind": "topic", "aliases": []}
    return found


def counts(texts) -> Counter:
    return Counter(tag for text in texts for tag in page_tags(text))


# One page build reads the notebook and writes none of it. Tag nodes asked for the whole-notebook tag scans once
# per tag page, each reading every page: with every WeChat friend on a page (~1.8k people, #3347) that doubled the
# build. `held` keeps each scan's answer for one build only, so the long-running Host never serves a stale one.
_LOCAL = threading.local()


def _held_map() -> dict:
    found = getattr(_LOCAL, "held", None)
    if found is None:
        found = _LOCAL.held = {}
    return found


def held_store(root) -> dict | None:
    return _held_map().get(str(Path(root).resolve()))


def __getattr__(name: str):
    if name == "_HELD":
        return _held_map()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@contextmanager
def held(root):
    mapping = _held_map()
    key = str(Path(root).resolve())
    outer = key in mapping
    mapping.setdefault(key, {})
    try:
        yield
    finally:
        if not outer:
            mapping.pop(key, None)


def once(root, name: str, compute):
    """`compute()`, or inside `held(root)` the answer this build already has."""
    store = held_store(root)
    if store is None:
        return compute()
    if name not in store:
        store[name] = compute()
    return store[name]


def vocabulary(root, records=None) -> dict:
    """Every tag with its count over the pages: {slug: {label, kind, aliases, count}}."""
    if records is None:
        return once(root, "vocabulary", lambda: _vocabulary(root, None))
    return _vocabulary(root, records)


def _vocabulary(root, records) -> dict:
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
