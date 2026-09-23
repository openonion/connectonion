"""Normalize page shapes and check a candidate before replacing an existing page."""

import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from .files import Notebook, WikiError


def headings(record: str) -> tuple[str, ...]:
    if record.startswith('people/'):
        return ('Contact', *Notebook.PERSON_SECTIONS, 'Sources')
    if record.startswith('projects/'):
        return (*Notebook.PROJECT_SECTIONS, 'Sources')
    if record.startswith('orgs/'):
        return ('Domains', *Notebook.ORG_SECTIONS, 'Sources')
    return ()


def prose(text: str) -> str:
    """Ignore headings and citation-looking text inside fenced examples."""
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            token = match[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append(' ' * len(line))
            continue
        lines.append(line if fence is None else ' ' * len(line))
    return '\n'.join(lines)


def normalize(record: str, text: str) -> str:
    """Add missing canonical sections without dropping or rewriting old content."""
    required = headings(record)
    if not required:
        return text
    matches = list(re.finditer(r'^## (.+)$', prose(text), re.M))
    found = [m[1] for m in matches]
    if len(found) != len(set(found)):
        raise WikiError('Existing page has duplicate sections; reconcile them before investigation')
    if found == list(required):
        return text
    prefix = text[:matches[0].start()] if matches else text
    status = re.findall(r'^Investigation:.*$', text, re.M)
    sections = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match[1]] = re.sub(r'^Investigation:.*$', '', text[match.end():end], flags=re.M).strip()
    prefix = re.sub(r'^Investigation:.*$', '', prefix, flags=re.M).strip()
    order = [*required[:-1], *(h for h in found if h not in required), 'Sources']
    output = [prefix]
    for heading in order:
        output += [f'## {heading}', sections.get(heading, '- Unknown — not investigated yet')]
    return '\n\n'.join(output + status) + '\n'


def _local_reference(value: str, original: str, items: list[dict]) -> bool:
    """Existence in a supplied source directory is identifiable, not proof of reading."""
    roots = [Path(m[1]).expanduser().resolve() for m in re.finditer(r'^- `?(/[^`\n]+?)`?\s*$', original, re.M)]
    roots += [Path(m[1]).resolve() for m in re.finditer(r'^- `(/[^`]+)`', original, re.M)]
    roots += [Path(i['project']).resolve() for i in items if i.get('project')]
    roots += [Path(i['file']).resolve().parent for i in items if i.get('file')]
    supplied_files = {Path(unquote(urlparse(i['reference']).path)).resolve() for i in items
                      if str(i.get('reference', '')).startswith('file:///')}
    supplied_files.update(Path(unquote(urlparse(ref).path) if ref.startswith('file:///') else ref).resolve()
                          for i in items for ref in i.get('references', [])
                          if isinstance(ref, str) and (ref.startswith('/') or ref.startswith('file:///')))
    candidates = re.findall(r'`(/[^`]+)`', value) + re.findall(r'/[^\s`]+', value)
    for candidate in candidates:
        path = Path(candidate).resolve()
        if (path in supplied_files or any(path == root or root in path.parents for root in roots)) and path.exists():
            return True
    return False


def prior_context_reference(value: str, record: str, items: list[dict]) -> bool:
    """A retained page is identifiable context, never independent corroboration."""
    supplied = any(item.get('role') == 'page' and item.get('record') == record for item in items)
    label = re.search(r'\b(existing|prior|derived|mapped)\b', value, re.I)
    return bool(supplied and label and (f'`{record}`' in value or 'investigation:page' in value))


def _project_overview_errors(candidate: str) -> list[str]:
    """Require the template's flow shape, without inventing a flow when unknown."""
    visible = prose(candidate)
    heading = re.search(r'^## Overview[ \t]*$', visible, re.M)
    if not heading:
        return []  # The canonical-section check reports this separately.
    following = re.search(r'^## ', visible[heading.end():], re.M)
    end = heading.end() + following.start() if following else len(candidate)
    section = candidate[heading.end():end].strip()
    if re.fullmatch(r'(?:- )?(?:Unknown|未知|尚未确认)[^\n]*', section):
        return []
    blocks = re.finditer(r'(?m)^[ \t]*(`{3,}|~{3,})(?:text|ascii)?[ \t]*\n'
                         r'([\s\S]*?)\n[ \t]*\1[ \t]*(?:\n|$)', section)
    if any(re.search(r'->|--|\||^[ \t]*v[ \t]*$', block[2], re.M) for block in blocks):
        return []
    return ['Project Overview requires a closed fenced ASCII flow, or an explicit Unknown statement']


def drop_uncited_sources(text: str) -> str:
    """Remove one-line Sources entries that no sentence cites.

    A listed source nobody cites misleads no reader, and refusing the page for
    it threw away a real, fully cited Ian Chan page on 2026-09-23 because the
    old page was listed as [1]. A citation that points at nothing is still
    refused by validate; only the harmless direction is repaired.
    """
    head, marker, tail = text.partition('\n## Sources\n')
    if not marker:
        return text
    sources, rest = tail, ''
    after = re.search(r'^(?:## |Investigation:)', tail, re.M)
    if after:
        sources, rest = tail[:after.start()], tail[after.start():]
    cited = set(re.findall(r'\[(W?\d+)\](?!\()', head + rest))
    kept = [line for line in sources.splitlines(keepends=True)
            if not (m := re.match(r'^\s*(?:- )?\[(W?\d+)\]', line)) or m[1] in cited]
    return head + marker + ''.join(kept) + rest


IDENTITY_LINE = re.compile(r'^(- (?:Email|Handles|Also known as): )(.*)$', re.M)


def drop_owner_addresses(text: str, owner: set[str]) -> tuple[str, list[str]]:
    """Take the account owner's own addresses off someone else's identity lines.

    Mail between the user and a person carries both addresses, and a real page
    (Dora, 2026-09-23) listed the user's own Outlook as her email and handle.
    Which addresses are the owner's is known, so this is removed mechanically
    rather than asked of the model; the rest of the page is kept.
    """
    removed = []

    def clean(match):
        head, value = match.groups()
        body, cites = re.match(r'^(.*?)((?:\s*\[W?\d+\])*)\s*$', value).groups()
        parts = [part.strip() for part in re.split(r'[;,]', body) if part.strip()]
        kept = [part for part in parts if part.casefold() not in owner]
        removed.extend(part for part in parts if part.casefold() in owner)
        if kept == parts:
            return match.group(0)
        return head + ('; '.join(kept) + cites if kept else 'Unknown')

    return IDENTITY_LINE.sub(clean, text), sorted(set(removed))


def validate(record: str, candidate: str, original: str, items: list[dict]) -> list[str]:
    """Structural checks only; citation existence does not prove factual entailment."""
    body = prose(candidate)
    errors = []
    if len(re.findall(r'^# .+', body, re.M)) != 1:
        errors.append('Expected exactly one page title')
    counts = Counter(re.findall(r'^## (.+)$', body, re.M))
    errors += [f'Section must occur once: {h}' for h in headings(record) if counts[h] != 1]
    errors += [f'Duplicate section: {h}' for h, n in counts.items() if n > 1]
    if re.findall(r'^Investigation:.*$', body, re.M) != re.findall(r'^Investigation:.*$', original, re.M):
        errors.append('Investigation status belongs to the runner')
    content, _, sources = body.partition('\n## Sources\n')
    refs = set(re.findall(r'\[(W?\d+)\](?!\()', content))
    definitions = re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?(.*)$', sources, re.M)
    defined = Counter(key for key, _ in definitions)
    errors += [f'Missing or duplicate citation: {key}' for key in refs if defined[key] != 1]
    known = {i['source'] for i in items if i.get('source') and i['source'] != 'investigation:page'}
    derived = [source for i in items if i.get("role") in ("reflection-summary", "extract")
               for source in i.get("sources", [])]
    known.update(derived)
    # A coding session is one transcript file; citing the session rather than
    # one line of it is coarse but traceable. Dora's page cited
    # `claude-code:<session>` for an account digested from that session.
    known.update(source.rsplit(":", 1)[0] for source in derived
                 if source.startswith(("codex:", "claude-code:")) and source.count(":") >= 2)
    if record.startswith('projects/'):
        errors += _project_overview_errors(candidate)
        for label in ('Sessions', 'First seen', 'Last seen'):
            pattern = r'^- ' + re.escape(label) + r': [0-9-]+$'
            previous = re.findall(pattern, prose(original), re.M)
            if previous and re.findall(pattern, body, re.M) != previous:
                errors.append(f'Preserve mapped project metadata: {label}')
    old_sources = original.partition('\n## Sources\n')[2]
    for key, value in definitions:
        files = {path for path in re.findall(r'`(/[^`]+)`', value) if Path(path).is_file()}
        if len(files) > 1:
            errors.append(f'Citation bundles multiple files: {key}')
        if key not in refs:
            errors.append(f'Unused citation: {key}')
        if not (any(source in value for source in known) or value.strip() in old_sources
                or re.search(r'https?://\S+', value) or _local_reference(value, original, items)
                or prior_context_reference(value, record, items)):
            errors.append(f'Citation has no identifiable source: {key}')
    if candidate != original and not refs:
        errors.append('Changed page has no numbered evidence references')
    if record.startswith('people/'):
        for label in Notebook.PERSON_CONTACT:
            if not re.search(r'^- ' + re.escape(label) + ':', content, re.M):
                errors.append(f'Missing contact field: {label}')
    return errors
