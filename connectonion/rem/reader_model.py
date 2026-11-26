"""Small, source-aware view models for the disposable REM reader.

Markdown is still the notebook. These projections make the records navigable
without rewriting a person's notes just to change the interface.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import sqlite3
from pathlib import Path

from .files import ALIAS_LABELS, split_handles, state_path
from .source import SESSION_SOURCE_PATTERN
from .store_messages import archived_message, has_message_index

REFERENCE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
CITATION = re.compile(r"\[(W?\d{1,3})\]")
SOURCE = re.compile(r"^[ \t]*[-*][ \t]*\[(W?\d{1,3})\][ \t]+([a-z][\w-]*:[^\n]+?)(?=[ \t]+[—–][ \t]+|[ \t]*$)", re.I | re.M)
ARCHIVED = re.compile(r"^## Sources\b", re.I | re.M)
PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)
SENSITIVE = re.compile(r"[\[［]sensitive[\]］]", re.I)
WIKILINK = re.compile(r"\[\[((?:orgs|people|devices|projects)/[^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def notebook_links(origin: str, text: str) -> list[str]:
    """Markdown links are page-relative; [[orgs/name]] is notebook-relative."""
    targets = [_destination(origin, raw) for _, raw in REFERENCE.findall(text)]
    targets += [raw if raw.endswith('.md') else raw + '.md' for raw in WIKILINK.findall(text)]
    return list(dict.fromkeys(targets))


def organisation_links(record: str, text: str) -> list[str]:
    from .facts import parse
    label = 'Company' if record.startswith('people/') else 'Organisation'
    # A labelled Company line is the person's private business: it does not place them in the org.
    return list(dict.fromkeys(path for fact in parse(text, record).get(label, []) if not PRIVATE.search(fact['value'])
                             for path in notebook_links(record, fact['value']) if path.startswith('orgs/')))


def organisation_fields(record: dict, paths: set[str]) -> dict:
    """Facts retain citation labels; the convenience fields never infer from a domain."""
    from .facts import ORG_KINDS, parse
    category, path, text = record['category'], record['path'], record['text']
    if category not in ('people', 'orgs', 'projects'):
        return {}
    facts = parse(text, path)
    value = lambda label: '; '.join(row['value'] for row in facts.get(label, []))
    result = {'facts': facts}
    if category == 'orgs':
        kind = value('Kind')
        # A label on the title (or Kind: personal) makes the organisation private; a labelled
        # passage in its body hides that passage only, as on a person's page. Reading the whole
        # body put a busy organisation's people, threads and graph behind one curtain.
        result.update(kind=kind if kind in ORG_KINDS else '', to_you=value('To you'),
                      private=bool(PRIVATE.search(text.split('\n', 1)[0])) or kind == 'personal')
    else:
        result['organisations'] = [org for org in organisation_links(path, text) if org in paths]
        if category == 'people':
            result['team'] = value('Unit')  # compatibility alias, never a second concept
    return result


def _org_roster(org: dict) -> set[str]:
    """The org's own contact roster establishes affiliation, not employment."""
    contacts = [fact['value'] for fact in org['facts']['Your contacts']]
    roster = re.search(r'^## People here\s*\n(.*?)(?=^## |\Z)', org['text'], re.M | re.S)
    # A labelled line stays behind its curtain: its person is not drawn into the org's structure.
    lines = [line for line in [*contacts, *(roster[1] if roster else '').splitlines()] if not PRIVATE.search(line)]
    return set(notebook_links(org['path'], '\n'.join(lines)))


def _parent_chain(org: dict, orgs: dict) -> set[str]:
    """The org and its cited Parent chain: a course's roster may place a person whose Company is its university."""
    chain, path = set(), org['path']
    while path in orgs and path not in chain:
        chain.add(path)
        parents = [link for value in orgs[path]['facts'].get('Parent', []) if value['citations']
                   for link in notebook_links(path, value['value']) if link.startswith('orgs/')]
        path = parents[0] if len(parents) == 1 else ''
    return chain


# Public mail hosts say nothing about where someone works.
FREE_MAIL = frozenset({"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
                       "icloud.com", "me.com", "mac.com", "yahoo.com", "qq.com", "163.com", "126.com",
                       "foxmail.com", "proton.me", "protonmail.com", "aol.com"})


def _mail_domains(row: dict) -> set[str]:
    """Work domains from the page's own Email fact, never from addresses quoted in its body."""
    values = ' '.join(fact['value'] for fact in row.get('facts', {}).get('Email', []))
    return {domain.lower() for domain in re.findall(r'@([A-Za-z0-9.-]+\.[A-Za-z]{2,})', values)} - FREE_MAIL


def _fold(text: str) -> str:
    return re.sub(r'[\W_]+', '', text).casefold()


def _owner_orgs(owner_row: dict, orgs: dict) -> set[str]:
    """The owner's own organisations. On real notebooks the owner page's Company is usually plain text
    ("Quillmoor Labs (co-founder)"), not a link, and no org says Kind: own_company (#3397 reopened), so an
    org whose title appears in that text counts as well as a linked one."""
    found = set(owner_row.get('organisations', [])) | {path for path, org in orgs.items() if org.get('kind') == 'own_company'}
    company = ' '.join(fact['value'] for fact in owner_row.get('facts', {}).get('Company', [])
                       if not PRIVATE.search(fact['value']))
    plain = _fold(company)
    return found | {path for path, org in orgs.items() if len(_fold(org['title'])) >= 3 and _fold(org['title']) in plain}


def organisation_members(records: list[dict], owner: str) -> None:
    """Only listed people and explicit affiliations populate the org roster.

    A roster is the org page's claim (someone on its threads). A person whose OWN page names a
    different company is not drawn into this org by it (#3397: the owner's co-founder sat inside a
    client's tree because she was on the thread). The owner's own people named there are the org's
    `your_side`: the contacts on the owner's side of the relationship.

    A person whose page names no company but whose own Email is at the owner's work domain is the
    owner's teammate: real teammates' pages rarely carry a Company line (#3397 reopened).
    """
    people = [row for row in records if row['category'] == 'people' and row['path'] != owner
              and not (row.get('service') or row.get('needs_review'))]
    orgs = {row['path']: row for row in records if row['category'] == 'orgs'}
    owner_row = next((row for row in records if row['path'] == owner), {})
    owner_orgs = _owner_orgs(owner_row, orgs) if owner_row else set()
    owner_domains = _mail_domains(owner_row) if owner_row else set()
    for person in people:
        if owner_orgs and owner_domains and not person['organisations'] and _mail_domains(person) & owner_domains:
            person['organisations'] = sorted(owner_orgs)
    own = {person['path']: set(person['organisations']) for person in people}
    for org in orgs.values():
        roster, chain = _org_roster(org), _parent_chain(org, orgs)
        org['your_side'] = []
        for person in people:
            if person['path'] not in roster or org['path'] in person['organisations']:
                continue
            elsewhere = own[person['path']] and not own[person['path']] & chain
            if elsewhere and own[person['path']] & owner_orgs and not chain & owner_orgs:
                org['your_side'].append(person['path'])
            elif not elsewhere:
                person['organisations'].append(org['path'])
    for org in orgs.values():
        linked = [row for row in records if org['path'] in row.get('organisations', [])
                  and not (row.get('service') or row.get('needs_review')) and row['path'] != owner]
        for category in ('people', 'projects'):
            org[category] = [row['path'] for row in linked if row['category'] == category]


def _obligation_people(row: dict, people: list[dict], origins: set[str]) -> list[str]:
    from .census import _thread_counterpart
    named = [person['path'] for person in people
             if _thread_counterpart(({'path': row['record']}, row['text'], {}), person, '', '')]
    # Names are a fallback only when unambiguous; copied page keys remain authoritative.
    return sorted({person['path'] for person in people if person['path'] in origins}
                  | (set(named) if len(named) == 1 else set()))


def organisation_obligations(records: list[dict], queue: list[dict]) -> None:
    """Reuse Today's obligation identity, including all copy keys and owner decisions."""
    from .org_hierarchy import obligation_units
    for row in queue:
        row['units'] = obligation_units(row, records)
        if not row['units'] and not any(re.search(r'(?:^|\s)- Unit:', key.partition('\n')[2]) for key in row['keys']):
            origins = {key.partition('\n')[0] for key in row['keys']}
            units = {unit['path'] for person in records if person['path'] in origins
                     for unit in person.get('units', [])}
            if len(units) == 1:
                row['units'] = sorted(units)
    for org in records:
        if org['category'] != 'orgs':
            continue
        members = set(org['people'])
        people = [person for person in records if person['path'] in members]
        org['obligations'] = []
        for row in queue:
            origins = {key.partition('\n')[0] for key in row['keys']}
            scoped = org['path'] in row['units']
            direct = origins & (members | {org['path']})
            explicit = any(re.search(r'(?:^|\s)- Unit:', key.partition('\n')[2]) for key in row['keys'])
            if not row['closed'] and (scoped or direct and (not org.get('unit_kind') or not row['units'] and not explicit)):
                org['obligations'].append({**row, 'people': _obligation_people(row, people, origins)})


def source_definitions(sources: str) -> list[tuple[str, str]]:
    """Citation labels and descriptions, including legacy numbered Sources lines."""
    listed = re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?(.*)$', sources, re.M)
    numbered = re.split(r'^(?:## |Investigation:)', sources, maxsplit=1, flags=re.M)[0]
    return listed + re.findall(r'^[ \t]*(\d+)\.[ \t]+(\S[^\n]*)$', numbered, re.M)


def _not_sources(text: str) -> str:
    """Source descriptions are not evidence of a relationship in the page."""
    match = ARCHIVED.search(text)
    return text[:match.start()] if match else text


def _destination(origin: str, raw: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(origin), raw))


def _clip(text: str, limit: int = 220) -> str:
    """A card preview ends on a whole word, and says it was shortened."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _relation(origin: str, target: str, line: str, kind: str) -> dict:
    basis = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    # The citation goes with the space before it: "at Fernhill [1]." reads "at Fernhill.", never "at Fernhill ." (rc36).
    basis = _clip(re.sub(r"[ \t]*" + CITATION.pattern, "", basis).lstrip("- ").strip())
    return {"path": target, "kind": kind, "basis": basis, "private": bool(PRIVATE.search(line)), "level": _level(line),
            "sources": list(dict.fromkeys(CITATION.findall(line)))[:4], "via": origin}


def _level(text: str) -> str:
    """The strongest privacy mark on a line: the reader curtains a relation reason by it (#3425). The basis can be
    clipped before its mark, so the level is read from the whole line, not from what the card shows."""
    return "sensitive" if SENSITIVE.search(text) else "personal" if PRIVATE.search(text) else ""


def _forward_relations(origin: str, text: str, paths: dict, names: list[tuple[re.Pattern[str], str, str]]) -> dict:
    body = _not_sources(text)
    found = {}
    # An exact notebook path does not depend on its label or the target's title.
    for line in body.splitlines():
        for target in notebook_links(origin, line):
            if target in paths and target != origin and target not in found:
                found[target] = _relation(origin, target, line.strip(), "linked")
    # Match visible prose once per name, never Markdown URLs. Replacing link
    # markup preserves line boundaries, citation numbers and privacy markers.
    prose = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
    folded = prose.casefold() if names else ""
    for pattern, target, name in names:
        if target == origin or target in found:
            continue
        # A literal check avoids running hundreds of regexes against each
        # written page. Python's IGNORECASE also equates dotted/dotless I, so
        # leave those names to the regex rather than filtering a real match.
        if (name not in folded and "i\u0307" not in name and "\u0131" not in name
                and not (("\u0130" in prose or "\u0131" in prose) and "i" in name)):
            continue
        match = pattern.search(prose)
        if match:
            start = prose.rfind("\n", 0, match.start()) + 1
            end = prose.find("\n", match.end())
            line = prose[start:end if end >= 0 else len(prose)].strip()
            kind = "cited mention" if CITATION.search(line) else "mentioned"
            found[target] = _relation(origin, target, line, kind)
    return found


def _ambiguous_person_names(records: list[dict]) -> set[str]:
    claimed = {}
    for row in records:
        if row['category'] != 'people':
            continue
        names = [row['title'], *re.findall(r'\(([^()]*)\)', row['title'])]
        for line in row['text'].splitlines()[:40]:
            field = line.strip().lstrip('-').strip()
            if field.casefold().startswith(ALIAS_LABELS):
                names += split_handles(re.split('[:：]', field, maxsplit=1)[1])
        for name in names:
            plain = re.sub(r'\s*\([^()]*\)$', '', name).strip().casefold()
            for key in {plain, plain.split()[0] if plain else ''} - {''}:
                claimed.setdefault(key, set()).add(row['path'])
    return {name for name, paths in claimed.items() if len(paths) > 1}


def relationships(records: list[dict]) -> dict[str, list[dict]]:
    """Exact notebook links first; unambiguous mentions remain navigation hints."""
    paths = {row["path"]: row for row in records}
    ambiguous = _ambiguous_person_names(records)
    names: dict[str, list[str]] = {}
    for row in records:
        if row["category"] in {"people", "orgs", "projects"}:
            title = row["title"].replace(" (automated candidate)", "").strip()
            if len(title) >= 4:
                names.setdefault(title.casefold(), []).append(row["path"])
                words = title.split()
                if (row["category"] in {"people", "orgs"} and len(words) >= 2
                        and words[0][0].isupper() and words[1][0].isupper()):
                    stem = words[0]
                    if len(stem) >= 4:
                        names.setdefault(stem.casefold(), []).append(row["path"])
    unique = [(re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I), rows[0], name)
              for name, rows in sorted(names.items(), key=lambda pair: -len(pair[0]))
              if len(set(rows)) == 1 and name not in ambiguous]
    # Mapped stubs have no investigated prose to infer relationships from.
    # Keep their explicit links, but avoid scanning every name in every stub.
    forward = {path: _forward_relations(path, row["text"], paths, unique if row.get("written", True) else [])
               for path, row in paths.items()}
    private_topics = {path: _level(row['text'].split('\n', 1)[0]) for path, row in paths.items()
                      if row['category'] == 'knowledge' and PRIVATE.search(row['text'].split('\n', 1)[0])}
    for origin, rows in forward.items():
        for target, relation in rows.items():
            relation['private'] |= origin in private_topics or target in private_topics
            topic = private_topics.get(origin) or private_topics.get(target) or ""
            if topic == "sensitive" or (topic and not relation.get('level')):
                relation['level'] = topic
    found = {path: dict(rows) for path, rows in forward.items()}
    # Finish every page's own links before adding incoming navigation. Otherwise
    # a reverse hint can replace a later page's explicit link and its provenance.
    for origin, rows in forward.items():
        for target, relation in rows.items():
            kind = "linked from" if relation["kind"] == "linked" else "mentioned by"
            found[target].setdefault(origin, {**relation, "path": origin, "kind": kind})
    rank = {"linked": 0, "linked from": 1, "cited mention": 2, "mentioned": 3, "mentioned by": 4}
    return {path: sorted(rows.values(), key=lambda rel: (rank[rel["kind"]], rel["path"]))
            for path, rows in found.items()}


TOPIC_LINKED = ('people/', 'orgs/', 'devices/', 'projects/', 'decisions/', 'principles/', 'agenda/')


def topic_mentions(row: dict, paths: set[str], owner: str) -> list[dict]:
    """The newest cited sentence per record naming a topic, newest first.

    Sessions and skills are counted, not linked; the owner's own page is not a
    backlink, and a sentence labelled private never leaves its page.
    """
    found = {}
    for e in sorted(row['evidence'], key=lambda e: e['date']):
        path = e['record']
        if path in paths and path != owner and path.startswith(TOPIC_LINKED) and not e.get('private'):
            found[path] = {'path': path, 'sentence': _around(e['sentence'], row.get('aliases', [])), 'date': e['date'], 'source': e['source']}
    return sorted(found.values(), key=lambda m: m['date'], reverse=True)


def _around(text: str, aliases: list[str], limit: int = 220) -> str:
    """A long sentence keeps the words naming the topic, starting on a whole word."""
    lowered = text.casefold()
    at = min((lowered.find(a.casefold()) for a in aliases if a.casefold() in lowered), default=0)
    if len(text) <= limit or at < limit - 60:
        return _clip(text, limit)
    start = text.find(' ', max(0, at - 80)) + 1
    return '…' + _clip(text[start:], limit - 1)


def graph_snapshot(records: list[dict], links: dict | None = None, topics: dict | None = None,
                   vocabulary: dict | None = None) -> dict:
    """Explicit undirected links only; sessions fold into their linked project.

    `topics` maps a topic page to the records whose cited sentences name it
    (`topic_mentions`); those become topic edges too. All other records remain
    in nodes, including isolates. Private nodes have no title; callers exporting
    off-device must remove private records beforehand.
    """
    from collections import Counter
    paths = {r['path']: r for r in records if r['path'] != 'skills/catalog/index.md'
             and r['category'] not in ('logs', 'notes')}
    links = relationships(records) if links is None else links
    folded = {}
    for path, row in paths.items():
        if row['category'] == 'sessions':
            projects = sorted(r['path'] for r in links.get(path, [])
                              if r['kind'] in ('linked', 'linked from') and r['path'].startswith('projects/'))
            if projects:
                folded[path] = projects[0]
    edges = {}
    for origin in paths:
        for rel in links.get(origin, []):
            # A link made only on a labelled line is private: it draws no edge.
            if rel['kind'] not in ('linked', 'linked from') or rel['path'] not in paths or rel.get('private'):
                continue
            a, b = sorted((folded.get(origin, origin), folded.get(rel['path'], rel['path'])))
            if a != b:
                kind = 'topic' if a.startswith('knowledge/') or b.startswith('knowledge/') else 'linked'
                edges[a, b] = {'source': a, 'target': b, 'kind': kind}
    for topic, targets in (topics or {}).items():
        for target in targets:
            if topic in paths and target in paths:
                edges.setdefault(tuple(sorted((topic, target))), {'source': min(topic, target), 'target': max(topic, target), 'kind': 'topic'})
    degree = Counter(node for pair in edges for node in pair)
    nodes = []
    for path, row in paths.items():
        if path in folded:
            continue
        private = bool(row.get('private') or PRIVATE.search(row['text'].split('\n', 1)[0]))
        open_threads = re.search(r'^## Open threads\s*\n(.*?)(?=^## |\Z)', row['text'], re.M | re.S)
        has_owed = bool(open_threads and re.search(r'\b(?:the user|user|you)\s+owes?\b|你欠|用户欠', open_threads[1], re.I))
        nodes.append({'id': path, 'kind': row['category'], 'title': '' if private else row['title'],
                      'degree': degree[path], 'has_owed': has_owed, 'private': private})
    isolated = Counter(n['kind'] for n in nodes if not n['degree'])
    return {'nodes': nodes, 'edges': list(edges.values()), 'folded_sessions': len(folded),
            'unconnected': {'count': sum(isolated.values()), 'by_kind': dict(isolated)},
            'tags': tag_layer(nodes, paths, vocabulary or {})}


def tag_layer(nodes: list[dict], paths: dict, vocabulary: dict) -> dict:
    """The knowledge graph has one kind of point, the page (#3140): a tag adds an edge from each page carrying
    it to the page the tag links to (a person, organisation, project or tag page), never a point of its own.

    Only drawn pages: a folded session or a private record adds no edge, and a tag whose page is not drawn
    adds none."""
    from .tags import page_tags
    drawn = {node['id'] for node in nodes}
    edges = {}
    for node in nodes:
        if node['private']:
            continue
        for slug in page_tags(paths[node['id']]['text']):
            target = vocabulary.get(slug, {}).get('page', '')
            if target in drawn and target != node['id']:
                edges.setdefault(tuple(sorted((node['id'], target))), {'source': node['id'], 'target': target, 'kind': 'tagged', 'tag': slug})
    return {'nodes': [], 'edges': list(edges.values())}


def _source_ids(records: list[dict]) -> set[str]:
    numbered = {source for row in records for _, source in SOURCE.findall(row["text"])}
    sessions = {source for row in records if row.get("category") == "sessions"
                for source in re.findall(rf"^- ({SESSION_SOURCE_PATTERN})$",
                                         row["text"].partition("\n## Sources\n")[2], re.M)}
    return numbered | sessions


def _budget_order(records: list[dict], ids: set[str]) -> list[str]:
    """Resolve structured documents before bulk mail and session excerpts spend the budget."""
    numbered = {source for row in records for _, source in SOURCE.findall(row["text"])}
    return sorted(ids, key=lambda source: (
        not (re.fullmatch(r"(gmail|outlook):[0-9a-f]{12}:.+", source)
             or source.startswith(("project-source:", "https://", "http://", "github:", "file:"))),
        source not in numbered, source.split(":", 1)[0] not in ("gmail", "outlook"), source))


def local_file_context(root: Path, source: str, private: bool) -> dict | None:
    """Owner-only text citations inside the notebook, excluding private credential stores."""
    if not private or not source.startswith("file:"):
        return None
    relative = Path(source[5:])
    if relative.is_absolute() or not relative.parts or any(
            part.startswith(".") or re.search(r"(?:env|keys?|secrets?|credentials?)", part, re.I)
            for part in relative.parts):
        return None
    path = root / relative
    if (path.suffix.lower() not in (".txt", ".md", ".markdown") or not path.is_file()
            or any((root / parent).is_symlink() for parent in (relative, *relative.parents))
            or not path.resolve().is_relative_to(root.resolve())):
        return None
    with path.open(encoding="utf-8", errors="replace") as stream:
        text = stream.read(32_769)
    return {"source": "file", "filename": path.name, "excerpt": text[:32_768], "truncated": len(text) > 32_768}


# A short citation (gmail:<12 hex>) names a message by its id's digest. Each lookup used to fetch every message
# of the provider and hash every id again, 534k sha256 calls for one Today queue on the owner's notebook (#3106).
# One digest index for the connection in use answers them all; connections here are short-lived and read-only,
# and a connection takes no weak reference, so the index is kept for the latest one only (held, so its id is not reused).
_DIGESTS: list = [None, {}]


def _digest_index(db, provider: str) -> dict[str, list]:
    if _DIGESTS[0] is not db:
        _DIGESTS[:] = [db, {}]
    per_db = _DIGESTS[1]
    if provider not in per_db:
        index: dict[str, list] = {}
        for row in db.execute("select * from messages where source = ?", (provider,)):
            index.setdefault(hashlib.sha256(row["id"].removeprefix(provider + ":").encode()).hexdigest()[:12], []).append(row)
        per_db[provider] = index
    return per_db[provider]


def _cited_row(db, source: str):
    row = db.execute("select * from messages where id = ?", (source,)).fetchone()
    if row is not None:
        return row
    match = re.fullmatch(r"(gmail|outlook):([0-9a-f]{12})", source)
    if not match:
        return None
    provider, digest = match.groups()
    # Its archived body, when it has one, is named by the same digest.
    homes = (f"mail/messages/{provider}/{digest}", f"mail/observed/{provider}/{digest}")
    rows = [row for row in _digest_index(db, provider).get(digest, [])
            if row["body_path"] is None or (row["body_path"].startswith(homes) and row["body_path"].endswith(".json"))]
    if len(rows) == 1:
        return rows[0]
    return None


def input_scope(saved: dict, message: dict) -> str:
    return saved.get("input_scope") or (
        "Your input only. Assistant replies and tool results are not included, so this does not verify what was completed."
        if message.get("body_line") else "")


def cited_context(root: Path, records: list[dict], *, budget: int = 1_500_000,
                  private: bool = False) -> dict[str, dict]:
    """Only archived, cited excerpts enter the owner-only local snapshot.

    `private` is for the owner's reader on this machine: labelled
    ([personal]/[sensitive]) excerpts show there, behind the reader's toggle.
    Without it -- the claim audit's model, the O Chat view -- they are left out.
    """
    from .evidence import research_contexts
    research = research_contexts(root, records, private=private)
    ids = _source_ids(records)
    file = state_path(root, "rem.db")
    if not ids or file.is_symlink():
        return {}
    mail_limit = 4_096 if budget >= 500_000 else 32_768
    output: dict[str, dict] = {}
    db = sqlite3.connect(file.absolute().as_uri() + "?mode=ro", uri=True) if has_message_index(file) else None
    if db is not None:
        db.row_factory = sqlite3.Row
    try:
        for source in _budget_order(records, ids):
            if budget <= 0:
                break
            row = _cited_row(db, source) if db is not None else None
            if row is None:
                from .attachments import attachment_context
                from .investigate import github_context
                from .project_material import retained_session_context
                from .project_pages import repository_context
                from .skill_runs import instruction_context, skill_record_context
                context = (local_file_context(root, source, private) or instruction_context(root, source) or skill_record_context(root, source)
                           or repository_context(root, source, private) or retained_session_context(root, source, private)
                           or github_context(root, source) or attachment_context(root, source) or research.get(source))
                if context:
                    output[source] = {**context, 'excerpt': context['excerpt'][:budget],
                                      'truncated': context['truncated'] or len(context['excerpt']) > budget}
                    budget -= len(output[source]['excerpt'])
                continue
            message = dict(row)
            saved = archived_message(root, message) or {}
            raw = saved.get("text" if message.get("body_line") else "body")
            mail = message.get("source") in ("gmail", "outlook") and not message.get("body_line")
            if not isinstance(raw, str) and mail and private:
                # Indexed, never archived (rc34 hunt: 214 of a real notebook's person and org citations). The owner's
                # own reader still says who wrote, when and about what, rather than "REM did not keep a copy".
                output[source] = {"excerpt": "", "truncated": False, "body_empty": True, "header_only": True,
                                  "time": message.get("time") or "", "sender": message.get("sender") or "",
                                  "thread": message.get("thread") or "", "source": message.get("source") or "",
                                  "subject": message.get("subject") or "", "input_scope": "",
                                  "participants": {"from": message.get("sender") or "", "to": [], "cc": []}}
                continue
            if not isinstance(raw, str) or (PRIVATE.search(raw) and not private):
                continue
            if mail and "--- Email Body ---" in raw:
                raw = raw.partition("--- Email Body ---")[2]
            excerpt = raw.strip()[: min(mail_limit if mail else 2_048, budget)]
            if not excerpt and not mail:
                continue
            output[source] = {"excerpt": excerpt, "truncated": len(raw.strip()) > len(excerpt),
                              "time": message.get("time") or "", "sender": message.get("sender") or "",
                              "thread": message.get("thread") or "", "source": message.get("source") or "",
                              "input_scope": input_scope(saved, message)}
            if mail:
                output[source].update({"body_empty": not excerpt, "subject": saved.get("subject") or "",
                    "participants": {key: saved.get(key) or ([] if key in ("to", "cc") else "")
                                                        for key in ("from", "to", "cc")},
                    "captured_at": saved.get("fetched_at") or "", "retained_at": saved.get("retained_at") or "",
                    "body_format": saved.get("body_format") or ""})
            budget -= len(excerpt)
    finally:
        if db is not None:
            db.close()
    return output


def _conversation_message(root: Path, row, budget: int, private: bool) -> dict | None:
    if budget <= 0:
        return None
    message = dict(row)
    saved = archived_message(root, message) or {}
    raw = saved.get("text" if message.get("body_line") else "body")
    if not isinstance(raw, str) or (PRIVATE.search(raw) and not private):
        return None
    excerpt = raw.strip()[:min(900, budget)]
    if not excerpt:
        return None
    sender = message.get("sender") or ""
    if message.get("body_line"):
        sender = "Agent" if saved.get("role") == "assistant" else "You"
    return {"id": message["id"], "sender": sender, "time": message.get("time") or "",
            "excerpt": excerpt, "truncated": len(raw.strip()) > len(excerpt),
            "input_scope": input_scope(saved, message)}


def cited_conversations(root: Path, contexts: dict[str, dict], *, max_threads: int = 40,
                        budget: int = 300_000, private: bool = False) -> dict[str, dict]:
    """Two archived neighbours on each side of each verified citation.

    Windows stay keyed by citation: pages citing different parts of the same
    session must not see each other's excerpts. Labelled text follows the same
    owner-only boundary as cited_context.
    """
    file = state_path(root, "rem.db")
    if not contexts or not has_message_index(file):
        return {}
    db = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    output: dict[str, dict] = {}
    try:
        threads = {}
        for source, context in contexts.items():
            row = _cited_row(db, source)
            if row is not None and row["thread"] and row["thread"] == context.get("thread"):
                threads.setdefault(row["thread"], []).append((source, row))
        ranked = sorted(threads, key=lambda thread: max(row["time"] or "" for _, row in threads[thread]), reverse=True)
        for thread in ranked[:max_threads]:
            if budget <= 0:
                break
            rows = db.execute("select * from messages where thread = ? order by time, id", (thread,)).fetchall()
            positions = {row["id"]: i for i, row in enumerate(rows)}
            messages, windows, anchors = {}, {}, {}
            for source, anchor in threads[thread]:
                message = messages.get(anchor["id"]) or _conversation_message(root, anchor, budget, private)
                if message is None:
                    continue
                if anchor["id"] not in messages:
                    messages[anchor["id"]] = message
                    budget -= len(message["excerpt"])
                at = positions[anchor["id"]]
                window = rows[max(0, at - 2):at + 3]
                for row in window:
                    if row["id"] not in messages:
                        neighbor = _conversation_message(root, row, budget, private)
                        if neighbor:
                            messages[row["id"]] = neighbor
                            budget -= len(neighbor["excerpt"])
                windows[source] = [row["id"] for row in window if row["id"] in messages]
                anchors[source] = anchor["id"]
            if messages:
                output[thread] = {"subject": rows[0]["subject"] or "Conversation", "total": len(rows),
                                  "messages": sorted(messages.values(), key=lambda row: positions[row["id"]]),
                                  "windows": windows, "anchors": anchors, "cited_ids": list(dict.fromkeys(anchors.values()))}
    finally:
        db.close()
    return output


def later_in_threads(root: Path, sources, *, per_thread: int = 4, chars: int = 1_500,
                     budget: int = 40_000) -> list[dict]:
    """The archived mail that came after these messages in their own threads, oldest first.

    A turn that sees only its batch reads an ask as still open after the reply
    that settled it: 10 of 35 bad claims in a real audit were stale this way.
    Labelled ([personal]/[sensitive]) mail is left out; secret shapes are removed.
    """
    from contextlib import closing
    from .files import KEY_SHAPES
    file = state_path(root, "rem.db")
    if not file.is_file() or file.is_symlink():
        return []
    with closing(sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [row for source in sorted(dict.fromkeys(sources)) if (row := _cited_row(db, source)) is not None
                and (row["thread"] or "").startswith("mail:")]
        given, after = {row["id"] for row in rows}, {}
        for row in rows:
            after[row["thread"]] = max(after.get(row["thread"], ""), row["time"] or "")
        later = [row for thread, time in after.items() for row in reversed(db.execute(
            "select * from messages where thread = ? and time > ? order by time desc, id desc limit ?",
            (thread, time, per_thread)).fetchall()) if row["id"] not in given]
    found = []
    for row in sorted(later, key=lambda row: (row["time"] or "", row["id"])):
        saved = archived_message(root, dict(row)) or {}
        raw = saved.get("body")
        if not isinstance(raw, str) or PRIVATE.search(raw):
            continue
        text = KEY_SHAPES.sub("[secret-shaped text removed by co rem]",
                                 raw.partition("--- Email Body ---")[2] or raw).strip()[:min(chars, budget)]
        if not text:
            continue
        provider, _, raw_id = row["id"].partition(":")
        found.append({"role": "thread-tail", "source": f"{provider}:{hashlib.sha256(raw_id.encode()).hexdigest()[:12]}",
                      "speaker": row["sender"] or "", "timestamp": row["time"] or "", "subject": row["subject"] or "",
                      "thread": row["thread"], "text": text})
        budget -= len(text)
        if budget <= 0:
            break
    return found


def reply_drafts(root: Path, *, local=False, records=None, omitted=()) -> list[dict]:
    """Reply bodies and mailboxes belong only in the owner's local reader."""
    if not local:
        return []
    from .drafts import listing
    from .writer_mail import attach_writer_mail
    drafts = listing(root, include_pending=True, **({'records': records} if records is not None else {}))
    attach_writer_mail(root, drafts, records, omitted)
    return drafts


def session_detail(text: str, *, private: bool = False) -> dict:
    """Project only the transcript retained in a session page, never live logs.

    Labelled turns follow cited_context's boundary: only an owner's local
    snapshot may carry them, and the UI still hides them behind its toggle.
    """
    from .sessions import AGENTS, _section
    facts = dict(re.findall(r"^- ([A-Za-z ]+): (.*)$", _section(text, "Facts"), re.M))
    kind = next((key for key, name in AGENTS.items() if name == facts.get("Agent")), "")
    sources = re.findall(rf"^- ({SESSION_SOURCE_PATTERN})$", _section(text, "Sources"), re.M)
    turns = []
    parts = re.split(r"^### ([^\n]+)\n", _section(text, "What you typed"), flags=re.M)
    for index, (stamp, body) in enumerate(zip(parts[1::2], parts[2::2])):
        raw = re.sub(r"^> ?", "", body, flags=re.M).strip()
        # A turn's heading ("### 09:12 [sensitive]") labels the whole turn; it reached a shared reader before.
        level = _level(stamp)
        if not raw or ((PRIVATE.search(raw) or level) and not private):
            continue
        turns.append({"id": f"session-message-{index + 1}", "role": "user", "time": PRIVATE.sub("", stamp).strip(),
                      "level": level, "text": raw, "source": sources[index] if index < len(sources) else ""})
    reply = re.sub(r"^> ?", "", _section(text, "Final reply"), flags=re.M).strip()
    if reply and (private or not PRIVATE.search(reply)):
        turns.append({"id": "session-final", "role": "assistant", "time": facts.get("Ended", ""), "text": reply})
    return {"session_kind": kind, "session_id": facts.get("Session", ""), "session_messages": turns,
            "session_commands": _session_commands(text, private),
            "session_status": facts.get("Status", ""), "session_ended": facts.get("Ended", "")}


def _session_commands(text: str, private: bool) -> list[dict]:
    from .sessions import _section
    command_line = next((line for line in _section(text, "Artifacts").splitlines()
                         if line.startswith("- Commands:") and "; notable: " in line), "")
    return [{"text": command, "private": bool(PRIVATE.search(command_line))}
                for command in re.findall(r"`([^`]+)`", command_line.partition("; notable: ")[2])
                if private or not PRIVATE.search(command_line)]


def organisation_logo(root: Path, record: dict) -> str:
    """Embed a bounded local raster; external paths and symlink escapes stay blank."""
    import base64
    from .facts import _lines, values
    if record['category'] != 'orgs':
        return ''
    logos = values(_lines(record['text']).get('Logo', ''))
    if not logos or PRIVATE.search(logos[0]['value']):
        return ''
    raw = logos[0]['value']
    link = re.fullmatch(r'!?\[[^\]]*\]\(([^)]+)\)', raw)
    path = Path(link[1] if link else raw)
    if path.is_absolute() or '..' in path.parts:
        return ''
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        return ''
    # A missing enrichment image is an expected state, including during an atomic update.
    try:
        if not target.is_file() or target.stat().st_size > 2_000_000:
            return ''
        data = target.read_bytes()
    except OSError:
        return ''
    mime = ('image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else
            'image/jpeg' if data.startswith(b'\xff\xd8\xff') else
            'image/gif' if data.startswith((b'GIF87a', b'GIF89a')) else
            'image/webp' if data[:4] == b'RIFF' and data[8:12] == b'WEBP' else '')
    return f'data:{mime};base64,{base64.b64encode(data).decode()}' if mime else ''
