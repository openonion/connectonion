"""`co rem investigate person "Jalaj Jain"`: a kind, then a name, to one page; never a guess (#3140).

The owner, 2026-11-19: a bare name is ambiguous. So a command names the kind
first (a fixed list), then the page by its title or an alias, compared without
case or spaces. More than one match is refused with every candidate's full name;
an unknown kind is refused with the list. A plural kind (people, tags) means
every due page of that kind; topic and topics are the same words as tag and tags.
The old path form (people/x.md) still resolves.
"""

from pathlib import Path

from . import tags
from .files import Notebook, RemError

# singular kind → the category it names.
# A tag's page lives in knowledge/: knowledge entries merge into tag pages, and the reader, the graph and
# page review already treat knowledge/ as pages, so no move is needed. "topic" is the same word as "tag".
KINDS = {"person": "people", "org": "orgs", "project": "projects", "tag": "knowledge",
         "skill": "skills", "decision": "decisions", "principle": "principles"}
PLURALS = {"people": "person", "orgs": "org", "projects": "project", "tags": "tag", "skills": "skill",
           "decisions": "decision", "principles": "principle"}
ALIASES = {"topic": "tag", "topics": "tags"}


def canonical(word: str) -> str:
    """topic and topics are the same words as tag and tags (#3140)."""
    return ALIASES.get(word, word)


def kinds_line() -> str:
    return (", ".join(KINDS) + " (one page); " + ", ".join(PLURALS) + " (every due page of that kind); "
            "topic and topics mean tag and tags")


def unknown_kind(word: str) -> RemError:
    return RemError(f"{word!r} is not a kind. Name the kind, then the page: co rem investigate person \"Jalaj Jain\". "
                    f"Kinds: {kinds_line()}")


def _key(text: str) -> str:
    return "".join(text.casefold().split())


def _names(text: str, record: str) -> set[str]:
    from .tag_nodes import _names_of, _title
    return {_key(_title(text, record))} | {_key(name.replace("-", " ")) for name in _names_of(text, record)} | {
        _key(name) for name in _names_of(text, record)}


def _title(root: Path, record: str) -> str:
    from .tag_nodes import _title as title
    return title(Notebook(root).read(record), record)


def resolve(root: Path, kind: str, name: str) -> str:
    """The one page of `kind` whose title or alias is `name` (case and spaces ignored), or RemError."""
    kind = canonical(kind)
    if kind not in KINDS:
        raise unknown_kind(kind)
    if not name.strip():
        raise RemError(f"Name the {kind}: co rem investigate {kind} \"NAME\"")
    if kind == "tag":
        return _tag(root, name)
    book, wanted = Notebook(root), _key(name)
    found = [record for record in book.list(KINDS[kind]) if wanted in _names(book.read(record), record)]
    if len(found) > 1:
        listed = "; ".join(f"{_title(root, record)} ({record})" for record in found)
        raise RemError(f"{len(found)} {PLURAL_OF[kind]} are named {name!r}: {listed}. Use a fuller name or one of these paths")
    if not found:
        raise RemError(f"No {kind} is named {name!r}. Find it with: co rem search {name!r}")
    return found[0]


PLURAL_OF = {singular: plural for plural, singular in PLURALS.items()}


def _tag(root: Path, name: str) -> str:
    from . import tag_nodes
    vocabulary, wanted = tags.vocabulary(root), _key(name)
    matches = [slug for slug, entry in vocabulary.items()
               if wanted in {_key(n) for n in (slug, slug.replace("-", " "), entry.get("label", ""), *entry.get("aliases", [])) if n}]
    if len(matches) > 1:
        raise RemError(f"{len(matches)} tags are named {name!r}: " + "; ".join(
            f"{vocabulary[slug].get('label') or slug} ({slug})" for slug in matches) + ". Use one of these")
    if not matches:
        raise RemError(f"No tag is named {name!r}. See the tags with: co rem search tag:")
    slug, named = matches[0], tag_nodes.pages_for_tags(root)
    if slug in named:
        page = named[slug]
        kind = next(singular for singular, category in KINDS.items() if page.startswith(category + "/"))
        raise RemError(f"The tag {name!r} links to the {kind} page {page}: co rem investigate {kind} \"{_title(root, page)}\"")
    return tag_nodes.node_record(root, slug)
