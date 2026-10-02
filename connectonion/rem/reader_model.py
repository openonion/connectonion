"""Small, source-aware view models for the disposable REM reader.

Markdown is still the notebook. These projections make the records navigable
without rewriting a person's notes just to change the interface.
"""

from __future__ import annotations

import posixpath
import hashlib
import re
import sqlite3
from pathlib import Path

from .files import state_path
from .store_messages import archived_message

REFERENCE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
CITATION = re.compile(r"\[(W?\d{1,3})\]")
SOURCE = re.compile(r"^\s*[-*]\s*\[(W?\d{1,3})\]\s+([a-z][\w-]*:[^\s—–]+)", re.I | re.M)
ARCHIVED = re.compile(r"^## Sources\b", re.I | re.M)
PRIVATE = re.compile(r"\[(?:sensitive|personal)\]", re.I)


def _not_sources(text: str) -> str:
    """Source descriptions are not evidence of a relationship in the page."""
    match = ARCHIVED.search(text)
    return text[:match.start()] if match else text


def _destination(origin: str, raw: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(origin), raw))


def relationships(records: list[dict]) -> dict[str, list[dict]]:
    """Exact, unambiguous mentions with their basis; reverse links stay explicit."""
    paths = {row["path"]: row for row in records}
    names: dict[str, list[str]] = {}
    for row in records:
        if row["category"] in {"people", "orgs", "projects"}:
            title = row["title"].replace(" (automated candidate)", "").strip()
            if len(title) >= 4:
                names.setdefault(title.casefold(), []).append(row["path"])
                # Short references are useful only when they identify one record.
                # A first name or organisation stem is a navigational hint, not a
                # claim about the nature of the relationship.
                words = title.split()
                if (row["category"] in {"people", "orgs"} and len(words) >= 2
                        and words[0][0].isupper() and words[1][0].isupper()):
                    stem = words[0]
                    if len(stem) >= 4:
                        names.setdefault(stem.casefold(), []).append(row["path"])
    unique = {name: rows[0] for name, rows in names.items() if len(set(rows)) == 1}
    found: dict[str, dict[str, dict]] = {path: {} for path in paths}

    for origin, row in paths.items():
        body = _not_sources(row["text"])
        lower = body.casefold()
        explicit = {_destination(origin, raw) for _, raw in REFERENCE.findall(body)}
        for name, target in sorted(unique.items(), key=lambda pair: -len(pair[0])):
            if target == origin or target in found[origin] or name not in lower:
                continue
            match = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", body, re.I)
            if not match:
                continue
            start, end = body.rfind("\n", 0, match.start()) + 1, body.find("\n", match.end())
            line = body[start:end if end >= 0 else len(body)].strip()
            cites = CITATION.findall(line)
            linked = target in explicit
            basis = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
            basis = CITATION.sub("", basis).lstrip("- ").strip()[:220]
            relation = {"path": target, "kind": "linked" if linked else "cited mention" if cites else "mentioned",
                        "basis": basis, "sources": cites[:4], "via": origin}
            found[origin][target] = relation
            found[target].setdefault(origin, {"path": origin, "kind": "mentioned by", "basis": basis,
                                              "sources": cites[:4], "via": origin})
    rank = {"linked": 0, "mentioned by": 1, "cited mention": 2, "mentioned": 3}
    return {path: sorted(rows.values(), key=lambda rel: (rank.get(rel["kind"], 4), rel["path"]))
            for path, rows in found.items()}


def _source_ids(records: list[dict]) -> set[str]:
    return {source for row in records for _, source in SOURCE.findall(row["text"])}


def _cited_row(db, source: str):
    row = db.execute("select * from messages where id = ?", (source,)).fetchone()
    if row is not None:
        return row
    match = re.fullmatch(r"(gmail|outlook):([0-9a-f]{12})", source)
    if not match:
        return None
    provider, digest = match.groups()
    rows = db.execute("select * from messages where source = ? and (body_path like ? or body_path like ?)",
                      (provider, f"mail/messages/{provider}/{digest}%.json",
                       f"mail/observed/{provider}/{digest}%.json")).fetchall()
    if len(rows) == 1 and hashlib.sha256(rows[0]["id"].removeprefix(provider + ":").encode()).hexdigest().startswith(digest):
        return rows[0]
    return None


def input_scope(saved: dict, message: dict) -> str:
    return saved.get("input_scope") or (
        "Your input only. Assistant replies and tool results are not included, so this does not verify what was completed."
        if message.get("body_line") else "")


def cited_context(root: Path, records: list[dict], *, budget: int = 1_500_000) -> dict[str, dict]:
    """Only archived, cited excerpts enter the owner-only local snapshot."""
    ids = _source_ids(records)
    file = state_path(root, "rem.db")
    if not ids or file.is_symlink():
        return {}
    output: dict[str, dict] = {}
    db = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True) if file.is_file() else None
    if db is not None:
        db.row_factory = sqlite3.Row
    try:
        for source in sorted(ids):
            if budget <= 0:
                break
            row = _cited_row(db, source) if db is not None else None
            if row is None:
                from .skill_runs import instruction_context, skill_record_context
                from .project_pages import repository_context
                context = instruction_context(root, source) or skill_record_context(root, source) or repository_context(root, source)
                if context:
                    output[source] = {**context, 'excerpt': context['excerpt'][:budget],
                                      'truncated': context['truncated'] or len(context['excerpt']) > budget}
                    budget -= len(output[source]['excerpt'])
                continue
            message = dict(row)
            saved = archived_message(root, message) or {}
            raw = saved.get("text" if message.get("body_line") else "body")
            if not isinstance(raw, str) or PRIVATE.search(raw):
                continue
            mail = message.get("source") in ("gmail", "outlook") and not message.get("body_line")
            if mail and "--- Email Body ---" in raw:
                raw = raw.partition("--- Email Body ---")[2]
            excerpt = raw.strip()[: min(640, budget)]
            if not excerpt:
                continue
            output[source] = {"excerpt": excerpt, "truncated": len(raw.strip()) > len(excerpt),
                              "time": message.get("time") or "", "sender": message.get("sender") or "",
                              "thread": message.get("thread") or "", "source": message.get("source") or "",
                              "input_scope": input_scope(saved, message)}
            if mail:
                output[source].update({"participants": {key: saved.get(key) or ([] if key in ("to", "cc") else "")
                                                        for key in ("from", "to", "cc")},
                    "captured_at": saved.get("fetched_at") or "", "retained_at": saved.get("retained_at") or "",
                    "body_format": saved.get("body_format") or ""})
            budget -= len(excerpt)
    finally:
        if db is not None:
            db.close()
    return output


def cited_conversations(root: Path, contexts: dict[str, dict], *, max_threads: int = 40,
                        budget: int = 300_000) -> dict[str, dict]:
    """A bounded local conversation view around cited archived messages.

    Each thread is selected by a cited message. Its latest twelve archived
    messages are shown, with a total count so the reader never implies that a
    clipped view is complete. Bodies never leave the owner-only HTML snapshot.
    """
    threads = {row.get("thread") for row in contexts.values() if row.get("thread")}
    file = state_path(root, "rem.db")
    if not threads or not file.is_file() or file.is_symlink():
        return {}
    db = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    output: dict[str, dict] = {}
    try:
        ranked = []
        for thread in threads:
            last = db.execute("select max(time) from messages where thread = ?", (thread,)).fetchone()[0]
            ranked.append((last or "", thread))
        for _, thread in sorted(ranked, reverse=True)[:max_threads]:
            if budget <= 0:
                break
            total = db.execute("select count(*) from messages where thread = ?", (thread,)).fetchone()[0]
            rows = db.execute("select * from messages where thread = ? order by time desc, id desc limit 12",
                              (thread,)).fetchall()
            messages = []
            for row in reversed(rows):
                message = dict(row)
                saved = archived_message(root, message) or {}
                raw = saved.get("text" if message.get("body_line") else "body")
                if not isinstance(raw, str) or PRIVATE.search(raw):
                    continue
                excerpt = raw.strip()[:min(900, budget)]
                if not excerpt:
                    continue
                messages.append({"id": message["id"], "sender": message.get("sender") or "",
                                 "time": message.get("time") or "", "excerpt": excerpt,
                                 "truncated": len(raw.strip()) > len(excerpt),
                                 "input_scope": input_scope(saved, message)})
                budget -= len(excerpt)
            if messages:
                output[thread] = {"subject": rows[0]["subject"] or "Conversation",
                                  "total": total, "messages": messages}
    finally:
        db.close()
    return output
