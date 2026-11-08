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
from .store_messages import archived_message

REFERENCE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
CITATION = re.compile(r"\[(W?\d{1,3})\]")
SOURCE = re.compile(r"^[ \t]*[-*][ \t]*\[(W?\d{1,3})\][ \t]+([a-z][\w-]*:[^\n]+?)(?=[ \t]+[—–][ \t]+|[ \t]*$)", re.I | re.M)
ARCHIVED = re.compile(r"^## Sources\b", re.I | re.M)
PRIVATE = re.compile(r"[\[［](?:sensitive|personal)[\]］]", re.I)
WIKILINK = re.compile(r"\[\[((?:orgs|people|projects)/[^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def notebook_links(origin: str, text: str) -> list[str]:
    """Markdown links are page-relative; [[orgs/name]] is notebook-relative."""
    targets = [_destination(origin, raw) for _, raw in REFERENCE.findall(text)]
    targets += [raw if raw.endswith('.md') else raw + '.md' for raw in WIKILINK.findall(text)]
    return list(dict.fromkeys(targets))


def organisation_links(record: str, text: str) -> list[str]:
    from .facts import parse
    label = 'Company' if record.startswith('people/') else 'Organisation'
    return list(dict.fromkeys(path for fact in parse(text, record).get(label, [])
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
        result.update(kind=kind if kind in ORG_KINDS else '', to_you=value('To you'),
                      private=bool(PRIVATE.search(_not_sources(text))) or kind == 'personal')
    else:
        result['organisations'] = [org for org in organisation_links(path, text) if org in paths]
        if category == 'people':
            result['team'] = value('Unit')  # compatibility alias, never a second concept
    return result


def _org_roster(org: dict) -> set[str]:
    """The org's own contact roster establishes affiliation, not employment."""
    contacts = [fact['value'] for fact in org['facts']['Your contacts']]
    roster = re.search(r'^## People here\s*\n(.*?)(?=^## |\Z)', org['text'], re.M | re.S)
    return set(notebook_links(org['path'], '\n'.join(contacts) + '\n' + (roster[1] if roster else '')))


def organisation_members(records: list[dict], owner: str) -> None:
    """Only listed people and explicit affiliations populate the org roster."""
    people = [row for row in records if row['category'] == 'people' and row['path'] != owner
              and not (row.get('service') or row.get('needs_review'))]
    for org in records:
        if org['category'] != 'orgs':
            continue
        roster = _org_roster(org)
        for person in people:
            if person['path'] in roster and org['path'] not in person['organisations']:
                person['organisations'].append(org['path'])
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
    basis = _clip(CITATION.sub("", basis).lstrip("- ").strip())
    return {"path": target, "kind": kind, "basis": basis,
            "private": bool(PRIVATE.search(line)), "sources": list(dict.fromkeys(CITATION.findall(line)))[:4], "via": origin}


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
    private_topics = {path for path, row in paths.items() if row['category'] == 'knowledge'
                      and PRIVATE.search(row['text'].split('\n', 1)[0])}
    for origin, rows in forward.items():
        for target, relation in rows.items():
            relation['private'] |= origin in private_topics or target in private_topics
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


def graph_snapshot(records: list[dict], links: dict | None = None) -> dict:
    """Explicit undirected links only; sessions fold into their linked project.

    All other records remain in nodes, including isolates. Private nodes have no
    title; callers exporting off-device must remove private records beforehand.
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
            if rel['kind'] not in ('linked', 'linked from') or rel['path'] not in paths:
                continue
            a, b = sorted((folded.get(origin, origin), folded.get(rel['path'], rel['path'])))
            if a != b:
                kind = 'topic' if a.startswith('knowledge/') or b.startswith('knowledge/') else 'linked'
                edges[a, b] = {'source': a, 'target': b, 'kind': kind}
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
            'unconnected': {'count': sum(isolated.values()), 'by_kind': dict(isolated)}}


def _source_ids(records: list[dict]) -> set[str]:
    numbered = {source for row in records for _, source in SOURCE.findall(row["text"])}
    sessions = {source for row in records if row.get("category") == "sessions"
                for source in re.findall(rf"^- ({SESSION_SOURCE_PATTERN})$",
                                         row["text"].partition("\n## Sources\n")[2], re.M)}
    return numbered | sessions


def _budget_order(records: list[dict], ids: set[str]) -> list[str]:
    """What a reader clicks first: a claim's numbered sources, mail among them, then the
    typed lines a session page lists. Sorted by id, 8,000 session lines spent the budget
    before the first gmail: or outlook: citation."""
    numbered = {source for row in records for _, source in SOURCE.findall(row["text"])}
    return sorted(ids, key=lambda source: (source not in numbered,
                                           source.split(":", 1)[0] not in ("gmail", "outlook"), source))


def _cited_row(db, source: str):
    row = db.execute("select * from messages where id = ?", (source,)).fetchone()
    if row is not None:
        return row
    match = re.fullmatch(r"(gmail|outlook):([0-9a-f]{12})", source)
    if not match:
        return None
    provider, digest = match.groups()
    rows = db.execute("select * from messages where source = ? and (body_path like ? or body_path like ? or body_path is null)",
                      (provider, f"mail/messages/{provider}/{digest}%.json",
                       f"mail/observed/{provider}/{digest}%.json")).fetchall()
    rows = [row for row in rows if hashlib.sha256(row['id'].removeprefix(provider + ':').encode()).hexdigest().startswith(digest)]
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
    output: dict[str, dict] = {}
    db = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True) if file.is_file() else None
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
                context = (instruction_context(root, source) or skill_record_context(root, source)
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
            if not isinstance(raw, str) or (PRIVATE.search(raw) and not private):
                continue
            mail = message.get("source") in ("gmail", "outlook") and not message.get("body_line")
            if mail and "--- Email Body ---" in raw:
                raw = raw.partition("--- Email Body ---")[2]
            excerpt = raw.strip()[: min(16_384 if mail else 2_048, budget)]
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
    if not contexts or not file.is_file() or file.is_symlink():
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
    from .files import SECRET_SHAPES
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
        text = SECRET_SHAPES.sub("[secret-shaped text removed by co rem]",
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


def reply_drafts(root: Path, *, local=False, records=None) -> list[dict]:
    """Reply bodies and mailboxes belong only in the owner's local reader."""
    if not local:
        return []
    from .drafts import listing
    return listing(root, include_pending=True, **({'records': records} if records is not None else {}))


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
        if not raw or (PRIVATE.search(raw) and not private):
            continue
        turns.append({"id": f"session-message-{index + 1}", "role": "user", "time": stamp,
                      "text": raw, "source": sources[index] if index < len(sources) else ""})
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
