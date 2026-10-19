"""Normalize page shapes and check a candidate before replacing an existing page."""

import difflib
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import facts
from .files import Notebook, RemError


# The owner's own page has no "How the user writes to them" (#2008): it said
# "Not applicable" on a real owner page, a heading for nothing.
NOT_ON_OWNER_PAGE = 'How the user writes to them'
PROJECT_CORE = ('Facts', 'Insight', 'What it is', 'Where it stands', 'Paths',
                'Open threads', 'Uncertainties', 'Sources')
SKILL_CORE = ('What it does', 'Insight', 'When to use', 'Current status', 'How to use',
              'Inputs and outputs', 'Usage history', 'Limitations', 'Uncertainties', 'Source', 'Sources')
SKILL_SECTIONS = ('What it does', 'Insight', 'When to use', 'Current status', 'Example result', 'How to use',
                  'Inputs and outputs', 'Usage history', 'Performance', 'Limitations', 'Maintenance',
                  'Related projects', 'Open threads', 'Uncertainties', 'Source', 'Sources')
SECTION_HEADING_RE = re.compile(r'^## ([^\r\n]+)\r?$', re.M)


def headings(record: str, owner: bool = False) -> tuple[str, ...]:
    if record.startswith('people/'):
        return ('Facts', 'Insight',
                *(h for h in Notebook.PERSON_SECTIONS if not (owner and h == NOT_ON_OWNER_PAGE)), 'Sources')
    if record.startswith('projects/'):
        return PROJECT_CORE
    if record.startswith('orgs/'):
        return ('Domains', 'Facts', *Notebook.ORG_SECTIONS, 'Sources')
    if record.startswith('skills/catalog/'):
        return SKILL_CORE
    return ()


def _canonical_headings(record: str, owner: bool = False) -> tuple[str, ...]:
    if record.startswith('projects/'):
        return ('Facts', 'Insight', *Notebook.PROJECT_SECTIONS, 'Sources')
    if record.startswith('skills/catalog/'):
        return SKILL_SECTIONS
    return headings(record, owner)


def prose(text: str) -> str:
    """Ignore headings and citation-looking text inside fenced examples."""
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            token = match[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append(re.sub(r'[^\r\n]', ' ', line))
            continue
        lines.append(line if fence is None else re.sub(r'[^\r\n]', ' ', line))
    return ''.join(lines)


def normalize(record: str, text: str, owner: bool = False) -> str:
    """Add missing canonical sections without dropping or rewriting old content."""
    required = headings(record, owner)
    if not required:
        return text
    # A page from before #2068: `## Contact` becomes `## Facts`, and the turn is
    # handed an Insight it must fill, not a bare Unknown it may leave.
    text = facts.upgrade(record, text, insight=f'- {PLACEHOLDER}')
    matches = list(SECTION_HEADING_RE.finditer(prose(text)))
    found = [m[1] for m in matches]
    if len(found) != len(set(found)):
        raise RemError('Existing page has duplicate sections; reconcile them before investigation')
    canonical = _canonical_headings(record, owner)
    expected = [h for h in canonical if h in found or h in required]
    expected[-1:-1] = [h for h in found if h not in canonical]
    if found == expected:
        return text
    prefix = text[:matches[0].start()] if matches else text
    status = re.findall(r'^Investigation:.*$', text, re.M)
    sections = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match[1]] = re.sub(r'^Investigation:.*$', '', text[match.end():end], flags=re.M).strip()
    prefix = re.sub(r'^Investigation:.*$', '', prefix, flags=re.M).strip()
    order = expected
    output = [prefix]
    for heading in order:
        output += [f'## {heading}', sections.get(heading, '- Unknown — not investigated yet')]
    return '\n\n'.join(output + status) + '\n'


def compact_page(record: str, text: str) -> str:
    """Hide empty optional headings after a project or skill has been investigated.

    The map keeps its full scaffold until a write. A written page carries only
    supported detail plus the core needed to resume and audit it (#2122).
    """
    # connectonion gained a History outside the project shape (2026-10-15); keep its lines as decisions.
    history = re.search(r'(?ms)^## History[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)', prose(text))
    if record.startswith('projects/') and history:
        body = text[history.start(1):history.end(1)].strip()
        text = text[:history.start()] + text[history.end():]
        decisions = re.search(r'(?ms)^## Key decisions[ \t]*\n.*?(?=^## |^Investigation:|\Z)', prose(text))
        at = decisions.end() if decisions else history.start()
        heading = '' if decisions else '## Key decisions\n'
        text = text[:at].rstrip('\r\n') + '\n\n' + heading + body + '\n\n' + text[at:]
    visible = prose(text)
    matches = list(SECTION_HEADING_RE.finditer(visible))
    if not matches:
        return text
    removable = set(_canonical_headings(record)) - set(headings(record))
    spans = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = re.sub(r'^Investigation:.*$', '', text[match.end():end], flags=re.M).strip()
        if (match[1] in removable and not re.search(r'\[W?\d+\]', content)
                and re.fullmatch(r'(?:- )?(?:Unknown|未知|尚未确认)[^\n]*', content)):
            spans.append((match.start(), end))
    for start, end in reversed(spans):
        text = text[:start].rstrip('\r\n') + '\n\n' + text[end:].lstrip('\r\n')
    return text


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


def prior_context_reference(value: str, record: str, items: list[dict], original: str = "") -> bool:
    """A retained page is identifiable context, never independent corroboration.

    Investigation hands the page over as an item; maintenance edits the page in
    place, so there the page that existed before the run is the supplied
    context. A real maintenance pass cited "Existing person-page contact field"
    for an email the map had put there, and the whole update was refused.
    """
    supplied = any(item.get('role') == 'page' and item.get('record') == record for item in items)
    label = re.search(r'\b(existing|prior|derived|mapped)\b', value, re.I)
    if supplied and label and (f'`{record}`' in value or 'investigation:page' in value):
        return True
    return bool(original.strip() and label and (record in value or re.search(r'\bpage\b', value, re.I)))


def repair_project_overview(record: str, text: str) -> tuple[str, bool]:
    """Keep pages refused for a missing flow without inventing one."""
    if not record.startswith('projects/'):
        return text, False
    visible = prose(text)
    heading = re.search(r'^## Overview[ \t]*$', visible, re.M)
    if not heading:
        return text, False
    following = re.search(r'^## ', visible[heading.end():], re.M)
    end = heading.end() + following.start() if following else len(text)
    section = text[heading.end():end].strip()
    if re.fullmatch(r'(?:- )?(?:Unknown|未知|尚未确认)[^\n]*', section):
        return text, False
    blocks = re.finditer(r'(?m)^[ \t]*(`{3,}|~{3,})(?:text|ascii)?[ \t]*\n'
                         r'([\s\S]*?)\n[ \t]*\1[ \t]*(?:\n|$)', section)
    # ASCII or box-drawing: a real candidate drew its flow with │ and ▼ and the
    # whole page was refused for it.
    if any(re.search(r'->|--|\||^[ \t]*v[ \t]*$|[│┃▼↓→⟶➜─]', block[2], re.M) for block in blocks):
        return text, False
    # An unclosed fence must not swallow the sections after Overview.
    if not following:
        following = re.search(r'^## ', text[heading.end():], re.M)
    end = heading.end() + following.start() if following else len(text)
    return text[:heading.end()] + '\n- Unknown\n\n' + text[end:], True


SOURCE_ID = re.compile(r'\b(?:codex|claude-code|gmail|outlook|whatsapp|email|reflection|review|project-source)'
                       r'(?:-summary)?:[\w.:+-]+')


def _carried_over(value: str, old_sources: str) -> bool:
    ids = [match.rstrip('.,;') for match in SOURCE_ID.findall(value)]
    return bool(ids) and all(source in old_sources for source in ids)


def _restore_citations(line: str, candidate: str, original: str) -> tuple[str, str]:
    """Carry a restored line's source ids into the candidate's numbering."""
    section = r'(?ms)^## Sources\n(.*?)(?=^## |^Investigation:|\Z)'
    entry = r'^([ \t]*- \[(W?\d+)\][ \t]*:?[ \t]*)(\S+)([^\n]*)$'
    before, after = re.search(section, original), re.search(section, candidate)
    old = {number: (prefix, source, suffix) for prefix, number, source, suffix in
           re.findall(entry, before[1] if before else '', re.M)}
    citations = re.findall(r'\[(W?\d+)\](?!\()', line)
    if any(number not in old for number in citations):
        return '', candidate
    rows = re.findall(entry, after[1] if after else '', re.M)
    numbers = {source: number for _, number, source, _ in rows}
    next_number = max((int(number) for _, number, _, _ in rows if number.isdigit()), default=0) + 1
    mapping, added = {}, []
    for number in citations:
        prefix, source, suffix = old[number]
        if source not in numbers:
            numbers[source] = str(next_number)
            prefix = prefix.replace(f'[{number}]', f'[{next_number}]', 1)
            added.append(f'{prefix}{source}{suffix}')
            next_number += 1
        mapping[number] = numbers[source]
    if added:
        if after:
            at = after.start(1) + len(after[1].rstrip('\n'))
            candidate = candidate[:at] + '\n' + '\n'.join(added) + (candidate[at:] or '\n')
        else:
            status = re.search(r'^Investigation:', candidate, re.M)
            at = status.start() if status else len(candidate)
            candidate = candidate[:at].rstrip('\n') + '\n\n## Sources\n' + '\n'.join(added) + '\n\n' + candidate[at:]
    return re.sub(r'\[(W?\d+)\](?!\()', lambda m: f'[{mapping[m[1]]}]', line), candidate


def _subject_handles(record: str, page: str) -> set[str]:
    """Only unqualified structured values establish continuity, never commentary."""
    if record.startswith("people/"):
        from .files import EMAIL
        section = r"(?ms)^## {}\n(.*?)(?=^## |^Investigation:|\Z)"
        facts = re.search(section.format("Facts"), page) or re.search(section.format("Contact"), page)
        line = re.search(r"(?m)^- Email:[ \t]*(.*)$", facts[1]) if facts else None
        value = re.sub(r"\[W?\d+\]", "", line[1]).strip() if line else ""
        parts = [part.strip() for part in re.split(r"[;,]", value)]
        return {part.casefold() for part in parts} if all(EMAIL.fullmatch(part) for part in parts) else set()
    domains = re.search(r"(?ms)^## Domains\n(.*?)(?=^## |^Investigation:|\Z)", page)
    lines = [re.sub(r"\[W?\d+\]", "", line[2:]).strip()
             for line in domains[1].splitlines() if line.startswith("- ")] if domains else []
    return {line.casefold() for line in lines
            if re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", line)}


def subject_scope_changed(record: str, original: str, candidate: str) -> bool:
    """A new title without a retained routing anchor cannot inherit old facts."""
    titles = [re.search(r"^# (.+)$", page, re.M) for page in (original, candidate)]
    renamed = all(titles) and titles[0][1].strip().casefold() != titles[1][1].strip().casefold()
    return bool(renamed and not (_subject_handles(record, original) & _subject_handles(record, candidate)))


def restore_runner_fields(record: str, candidate: str, original: str) -> str:
    """Put back the lines the runner owns, instead of refusing the page for them.

    The Investigation status line and a project's mapped Sessions / First seen /
    Last seen are written by code that knows their true values. A real
    maintenance pass rewrote them and the whole page was refused; the rest of
    the page was sound. Restoring them is exact, so nothing is guessed.
    """
    if not original:
        return candidate
    if record.startswith(('people/', 'orgs/')) and not subject_scope_changed(record, original, candidate):
        # A correction may change who this file describes; keep its Unknowns.
        # 2026-10-16 trial: a later round erased Ying Tan's extracted Last contact.
        section = r'(?ms)^## Facts\n(.*?)(?=^## |\Z)'
        before, after = re.search(section, original), re.search(section, candidate)
        if before and after:
            body = after[1]
            for label in ('First contact', 'Last contact'):
                kept = re.search(r'^- ' + label + r': \d{4}-\d{2}-\d{2}(?:[ \t]*\[W?\d+\])+$', before[1], re.M)
                unknown = r'^- ' + label + r': Unknown$'
                if kept and re.search(unknown, body, re.M):
                    line, candidate = _restore_citations(kept[0], candidate, original)
                    if line:
                        body = re.sub(unknown, lambda _: line, body, count=1, flags=re.M)
            candidate = re.sub(section, lambda _: '## Facts\n' + body, candidate, count=1)
    if record.startswith('skills/catalog/'):
        mapped = re.search(r'(?ms)^## Source\n.*?(?=^## |^Investigation:|\Z)', original)
        if mapped:
            candidate = re.sub(r'(?ms)^## Source\n.*?(?=^## |^Investigation:|\Z)',
                               lambda _: mapped[0], candidate, count=1)
        usage = re.search(r'(?s)<!-- rem-usage -->.*?<!-- /rem-usage -->', original)
        if usage:
            candidate = re.sub(r'(?s)<!-- rem-usage -->.*?<!-- /rem-usage -->\s*', '', candidate)
            candidate = candidate.replace('## Usage history\n', '## Usage history\n' + usage[0] + '\n', 1)
    status = re.search(r'^Investigation:.*$', original, re.M)
    if status:
        candidate = (re.sub(r'^Investigation:.*$', lambda _: status.group(0), candidate, count=1, flags=re.M)
                     if re.search(r'^Investigation:.*$', candidate, re.M)
                     else candidate.rstrip('\n') + '\n\n' + status.group(0) + '\n')
    if record.startswith('projects/'):
        for label in ('Sessions', 'First seen', 'Last seen'):
            kept = re.search(r'^- ' + re.escape(label) + r': [0-9-]+$', original, re.M)
            if kept:
                # A real project candidate kept these values but nested them under
                # a bullet ("  - Sessions: 2"); the top-level check then refused an
                # otherwise sound page. Indentation is layout, not a claim.
                candidate = re.sub(r'^[ \t]*- ' + re.escape(label) + r': .*$', lambda _: kept.group(0), candidate,
                                   count=1, flags=re.M)
    return candidate


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
    # Counted as validate counts them, in prose: a [9] only inside a diagram's
    # code block left its source "unused" and refused a real project page (2026-10-08).
    cited = set(re.findall(r'\[(W?\d+)\](?!\()', prose(head + rest)))
    kept = [line for line in sources.splitlines(keepends=True)
            if not (m := re.match(r'^\s*(?:- )?\[(W?\d+)\]', line)) or m[1] in cited]
    return head + marker + ''.join(kept) + rest


CODE = re.compile(r'```.*?```|`[^`\n]*`', re.S)


def renumber_sources(text: str) -> str:
    """Number the kept Sources 1, 2, 3... and their citations to match.

    Dropping uncited sources left gaps the reader showed as they were: 40 of
    123 pages in a real 1.9.2b3 notebook. Code is not prose, so `rows[5]`
    keeps its index; web sources ([W1]) keep their own numbering.
    """
    sources = text.partition('\n## Sources\n')[2]
    listed = [int(n) for n in re.findall(r'^\s*(?:- )?\[(\d+)\]', sources, re.M)]
    order = {old: new for new, old in enumerate(sorted(set(listed)), 1)}
    if all(old == new for old, new in order.items()):
        return text
    swap = lambda prose: re.sub(r'\[(\d+)\](?!\()',  # noqa: E731
                                lambda m: f'[{order.get(int(m[1]), m[1])}]', prose)
    parts, last = [], 0
    for code in CODE.finditer(text):
        parts += [swap(text[last:code.start()]), code[0]]
        last = code.end()
    return ''.join(parts) + swap(text[last:])


def collapse_repeated_markers(text: str) -> str:
    """Keep each numeric citation once per run, leaving code and links alone."""
    # Dora and Jiexuan's pages repeated citations after sources merged (2026-10-16).
    swap = lambda prose: re.sub(r'\[\d+\](?!\()(?: ?\[\d+\](?!\())*',  # noqa: E731
                                lambda m: ''.join(dict.fromkeys(re.findall(r'\[\d+\]', m[0]))), prose)
    parts, last = [], 0
    for code in CODE.finditer(text):
        parts += [swap(text[last:code.start()]), code[0]]
        last = code.end()
    return ''.join(parts) + swap(text[last:])


# Every `investigation:` item is the run's own context, never the subject's
# evidence; cited, it refused pages it could simply leave out.
RUN_SOURCES = {"projects/": ("investigation:",),
               # The same refusal on a skill page (title-refine, 2026-10-08).
               "skills/": ("skill-runs:", "investigation:")}
MAPPED_LINE = re.compile(r'^- (Sessions|First seen|Last seen): [0-9-]+$', re.M)


def repair_run_citations(record: str, text: str, original: str) -> str:
    """Fix the two refusals of a project page that need no model.

    A 1.9.0 Codex init refused 4 of its first 8 project pages whole: they cited
    the run's own coverage note, or folded the mapped Sessions / First seen /
    Last seen lines into one. A line resting only on the run is dropped, a run
    citation beside a real one is removed, and the mapped lines are put back.
    """
    kind = next((prefix for prefix in RUN_SOURCES if record.startswith(prefix)), None)
    if not kind:
        return text
    if kind == "skills/" and "<!-- rem-skill-runs:start -->" in text:
        # Edited in place, a skill page kept the collector's Run evidence block
        # and the model added the heading again above it (linkedin-engagement).
        before, marker, after = text.partition("<!-- rem-skill-runs:start -->")
        before = re.sub(r"(?ms)^## Run evidence\n.*?(?=^## |\Z)", "", before)
        text = before.rstrip("\n") + "\n\n" + marker + after
    head, marker, tail = text.partition('\n## Sources\n')
    run = set(re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?\s*(?:' + '|'.join(map(re.escape, RUN_SOURCES[kind])) + r')',
                         tail, re.M)) if marker else set()
    if run:
        lines = []
        for line in head.splitlines(keepends=True):
            cites = re.findall(r'\[(W?\d+)\](?!\()', line)
            if cites and set(cites) <= run:
                # A Facts field keeps its label: "People: the user [4]" citing
                # investigation:page refused a whole first-run page (2026-10-20 trial).
                if CONTACT_LINE.match(line):
                    lines.append(CONTACT_LINE.match(line).group(0) + ' Unknown\n')
                continue
            lines.append(re.sub(r'\[(W?\d+)\](?!\()', lambda m: '' if m[1] in run else m[0], line))
        head = ''.join(lines)
    text = drop_uncited_sources(head + marker + tail)
    mapped = MAPPED_LINE.findall(prose(original))
    if mapped and MAPPED_LINE.findall(prose(text)) != mapped:
        lines = ''.join(m[0] + '\n' for m in MAPPED_LINE.finditer(original))
        text = MAPPED_LINE.sub('', text).replace('\n\n\n', '\n\n')
        paths = re.search(r'(?ms)^## Paths\n.*?(?=\n## |\Z)', text)
        at = paths.end() if paths else len(text.partition('\n## Sources\n')[0])
        rest = text[at:].lstrip('\n')
        text = text[:at].rstrip('\n') + '\n' + lines + ('\n' + rest if rest else '')
    return text


def normalize_numbered_sources(text: str) -> str:
    """Accept Markdown's numbered-list spelling for an otherwise valid citation.

    The model sometimes cites [1] in prose but writes `1. source-id` under
    Sources, or cites two at once as [1, 2]. Convert only the label, inside that section; source content and
    citation validation remain unchanged.
    """
    head, marker, tail = text.partition('\n## Sources\n')
    if not marker:
        return number_inline_sources(text)
    # "[1, 2]" is two citations; read as neither, both were reported unused
    # and the page was refused. A link's [text](url) is left alone.
    head = re.sub(r'\[(\d+(?:[ \t]*,[ \t]*\d+)+)\](?!\()',
                  lambda m: ''.join(f'[{n.strip()}]' for n in m.group(1).split(',')), head)
    after = re.search(r'^(?:## |Investigation:)', tail, re.M)
    sources, rest = (tail[:after.start()], tail[after.start():]) if after else (tail, '')
    sources = re.sub(r'(?m)^([ \t]*)(\d+)\.[ \t]+', r'\1- [\2] ', sources)
    # `- [3] \`git:…\`` is the same id: 7 real git citations were dropped for the backticks (v192b3).
    sources = re.sub(r'(?m)^([ \t]*- (?:\[W?\d+\][ \t]*:?[ \t]*)?)`([^`\n]+)`', r'\1\2', sources)
    return number_inline_sources(head + marker + sources + rest)


# A source id written where a citation number belongs: `[outlook:3a09…]`, or
# (`project-source:…`; `codex:…`). A link's target is never one.
INLINE_ID = r'(?!https?:|mailto:|file:///)[a-z][\w-]*:[^\s\[\]()`;,]+'
INLINE_CITATION = re.compile(rf'\[`?({INLINE_ID})`?\](?!\()'
                             rf'|(?<!\])\(\s*((?:`?{INLINE_ID}`?\s*[;,]\s*)*`?{INLINE_ID}`?)\s*\)')
UNNUMBERED_SOURCE = re.compile(rf'(?m)^([ \t]*)- (?=({INLINE_ID}))')


def number_inline_sources(text: str) -> str:
    """Turn source ids cited inline into numbered citations, defined once under Sources.

    Before this, every fact citing `[outlook:3a09…]` was uncited and went: one
    person investigation lost seven true fields, and a 4.56M-token project page
    whose every claim read (`project-source:…`) was refused for "no numbered
    evidence references" (v193q1, 2026-10-15).
    """
    head, marker, tail = text.partition('\n## Sources\n')
    after = re.search(r'^(?:## |Investigation:)', tail, re.M)
    sources, rest = (tail[:after.start()], tail[after.start():]) if after else (tail, '')
    numbers = [int(n) for n in re.findall(r'\[(\d+)\]', text)]
    counter = iter(range(max(numbers, default=0) + 1, 10 ** 6))
    sources = UNNUMBERED_SOURCE.sub(lambda m: f'{m[1]}- [{next(counter)}] ', sources)
    from .reader_model import SOURCE
    number = {source: key for key, source in SOURCE.findall(sources)}
    added = []

    def cite(match):
        ids = re.split(r'\s*[;,]\s*', (match[1] or match[2]).replace('`', '').strip())
        for source in ids:
            if source not in number:
                number[source] = str(next(counter))
                added.append(f'- [{number[source]}] {source}\n')
        return ''.join(f'[{number[source]}]' for source in ids)

    lines = [line if not visible.strip() else INLINE_CITATION.sub(cite, line)
             for line, visible in zip(head.split('\n'), prose(head).split('\n'))]
    head = '\n'.join(lines)
    if not added:
        return head + marker + sources + rest
    sources = (sources.rstrip('\n') + '\n' if sources.strip() else '') + ''.join(added)
    if not marker:
        status = re.search(r'(?m)^Investigation:', head)
        at = status.start() if status else len(head)
        return head[:at].rstrip('\n') + '\n\n## Sources\n' + sources + ('\n' + head[at:] if status else '')
    return head + marker + sources + ('\n' + rest if rest else '')


IDENTITY_LINE = re.compile(r'^(- (?:Email|Phone|Handles|Also known as): )(.*)$', re.M)


def _identity_key(value: str) -> str:
    """A phone compares by its last nine digits (+61 435 ... is 0435 ...); anything else by case-folded text."""
    value = re.sub(r"\s*\[W?\d+\]", "", value).strip()   # a part's own citation is not its digits
    digits = re.sub(r"\D", "", re.sub(r"\(.*?\)", "", value))
    return digits[-9:] if len(digits) >= 8 else value.casefold()


def drop_owner_addresses(text: str, owner: set[str]) -> tuple[str, list[str]]:
    """Take the account owner's own addresses and phones off someone else's identity lines.

    Mail between the user and a person carries both addresses, and a real page
    (Dora, 2026-09-23) listed the user's own Outlook as her email and handle;
    1.9.2b1 gave Weiwei the user's phone from his own quoted signature
    (2026-10-09), though the instructions forbid it. Which values are the
    owner's is known, so they are removed mechanically; the rest of the page is kept.
    """
    owner = {_identity_key(value) for value in owner}
    removed = []

    def clean(match):
        head, value = match.groups()
        body, cites = re.match(r'^(.*?)((?:\s*\[W?\d+\])*)\s*$', value).groups()
        parts = [part.strip() for part in re.split(r'[;,]', body) if part.strip()]
        kept = [part for part in parts if _identity_key(part) not in owner]
        removed.extend(part for part in parts if _identity_key(part) in owner)
        if kept == parts:
            return match.group(0)
        return head + ('; '.join(kept) + cites if kept else 'Unknown')

    return IDENTITY_LINE.sub(clean, text), sorted(set(removed))



PHONE_LINE = re.compile(r'^(- Phone: )(.*)$', re.M)


def drop_others_phones(text: str, others: list[str], own: list[str]) -> tuple[str, list[str]]:
    """Take a number off a contact's page when it is in someone else's own signature (#2348).

    1.9.2b1 put another person's number on 6 of 25 people, each from a signature
    quoted in the thread. Keeping only numbers from the person's own signature
    went too far: it took 7 right ones, a number given in their own words among
    them. A number that is theirs too (`own`) stays.
    """
    keys = {_identity_key(value) for value in others} - {_identity_key(value) for value in own}
    removed = []

    def clean(match):
        parts = [part.strip() for part in match.group(2).split(';') if part.strip()]
        kept = [part for part in parts if _identity_key(part) not in keys]
        removed.extend(part for part in parts if part not in kept)
        return match.group(0) if kept == parts else match.group(1) + ("; ".join(kept) or "Unknown")

    return PHONE_LINE.sub(clean, text), removed


def _cited_sources(text: str) -> dict[str, str]:
    """Citation number to source id, from the page's Sources."""
    from .reader_model import SOURCE
    return dict(SOURCE.findall(text.partition("\n## Sources\n")[2]))


def _source_item(root: Path, source: str, items: list[dict]) -> dict | None:
    """The cited mail or attachment as an item: from this run, else the private mail archive."""
    given = next((item for item in items if item.get("source") == source and "text" in item), None)
    provider, _, rest = source.partition(":")
    short, _, name = rest.partition(":")
    if given or provider not in ("gmail", "outlook") or not re.fullmatch(r"[0-9a-f]{12}", short):
        return given
    from .files import read_json, state_path
    from .mail_archive import _material_item
    path = next((path for folder in ("messages", "observed")
                 for path in sorted(state_path(root, f"mail/{folder}/{provider}").glob(short + "*.json"))), None)
    if path is None:
        return None
    item = _material_item(read_json(path, {}), set())
    if not name:
        return item
    from .attachments import extract_text
    attached = state_path(root, f"attachments/{provider}/{short}/{name}")
    return {**item, "text": extract_text(attached, limit=None)} if attached.is_file() else None


def _full_names(text: str, people: list[dict]) -> list[str]:
    """What the person is called in full: the page's title, a name in its brackets, the map's display names."""
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    full = [re.sub(r"\s*\(.*?\)", "", title), *re.findall(r"\((.*?)\)", title), *(p.get("name") or "" for p in people)]
    return sorted({" ".join(name.split()).casefold() for name in full if len(name.strip()) >= 3 and "@" not in name})


def _named_at(root: Path, items: list[dict], full: list[str]) -> set[str]:
    """Addresses that carry the person's name in a From, To or Cc of any mail we hold."""
    from email.utils import getaddresses

    from .mail_archive import mail_metadata
    found = set()
    given = [item.get("participants") or {"from": item.get("speaker") or ""} for item in items]
    for row in [*mail_metadata(root), *given]:
        for value in (row.get("from") or [], row.get("to") or [], row.get("cc") or []):
            for display, address in getaddresses(value if isinstance(value, list) else [value]):
                display = " ".join(display.strip("\"' ").split()).casefold()
                if display in full:
                    found.add(address.casefold())
    return found


def _own_addresses(text: str, held: set[str]) -> tuple[str, list[str]]:
    """Email keeps the addresses in `held`; Handles, which hold more than addresses, lose only relays."""
    from .files import EMAIL
    from .map import RELAY
    removed = []
    for label in ("Email", "Handles"):
        line = re.search(rf"(?m)^- {label}:[ \t]*(.*)$", text)
        if not line or not EMAIL.search(line[1]):
            continue
        parts = [piece.strip() for part in facts._split(line[1])
                 for piece in (part.split(",") if len(EMAIL.findall(part)) > 1 else [part]) if piece.strip()]
        found = [EMAIL.findall(part) for part in parts]
        kept = [part for part, addresses in zip(parts, found)
                if all(a.casefold() in held for a in addresses)
                or label == "Handles" and not any(RELAY.search(a) for a in addresses)]
        if kept != parts:
            removed += [part for part in parts if part not in kept]
            text = text[:line.start(1)] + ("; ".join(kept) or "Unknown") + text[line.end(1):]
    return text, removed


def _own_phones(root: Path, text: str, items: list[dict], held: set[str], names: list[str]) -> tuple[str, list[str]]:
    """Phone keeps a number a mail it cites, or any mail this run gathered, shows the person giving.

    Ivan's number was cited to an assistant session that quoted his Airbnb
    message; the message is in the material, so the number is still his. A
    number cited to a web page `[W…]` is a published one and is left as it was.
    """
    from .fact_extract import MAIL_SOURCES, gave_number
    line = re.search(r"(?m)^- Phone:[ \t]*(.*)$", text)
    parts, found = (facts._split(line[1]), facts.values(line[1])) if line else ([], [])
    if not found or len(parts) != len(found):
        return text, []
    sources = _cited_sources(text)
    mail = [item for item in items if str(item.get("source", "")).startswith(MAIL_SOURCES)]
    kept = [part for part, value in zip(parts, found)
            if any(n.startswith("W") for n in value["citations"]) or any(item and gave_number(item, value["value"], held, names)
                   for item in [*(_source_item(root, sources[n], items) for n in value["citations"] if n in sources),
                                *mail])]
    if len(kept) == len(parts):
        return text, []
    return text[:line.start(1)] + ("; ".join(kept) or "Unknown") + text[line.end(1):], [
        part for part in parts if part not in kept]


def verify_contacts(root: Path, record: str, text: str, items: list[dict], original: str = "") -> tuple[str, list[str]]:
    """A Phone or Email stays only when the material shows it is this person's own (#2348).

    Removal was a denylist: another sender's signature number went, and anything
    else stayed. 1.9.2b3 still put a facilities manager's mobile on Nina's page
    from a notice she forwarded, "call Larry 0405…" on Ody's from a Luma host
    copy, and Luma relays as two people's Email (contacts audit P1, P2, E1, E2).
    An Email is one the page already carried (the map's, or the user's own
    `co rem stub`), or one the person is named at in a From, To or Cc; a relay
    never is. A Phone needs a mail the person sent (or a
    relay message under their name) with the number and nobody else named to
    call beside it. A missing value is Unknown; a wrong one is worse.
    """
    from .files import EMAIL, read_json, state_path
    from .map import RELAY
    people = [p for p in read_json(state_path(root, "map.json"), {}).get("people", []) if p.get("record") == record]
    carried = re.search(r"(?m)^- Email:[ \t]*(.*)$", original)
    known = {a.casefold() for p in people for a in p.get("addresses") or [p.get("address") or ""] if a} | {
        a.casefold() for a in EMAIL.findall(carried[1] if carried else "")}
    full = _full_names(text, people)
    names = sorted({*full, *(name.split()[0] for name in full if len(name.split()[0]) >= 3)})
    held = {a for a in known | _named_at(root, items, full) if not RELAY.search(a)}
    text, addresses = _own_addresses(text, held)
    text, phones = _own_phones(root, text, items, held, names)
    return text, addresses + phones


# What an investigation hands the model about itself, not about the subject.
# A page that cites only these was written from nothing (#1974).
CONTEXT_SOURCES = ("investigation:page", "investigation:coverage", "investigation:quick-scope",
                   "investigation:project-inventory", "investigation:project-repositories",
                   "investigation:original-evidence", "investigation:timeline",
                   "investigation:org-pages", "investigation:facts", "investigation:skill-records")


def _known_sources(items: list[dict]) -> set:
    known = {i['source'] for i in items if i.get('source') and i['source'] != 'investigation:page'}
    # Fact extraction reads all gathered mail before a quick turn samples it.
    # A restored field may cite mail outside that sample; its provenance is in
    # the facts item even though the raw mail is absent from this turn.
    known.update(row['source'] for item in items if item.get('role') == 'facts'
                 for row in item.get('facts', []) if row.get('source'))
    derived = [source for i in items if i.get("role") in ("reflection-summary", "extract", "evidence-index", "owner-work-evidence")
               for source in i.get("sources", [])]
    known.update(derived)
    # Numbered pieces are one original record. A citation to the whole record
    # remains traceable when the model omits the layout-only part suffix.
    known.update(re.sub(r':part-\d+$', '', source) for source in derived)
    # A coding session is one transcript file; citing the session rather than
    # one line of it is coarse but traceable. Dora's page cited
    # `claude-code:<session>` for an account digested from that session.
    known.update(source.rsplit(":", 1)[0] for source in derived
                 if source.startswith(("codex:", "claude-code:")) and source.count(":") >= 2)
    return known


# An assistant's memory and transcript folders hold its own notes, not material.
# Ian's page cited the owner's Claude memory file, which sat beside a supplied
# transcript (1.9.2b1). A session is cited by its id, `claude-code:<id>`.
PRIVATE_STORE = re.compile(r'/\.claude/projects/|/\.codex/(?:sessions|archived_sessions|memories)/')


PINNED_FILE = re.compile(r'^file:(/[^\s#]+)#sha256:([0-9a-f]{64})\b')


def _pinned_file(value: str) -> bool:
    """A local file cited with the hash it has now: the job-followup skill page
    cited its applications log this way and was refused, as only project pages
    accepted a `file:` id (1.9.2b3)."""
    import hashlib
    match = PINNED_FILE.match(value.strip())
    return bool(match) and Path(match[1]).is_file() and \
        hashlib.sha256(Path(match[1]).read_bytes()).hexdigest() == match[2]


def archived(root: Path, source: str) -> bool:
    """rem itself holds this message: in rem.db, or as mail kept under .state/mail.

    Only the turn's own items used to count. Ody's 2.04M-token investigation
    was refused for [27][28], real mail in .state/mail that supported the
    claim; 18 mail citations went the same way over nine pages (v192b3).
    """
    import sqlite3
    from contextlib import closing
    from .files import state_path
    from .reader_model import _cited_row
    file = state_path(root, 'rem.db')
    if file.is_file() and not file.is_symlink():
        with closing(sqlite3.connect(file.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            if _cited_row(db, source) is not None:
                return True
    mail = re.fullmatch(r'(gmail|outlook):([0-9a-f]{12})', source)
    return bool(mail) and any(next(state_path(root, f'mail/{folder}/{mail[1]}').glob(mail[2] + '*.json'), None)
                              for folder in ('messages', 'observed'))


def _archived_sources(root: Path | None, definitions) -> set[str]:
    if root is None:
        return set()
    ids = {re.split(r'\s+[—–]\s+', value.strip(), 1)[0] for _, value in definitions}
    return {source for source in ids if archived(root, source)}


def _mail_digest(root: Path, source: str) -> str:
    """A raw provider id (a Graph `AQMk…` id) as the digest id the archive files it under."""
    import hashlib
    match = re.fullmatch(r'(gmail|outlook):(\S+)', source)
    if not match or re.fullmatch(r'[0-9a-f]{12}', match[2]):
        return source
    digest = f'{match[1]}:{hashlib.sha256(match[2].encode()).hexdigest()[:12]}'
    return digest if archived(root, digest) else source


SHORT_PIN = re.compile(r'file:(/[^\s@#]+?)(?:@sha256:|#sha256[:=]|@)([0-9a-f]{7,64})')


def _repin(record: str, source: str) -> str:
    """`file:/x@905fb89` pinned to the SHA-256 the file has now, when that is the content named.

    41 such citations were dropped in v192b3: a short hash, a commit, or a
    truncated SHA-256, each naming the file as it still is.
    """
    import hashlib
    import subprocess
    match = SHORT_PIN.fullmatch(source)
    path = Path(match[1]) if match else None
    if path is None or path.is_symlink() or not path.is_file():
        return source
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if not digest.startswith(match[2]):
        committed = subprocess.run(['git', '-C', str(path.parent), 'show', f'{match[2]}:./{path.name}'],
                                   capture_output=True)
        if committed.returncode or committed.stdout != raw:
            return source
    return f'file:{path}@{digest}' if record.startswith('projects/') else f'file:{path}#sha256:{digest}'


def resolve_sources(root: Path, record: str, text: str) -> str:
    """Write each Sources id in the form that resolves: mail by its digest, a file by its full hash."""
    head, marker, tail = text.partition('\n## Sources\n')
    if not marker:
        return text
    entry = re.compile(r'(?m)^([ \t]*- \[W?\d+\][ \t]*:?[ \t]*)(\S+)')
    return head + marker + entry.sub(lambda m: m[1] + _repin(record, _mail_digest(root, m[2])), tail)


def _identifiable(value: str, *, known, record, original, old_sources, items, pages) -> bool:
    if PRIVATE_STORE.search(value):
        return False
    if record.startswith('projects/') and value.strip().startswith(('file:', 'git:')):
        from .project_pages import live_source_snapshot
        source = re.split(r'\s+[—–]\s+', value.strip(), 1)[0]
        return value.strip() in old_sources or live_source_snapshot(original, source) is not None
    if _pinned_file(value):
        return True
    return bool(any(source in value for source in known) or value.strip() in old_sources
                or re.search(r'https?://\S+', value) or _local_reference(value, original, items)
                or prior_context_reference(value, record, items, original)
                # The map's own record, when the page already cited it: a real
                # pass reworded "Enumeration metadata ... .state/map.json".
                or ('.state/map.json' in value and '.state/map.json' in original)
                # "The page as it stood said so", named by the page item's own id.
                or 'investigation:page' in value
                # A citation carried over from the page before this run: every
                # source id it names is already in that page's Sources, reworded.
                or _carried_over(value, old_sources)
                # Another page of this notebook, named as context -- never as
                # corroboration: "Existing mapped page `people/…md`, inspected".
                or (re.search(r'\b(existing|mapped|prior)\b', value, re.I)
                    and any(page in value for page in pages if page != record)))


def _material(value: str, *, known, record, original, old_sources, items) -> bool:
    """Does this Sources entry name something about the subject, not the run's own context?"""
    if record.startswith('projects/') and value.strip().startswith(('file:', 'git:')):
        from .project_pages import live_source_snapshot
        source = re.split(r'\s+[—–]\s+', value.strip(), 1)[0]
        return value.strip() in old_sources or live_source_snapshot(original, source) is not None
    if '.state/map.json' in value or 'Enumeration metadata' in value:
        return False
    material = known - set(CONTEXT_SOURCES)
    return bool(any(source in value for source in material) or re.search(r'https?://\S+', value)
                or _local_reference(value, original, items) or _carried_over(value, old_sources)
                or (value.strip() and value.strip() in old_sources
                    and not any(source in value for source in CONTEXT_SOURCES)))


PLACEHOLDER = 'Unknown — not investigated yet'


def clear_placeholders(text: str) -> str:
    """After its investigation a page no longer says it was not investigated (#2008).

    Project pages came back after 0.6-0.9M tokens with five and six sections
    still reading "Unknown — not investigated yet", and were refused for it.
    The material showed nothing there, so the section says a bare `Unknown`;
    a line that also says something keeps it. Only for a page's own
    investigation: an upkeep pass that touched one line is not asked to finish the rest.
    """
    head, marker, tail = text.partition('\n## Sources\n')
    parts = re.split(r'(?m)^(## .+)$', head)
    for index in range(2, len(parts), 2):
        if PLACEHOLDER not in parts[index]:
            continue
        lines = [line.replace(PLACEHOLDER, 'Unknown') for line in parts[index].split('\n')
                 if line.strip().lstrip('- ') != PLACEHOLDER]
        parts[index] = '\n'.join(lines) if any(line.strip() for line in lines) else '\n- Unknown\n\n'
    return ''.join(parts) + marker + tail


def single_title(text: str) -> str:
    """Keep the first `# ` title; a second one is the turn repeating it, not a reason to refuse."""
    seen, kept = False, []
    for line, visible in zip(text.split('\n'), prose(text).split('\n')):
        if re.match(r'# \S', visible):
            if seen:
                continue
            seen = True
        kept.append(line)
    return '\n'.join(kept)


# The skills ask for about 15k characters; past this a candidate that grew the
# page is refused (#2019). On a copy of the owner's notebook (2026-10-01) 696 of
# 698 pages were under 15k and the largest page grown from read material was
# 18.9k; one daily update took a project page from 13.4k to 25.3k.
PAGE_LIMIT = 20_000


# How the tool ran, said on a page about someone else (#2058): "web: not
# searched; Wiki runs are offline" sat in 5 of the owner's 7 investigated
# person pages, and Tamara's History opened with "The current collector
# reports 50 matching Outlook messages with 50 bodies read".
TOOL_TEXT = re.compile(r"\bnot searched\b|\boffline\b.{0,20}\b(?:wiki|rem|run)\b|\b(?:wiki|rem) runs?\b.{0,12}\boffline\b"
                       r"|\bcollector (?:reports|found|read)\b|\bbodies read\b", re.IGNORECASE)


def drop_tool_text(record: str, text: str, original: str) -> tuple[str, list[str]]:
    """Remove lines a candidate adds about the run rather than the subject; above Sources only.

    Removed, not refused: a refusal re-runs a turn that cost 600k tokens over
    a sentence. A contact field keeps its label and says Unknown, as
    `drop_unresolved` does. Lines the page already had are tidy's (#2058)."""
    head, marker, tail = text.partition('\n## Sources\n')
    before, kept, removed = set(original.splitlines()), [], []
    for line in head.split('\n'):
        if line in before or not TOOL_TEXT.search(line):
            kept.append(line)
            continue
        removed.append(line.strip())
        contact = CONTACT_LINE.match(line) if record.startswith('people/') else None
        if contact:
            kept.append(f'- {contact[1]}: Unknown')
    return '\n'.join(kept) + marker + tail, removed


# History is threads and how they ended (#2059, #2314): Ody Zhou's once held 17
# bullets, five of them "sent report X"; eight then squeezed out how threads ended.
HISTORY_LIMIT = 16


# A line that says what is not known instead of what is. The page template has
# one place for these, Uncertainties, and a ceiling of five there.
HEDGE = re.compile(r"not (?:established|confirmed|documented|verified|recorded|stated)|unknown whether"
                   r"|is unknown|remains? (?:unknown|unconfirmed|unresolved)"
                   r"|no (?:outcome|reply) (?:is )?(?:documented|found|recorded)|does not say|cannot be verified"
                   # Richard Lai, 2026-10-15: "no reply or completion is established in the supplied mail", 8 times.
                   r"|\bunconfirmed\b|is established in|do(?:es)? not establish|in the supplied (?:mail|material|messages|record)", re.I)


def hedged_lines(text: str) -> list[tuple[str, str]]:
    """(section, line) for every hedge outside Uncertainties and Sources.

    After 1.9.2b1 let a pass delete, the hedges on one real page did not fall
    (16 -> 19): they moved from Uncertainties into the lead, History and Open
    threads (#2343). On the 2026-10-10 trial 56 of 87 person pages carried
    them there. A page without an Uncertainties section is not of this shape.
    """
    if not re.search(r"(?m)^## Uncertainties\s*$", text):
        return []
    found, section = [], "lead"
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section in ("Uncertainties", "Sources") or line.startswith("Investigation:"):
            continue
        if HEDGE.search(line):
            found.append((section, line.strip()))
    return found


def _history(text: str) -> list[str]:
    section = prose(text).partition('\n## History\n')[2].split('\n## ', 1)[0]
    return [line for line in section.splitlines() if line.startswith('- ') and 'not investigated yet' not in line]


def history_note(page: str) -> str:
    """The History limit, said before the turn, for a page that already has a History."""
    lines = len(_history(page))
    if not lines:
        return ""
    return (f"History holds at most {HISTORY_LIMIT} dated lines, one per thread with how it ended; it has {lines}"
            + (": fold the oldest into one line per year. " if lines > HISTORY_LIMIT else ". "))


DATED = re.compile(r'^- \**(\d{4})(?:-\d{2}){0,2}\**[ \t]*[:—–-][ \t]*(.*)$')


def sort_history(text: str) -> str:
    """History and Key decisions newest first, in code: a dated story read out of order misleads.

    2026-10-20 trial: three of five first-run person pages put one line out of
    order although the Skill says newest first. Undated lines keep their place
    after the dated ones; lines of one date keep the turn's order.
    """
    for heading in ('History', 'Key decisions'):
        span = re.search(rf'(?ms)^## {heading}[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)', text)
        if not span:
            continue
        lines = span[1].split('\n')
        dated = [line for line in lines if DATED.match(line)]
        if len(dated) < 2:
            continue
        ordered = iter(sorted(dated, key=lambda line: re.match(r'^- \**([\d-]+)', line)[1], reverse=True))
        lines = [next(ordered) if DATED.match(line) else line for line in lines]
        text = text[:span.start(1)] + '\n'.join(lines) + text[span.end(1):]
    return text


def fold_history(text: str) -> str:
    """Fold the oldest years of a History past its limit into one line a year, in code.

    The skill asks the turn to do this; when it does not, the page was refused
    whole for a seventeenth line. The newest year is never folded: what is
    current stays one line per thread, and `history_errors` still has the last word.
    """
    span = re.search(r'(?ms)^## History[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)', text)
    if not span:
        return text
    lines = span[1].split('\n')
    excess = len(_history(text)) - HISTORY_LIMIT
    for year in sorted({m[1] for line in lines if (m := DATED.match(line))})[:-1]:
        dated = [line for line in lines if (m := DATED.match(line)) and m[1] == year]
        if excess <= 0:
            break
        if len(dated) < 2:
            continue
        folded = f'- {year}: ' + '; '.join(DATED.match(line)[2].rstrip(' .') for line in dated) + '.'
        at = lines.index(dated[0])
        lines = [line for line in lines if line not in dated]
        lines.insert(at, folded)
        excess -= len(dated) - 1
    return text[:span.start(1)] + '\n'.join(lines) + text[span.end(1):]


def history_errors(candidate: str, original: str) -> list[str]:
    """A History past 16 lines may not grow; one already past may come down in steps."""
    lines, before = len(_history(candidate)), len(_history(original))
    if lines <= HISTORY_LIMIT or lines <= before:
        return []
    return [f'History has {lines} lines (was {before}); keep at most {HISTORY_LIMIT} dated lines, one per thread '
            'with how it ended: fold the oldest into one line per year, and drop sends, reminders and newsletters']


# Over the limit by less than this, the page is kept: code folds its History and
# the next pass is asked to come down. Refused at 20,493 characters, a page cost
# 643k tokens and then 933k more on the same mail (#2026).
PAGE_REFUSED = PAGE_LIMIT * 3 // 2


def size_errors(candidate: str, original: str) -> list[str]:
    """A page far over the limit may not grow; one already over may come down in steps."""
    if len(candidate) <= PAGE_REFUSED or len(candidate) <= len(original):
        return []
    return [f'Page is {len(candidate):,} characters (was {len(original):,}), over the {PAGE_LIMIT:,} limit; '
            'keep it near 15,000: fold the oldest History into dated one-line summaries with their '
            'citations, and keep the lead and the current state']


def size_note(page_chars: int) -> str:
    """The limit `size_errors` enforces, said in the prompt before the turn rather than after it.

    Said only in the review, a page near the limit was written at full length,
    refused, and retried: 20,493 characters, 643k tokens, then 933k more on
    the same mail (#2026 for project pages, #2041 for the others)."""
    if page_chars <= PAGE_LIMIT * 3 // 4:
        return f"The page must stay under {PAGE_LIMIT:,} characters. "
    return (f"The page is {page_chars:,} characters; it must end under {PAGE_LIMIT:,}, or at least not grow: "
            "first fold the oldest History into dated one-line summaries with their citations, then add. ")


def validate(record: str, candidate: str, original: str, items: list[dict], pages=frozenset(),
             owner: bool = False, root: Path | None = None) -> list[str]:
    """Structural checks only; citation existence does not prove factual entailment."""
    body = prose(candidate)
    errors = size_errors(candidate, original) + history_errors(candidate, original)
    if len(re.findall(r'^# .+', body, re.M)) != 1:
        errors.append('Expected exactly one page title')
    if record.startswith('skills/catalog/'):
        old_title = re.search(r'^# (.+)$', prose(original), re.M)
        new_title = re.search(r'^# (.+)$', body, re.M)
        if old_title and new_title and old_title[1] != new_title[1]:
            errors.append('Preserve the exact skill invocation name as the page title')
    counts = Counter(re.findall(r'^## (.+)$', body, re.M))
    errors += [f'Missing section: {h}' if counts[h] == 0 else f'Section must occur once: {h}'
               for h in headings(record, owner) if counts[h] != 1]
    errors += [f'Duplicate section: {h}' for h, n in counts.items() if n > 1]
    if re.findall(r'^Investigation:.*$', body, re.M) != re.findall(r'^Investigation:.*$', original, re.M):
        errors.append('Investigation status belongs to the runner')
    content, _, sources = body.partition('\n## Sources\n')
    refs = set(re.findall(r'\[(W?\d+)\](?!\()', content))
    definitions = re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?(.*)$', sources, re.M)
    defined = Counter(key for key, _ in definitions)
    errors += [f'Missing or duplicate citation: {key}' for key in refs if defined[key] != 1]
    known = _known_sources(items) | _archived_sources(root, definitions)
    if record.startswith('projects/'):
        from .project_pages import live_source_snapshot
        carried = original.partition('\n## Sources\n')[2]
        for _, value in definitions:
            source = re.split(r'\s+[—–]\s+', value.strip(), 1)[0]
            if source.startswith(('file:', 'git:')) and value.strip() not in carried:
                if live_source_snapshot(original, source):
                    known.add(source)
                else:
                    errors.append(f'Cited file needs a hash or exact Git commit in a mapped repository: {source}')
    if record.startswith('projects/'):
        if any(item.get('role') == 'project-input-scope' and item.get('inputs_read') == 0 for item in items):
            for heading in ('Insight', 'Open threads'):
                section = re.search(rf'(?ms)^## {heading}\n(.*?)(?=^## |\Z)', body)
                if section and not re.fullmatch(r'-?\s*Unknown', section[1].strip(), re.I):
                    errors.append(f'No assigned project session inputs: keep {heading} Unknown')
        for label in ('Sessions', 'First seen', 'Last seen'):
            pattern = r'^- ' + re.escape(label) + r': [0-9-]+$'
            previous = re.findall(pattern, prose(original), re.M)
            if previous and re.findall(pattern, body, re.M) != previous:
                errors.append(f'Preserve mapped project metadata: {label}')
    old_sources = original.partition('\n## Sources\n')[2]
    for key, value in definitions:
        if record.startswith('projects/') and value.strip().startswith('/') and value.strip() not in old_sources:
            errors.append(f'Cited local file needs a file: source ID and SHA-256: {key}')
        if record.startswith('projects/') and value.strip().startswith('investigation:project-inventory'):
            errors.append(f'Candidate file inventory is not a citable original: {key}')
        if record.startswith('projects/') and value.strip().startswith('investigation:project-repositories'):
            errors.append(f'Project paths are reading leads, not citable originals: {key}')
        if record.startswith('projects/') and value.strip().startswith('investigation:coverage'):
            errors.append(f'Investigation coverage belongs in the run report, not page Sources: {key}')
        if record.startswith('projects/') and value.strip().startswith('investigation:project-scope'):
            errors.append(f'Project input scope is not a citable original: {key}')
        if record.startswith('projects/') and value.strip().startswith('investigation:timeline'):
            errors.append(f'Project timeline is a reading guide, not a citable original: {key}')
        if record.startswith('skills/') and value.strip().startswith(('skill-runs:', 'investigation:page')):
            errors.append(f'Skill run summaries and carried pages are not citable originals: {key}')
        files = {path for path in re.findall(r'`(/[^`]+)`', value) if Path(path).is_file()}
        if len(files) > 1:
            errors.append(f'Citation bundles multiple files: {key}')
        if key not in refs:
            errors.append(f'Unused citation: {key}')
        if not _identifiable(value, known=known, record=record, original=original, old_sources=old_sources,
                             items=items, pages=pages):
            errors.append(f'Citation has no identifiable source: {key}')
    if candidate != original and not refs:
        errors.append('Changed page has no numbered evidence references')
    investigation = any(item.get('role') == 'page' and item.get('record') == record for item in items)
    if (investigation and candidate != original and definitions
            and not any(_material(value, known=known, record=record, original=original,
                                  old_sources=old_sources, items=items) for _, value in definitions)):
        # founders@unsw (1.9.0a2): 919k tokens, stamped "investigated", written
        # from the page and the coverage note -- nothing about the subject.
        errors.append('Page cites only the page itself and the coverage note; nothing about the subject was read')
    errors += fact_errors(record, candidate, original)
    return errors


def fact_errors(record: str, candidate: str, original: str) -> list[str]:
    """Every Facts label present; every value cited unless the page already carried it (#2068).

    An uncited value carried over from the page before is the page's history,
    not this turn's claim; the map's own addresses need no citation at all.
    """
    labels = facts.fields(record)
    span = re.search(r'(?ms)^## Facts[ \t]*\n(.*?)(?=^## |\Z)', prose(candidate))
    if not labels or not span:
        return []
    errors = [f'Missing fact field: {label}' for label in labels
              if not re.search(r'^- ' + re.escape(label) + ':', span[1], re.M)]
    before = facts.parse(original, record) if original else {}
    for label, found in facts.parse(candidate, record).items():
        carried = {v['value'] for v in before.get(label, [])}
        if label not in facts.UNCITED and any(not v['citations'] and v['value'] not in carried for v in found):
            errors.append(f'Fact without a citation: {label}; cite the message it came from, or write Unknown')
    return errors


CITATION = re.compile(r'\[(W?\d+)\](?!\()')
CONTACT_LINE = re.compile(r'^- (' + '|'.join(re.escape(label) for labels in facts.FIELDS.values()
                                             for label in labels) + r'):')


def unresolved_findings(text: str, citations: list[str]) -> list[str]:
    """Do not silently discard the findings the user came to read."""
    bad, section, found = set(citations), 'Lead', {}
    for line in prose(text).splitlines():
        if line.startswith('## '):
            section = line[3:].strip()
        marks = set(CITATION.findall(line))
        if section in ('Lead', 'Insight', 'Current status', 'Open threads') and marks and marks <= bad:
            found.setdefault(section, set()).update(marks)
    return [f'Finding has unresolved citations in {section}: ' + ', '.join(f'[{n}]' for n in sorted(marks))
            for section, marks in found.items()]


def drop_unresolved(record: str, text: str, original: str, items: list[dict],
                    pages=frozenset(), root: Path | None = None) -> tuple[str, dict]:
    """Remove only what rests on a citation that cannot be traced, instead of refusing the page (#1974).

    A project page was refused after 199 seconds and 16k output tokens for one
    miscopied session id; everything else on it was cited correctly. The
    validator already decides which citations resolve, so this acts on that
    decision: a marker beside a good citation goes, a line resting on it alone
    goes (a contact field keeps its label and says Unknown), its Sources entry
    goes. What remains is validated as usual.
    """
    nothing = {'citations': [], 'lines': 0}
    head, marker, tail = text.partition('\n## Sources\n')
    if not headings(record) or not marker:
        return text, nothing
    after = re.search(r'^(?:## |Investigation:)', tail, re.M)
    sources, rest = (tail[:after.start()], tail[after.start():]) if after else (tail, '')
    definitions = re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?(.*)$', sources, re.M)
    defined = Counter(key for key, _ in definitions)
    old_sources = original.partition('\n## Sources\n')[2]
    known = _known_sources(items) | _archived_sources(root, definitions)
    bad = {key for key, value in definitions if defined[key] == 1 and not _identifiable(
        value, known=known, record=record, original=original, old_sources=old_sources, items=items, pages=pages)}
    bad |= {key for key in CITATION.findall(prose(head)) if not defined[key]}
    if not bad:
        return text, nothing
    kept, dropped = [], 0
    for line, visible in zip(head.split('\n'), prose(head).split('\n')):
        cited = CITATION.findall(visible)
        if not set(cited) & bad:
            kept.append(line)
            continue
        dropped += 1 if set(cited) <= bad or CONTACT_LINE.match(line) else 0
        if CONTACT_LINE.match(line) and set(cited) <= bad:
            kept.append(CONTACT_LINE.match(line).group(0) + ' Unknown')
        elif not set(cited) <= bad:
            kept.append(re.sub(r'[ \t]*\[(?:' + '|'.join(sorted(bad)) + r')\](?!\()', '', line))
    head = _fill_emptied_sections('\n'.join(kept))
    sources = ''.join(line for line in sources.splitlines(keepends=True)
                      if not ((match := re.match(r'^\s*(?:- )?\[(W?\d+)\]', line)) and match[1] in bad))
    return head + marker + sources + rest, {'citations': sorted(bad), 'lines': dropped}


def add_missing_sections(record: str, text: str, owner: bool = False) -> str:
    """A required section the turn left out is added as Unknown, in its place.

    1.9.2b3 trial: a project page without Open threads and a skill page
    without Limitations were refused whole, after every other section was
    written. Unknown is what the page knows about the missing one.
    """
    required = headings(record, owner)
    for index, heading in enumerate(required):
        if re.search(rf'^## {re.escape(heading)}[ \t]*$', text, re.M):
            continue
        later = (re.search(rf'^## {re.escape(h)}[ \t]*$', text, re.M) for h in required[index + 1:])
        at = next((m.start() for m in later if m), len(text))
        text = text[:at] + f'## {heading}\n- Unknown\n\n' + text[at:]
    return text


def _placeholder(body: str) -> bool:
    return not body.strip() or bool(re.fullmatch(r'(?:- )?(?:Unknown|None)\b[^\n]*', body.strip()))


def merge_duplicate_sections(record: str, text: str, owner: bool = False) -> str:
    """One section per heading, settled by code instead of refusing the page.

    A heading glued to the end of a paragraph ("... [10]. ## Our relationship")
    goes back on its own line: hamish-mcfarlane was refused for it on every
    pass since 1.9.2b3's init. A repeated section keeps the copy with content
    and appends any second real body to the first, in place.
    """
    names = '|'.join(re.escape(h) for h in _canonical_headings(record, owner))
    if not names:
        return text
    text = re.sub(rf'(?m)(\S)[ \t]+(## (?:{names})[ \t]*)$', r'\1\n\n\2', text)
    parts = re.split(rf'(?m)^(## (?:{names}))[ \t]*$', text)
    first, merged = {}, [parts[0]]
    for index in range(1, len(parts), 2):
        heading, body = parts[index], parts[index + 1]
        if heading not in first:
            first[heading] = len(merged)
            merged += [heading, body]
            continue
        at = first[heading] + 1
        if _placeholder(merged[at]):
            merged[at] = body
        elif not _placeholder(body):
            lines = [line for line in body.strip('\n').split('\n') if line not in merged[at].split('\n')]
            merged[at] = merged[at].rstrip('\n') + '\n' + '\n'.join(lines) + '\n\n'
    return ''.join(merged)


def _fill_emptied_sections(head: str) -> str:
    """A section whose every line went says Unknown, so the page keeps its shape."""
    parts = re.split(r'(?m)^(## .+)$', head)
    for index in range(1, len(parts), 2):
        body = parts[index + 1] if index + 1 < len(parts) else ''
        if not body.strip():
            parts[index + 1] = '\n- Unknown\n\n' if index + 1 < len(parts) else ''
    return ''.join(parts)


def person_names(notebook, owner: str = '') -> dict:
    """{full name: record} for people pages a sentence can safely link: two words or more, one page each."""
    seen, first_names = {}, {}
    for person in notebook.list('people'):
        page = notebook.read(person)
        title = next((line[2:].strip() for line in page.splitlines() if line.startswith('# ')), '')
        if person == owner or '@' in title:
            continue
        if len(title.split()) >= 2 and len(title) >= 5:
            seen.setdefault(title, []).append(person)
        elif re.fullmatch(r'[A-Z][a-z]{2,}', title):
            email = (re.search(r'^- Email: (.*)$', page, re.M) or [None, ''])[1]
            first_names.setdefault(title, []).append((person, email.split('@')[0].casefold()))
    names = {name: records[0] for name, records in seen.items() if len(records) == 1}
    # A page titled by a first name, as the mail's display name gave it ("Ivan"): a
    # full name in a sentence ("Ivan Zhu") is that page when it is the only "Ivan"
    # and its address carries the surname (ivanxzhu@). Two Harrys link neither.
    names.update({f'{first} *': pages[0] for first, pages in first_names.items() if len(pages) == 1})
    return names


def link_people(record: str, text: str, names: dict) -> str:
    """The first mention of a person the notebook has a page for links to it (#2060).

    Ody Zhou's page named Harry Cao, Ivan Zhu and James Guo, who all had pages,
    and linked none; 2 of the owner's 381 people pages had any link at all.
    Exact full names only, outside Contact fields and Sources, so nothing is guessed."""
    head, marker, tail = text.partition('\n## Sources\n')
    lines = head.split('\n')
    for name, target in sorted(names.items(), key=lambda item: -len(str(item[0]))):
        if isinstance(target, tuple):        # a first-name page: (record, address local part)
            target, local = target
            pattern = re.compile(r'(?<![\w\[/])' + re.escape(name[:-2]) + r' ([A-Z][a-z]+)(?![\w\]])')
            hits = {m[0] for line in lines for m in pattern.finditer(line) if m[1].casefold() in local}
            if len(hits) != 1:
                continue
            name = hits.pop()
        if target == record or f'[{name}](' in head:
            continue
        pattern = re.compile(r'(?<![\w\[/])' + re.escape(name) + r'(?![\w\]])')
        for i, line in enumerate(lines):
            if line.startswith(('#', 'Investigation:')) or CONTACT_LINE.match(line):
                continue
            # Not inside an existing link's label or target.
            spans = [m.span() for m in re.finditer(r'\[[^\]]*\]\([^)]*\)', line)]
            found = next((m for m in pattern.finditer(line)
                          if not any(a <= m.start() < b for a, b in spans)), None)
            if found:
                lines[i] = line[:found.start()] + f'[{name}](../{target})' + line[found.end():]
                break
    return '\n'.join(lines) + marker + tail


def project_names(notebook) -> dict[str, str]:
    """Only unique, specific project titles are safe to link from the owner's page."""
    seen = {}
    for record in notebook.list('projects'):
        title = next((line[2:].strip() for line in notebook.read(record).splitlines()
                      if line.startswith('# ')), '')
        if len(title) >= 4 or (len(title) >= 2 and title.isupper()):
            seen.setdefault(title.casefold(), []).append((title, record))
    return {title: records[0][1] for title, records in seen.items() if len(records) == 1}


def link_projects(text: str, names: dict[str, str]) -> str:
    """Link the first exact project name on the owner's page, outside fields and sources."""
    head, marker, tail = text.partition('\n## Sources\n')
    lines = head.split('\n')
    for title, target in sorted(names.items(), key=lambda item: -len(item[0])):
        pattern = re.compile(r'(?<![\w\[/])' + re.escape(title) + r'(?![\w\]])', re.I)
        if re.search(r'\]\(\.\./' + re.escape(target) + r'\)', head):
            continue
        for index, line in enumerate(lines):
            if (line.startswith(('#', 'Investigation:')) or CONTACT_LINE.match(line)
                    or not re.search(r'\[W?\d+\]', line)):
                continue
            linked = [match.span() for match in re.finditer(r'\[[^\]]*\]\([^)]*\)', line)]
            found = next((match for match in pattern.finditer(line)
                          if not any(start <= match.start() < end for start, end in linked)), None)
            if found:
                name = line[found.start():found.end()]
                lines[index] = line[:found.start()] + f'[{name}](../{target})' + line[found.end():]
                break
    return '\n'.join(lines) + marker + tail


def link_company(notebook, record: str, text: str) -> str:
    """`Company:` naming an organisation the notebook has a page for links to it (#1974).

    0 of 4 person pages whose company had an organisation page linked it; the
    title match is exact, so nothing is guessed.
    """
    match = re.search(r'^- Company: (.*)$', text, re.M)
    if not record.startswith('people/') or not match:
        return text
    name, cites = re.match(r'^(.*?)((?:\s*\[W?\d+\])*)\s*$', match.group(1)).groups()
    name = name.strip()
    if not name or name.startswith('[') or name.casefold().startswith('unknown'):
        return text
    for org in notebook.list('orgs'):
        title = next((line[2:].strip() for line in notebook.read(org).splitlines() if line.startswith('# ')), '')
        if title.casefold() == name.casefold():
            return text[:match.start()] + f'- Company: [{name}](../{org}){cites}' + text[match.end():]
    return text


def _named_orgs(notebook) -> list[tuple[str, str, list[str]]]:
    """(record, title, domains) of each organisation page whose title is a name, not its domain."""
    from .investigate import org_domains
    found = []
    for org in notebook.list('orgs'):
        page = notebook.read(org)
        title = next((line[2:].strip() for line in page.splitlines() if line.startswith('# ')), '')
        if title and title.casefold() not in org_domains(page):
            found.append((org, title, org_domains(page)))
    return found


def _employer_domain(address: str) -> str:
    """The domain of an address that can name an employer, or '' (contacts audit C1-C4).

    Not a mailbox provider, a relay, a ConnectOnion agent's mail, or a student
    address: `student.`/`ad.` subdomains and an ID for a local part
    (z1234567@unsw.edu.au) prove enrolment, and the skill says that is Unknown.
    """
    from .map import AGENT_ADDRESS, RELAY
    from .scan import personal_mailbox
    local, _, domain = address.casefold().rpartition("@")
    if (personal_mailbox(domain) or RELAY.search(address) or AGENT_ADDRESS.search(address)
            or domain.endswith("mail.openonion.ai") or re.match(r"(?:student|students|ad)\.", domain)
            or re.fullmatch(r"[a-z]?\d{6,}", local)):
        return ""
    return domain


def company_from_domain(notebook, record: str, text: str, rows: list[dict]) -> tuple[str, dict]:
    """`Company: Unknown` takes the organisation page whose Domains hold the person's own mail domain (#2349).

    28 of 53 unknown companies on a real notebook wrote from a domain it had a
    page for. Only the address they write from now counts: falling back to older
    domains named UNSW for Ziming, graduated and writing from Hotmail, and for
    Sam, writing from his own company; seven students got their university as
    employer (contacts audit C1-C3). A page still titled by its domain is the
    map's stub: its name is not known yet. Returns the page and what was filled.
    """
    match = re.search(r'^- Company: (.*)$', text, re.M)
    if not record.startswith('people/') or not match or not match.group(1).casefold().startswith('unknown'):
        return text, {}
    newest = next((row for row in rows if row['field'] == 'Email'), None)
    domain = _employer_domain(newest['value']) if newest else ''
    for org, title, domains in _named_orgs(notebook) if domain else []:
        if any(domain == known or domain.endswith('.' + known) for known in domains):
            text, number = facts._cite(text, newest)
            match = re.search(r'^- Company: (.*)$', text, re.M)
            filled = {'company': title, 'domain': domain, 'source': newest['source']}
            return text[:match.start()] + f'- Company: [{title}](../{org}) [{number}]' + text[match.end():], filled
    return text, {}


# A quotation mark is a promise that these are the speaker's words. Decision
# 076 asks pages to quote rather than retell; without this check a model can
# paraphrase inside “…” and the page looks more trustworthy than before.
QUOTE = re.compile(r'“([^”\n]{4,})”')
FOLD = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' ',
                      '，': ',', '。': '.', '：': ':', '；': ';', '！': '!', '？': '?', '（': '(', '）': ')'})


def _plain(text: str) -> str:
    """Compare words, not layout: mail wraps lines and a page joins them."""
    text = re.sub(r'(?m)^[ \t]*>+', '', text)   # a reply's quoted lines
    text = re.sub(r'\*\*|__|\\(?=[^\s\w])', '', text.translate(FOLD))
    return re.sub(r'\s+', '', text).casefold()


def _quoted_in(quote: str, original: str) -> bool:
    """Each part between ellipses appears, in order, in the original."""
    # “Best.” and “sounds great,”: punctuation the page put inside the marks,
    # and a link the page added to a name, are not the speaker's.
    quote = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', quote).rstrip(' ,.;:!?，。；：！？')
    at = 0
    for part in filter(None, (_plain(part) for part in re.split(r'…|\.\.\.', quote))):
        at = original.find(part, at)
        if at < 0:
            return False
        at += len(part)
    return True


def cited_texts(root: Path, text: str, items: list[dict]) -> dict[str, tuple[str, bool]]:
    """Source id -> (the original's text, whether that text is complete)."""
    from .reader_model import SOURCE, cited_context
    ids = {source for _, source in SOURCE.findall(text.partition('\n## Sources\n')[2])}
    found = {i['source']: (i['text'], True) for i in items
             if i.get('source') in ids and isinstance(i.get('text'), str) and i['text'].strip()}
    for source, context in cited_context(root, [{'text': text}]).items():
        if source not in found and context.get('excerpt'):
            # A name is quoted from the From line as often as from the body.
            header = ' '.join(str(v) for v in (context.get('sender'), context.get('subject'),
                                               context.get('participants')) if v)
            found[source] = (header + '\n' + context['excerpt'], not context.get('truncated'))
    return found


def misquoted(root: Path, record: str, text: str, items: list[dict]) -> list[str]:
    """Quotes that are not, word for word, in any source their line cites.

    Only a quote whose cited originals are all here and complete is judged;
    one resting on an unavailable or truncated original is left to the claim audit.
    """
    from .reader_model import SOURCE
    if not record.startswith(('people/', 'projects/', 'orgs/')):
        return []
    head, _, sources = prose(text).partition('\n## Sources\n')
    numbers = dict(SOURCE.findall('\n' + sources))
    originals = {source: (_plain(body), whole) for source, (body, whole) in cited_texts(root, text, items).items()}
    errors = []
    for line in head.splitlines():
        cited = [numbers[n] for n in CITATION.findall(line) if n in numbers]
        checkable = cited and all(originals.get(source, ('', False))[1] for source in cited)
        for quote in QUOTE.findall(line) if checkable else ():
            if not any(_quoted_in(quote, originals[source][0]) for source in cited):
                errors.append(f'Quote is not in its cited source: “{quote[:120]}”')
    return errors


def _claim_key(text: str) -> str:
    """A claim as the audit copies it: no citation markers, no links, no closing punctuation.

    Code links names after the audit reads the page: "[Sasha Ward](../people/…)"
    on the page was "Sasha Ward" in the finding (v193q1, 2026-10-15)."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', CITATION.sub('', text))
    return _plain(text).rstrip(',.;:!?，。；：！？')


def uncited_field(line: str) -> bool:
    """Identity field lines belong to the map and contact checks, not the prose audit."""
    # Vern Chan's own email became Unknown for lacking a citation (2026-10-16 trial).
    return any(line.strip().removeprefix('- ').startswith(label + ':') for label in facts.UNCITED)


def drop_claims(record: str, text: str, claims: list[str]) -> tuple[str, list[str]]:
    """Remove each sentence holding a refuted claim; return the claims no line holds.

    Only the sentence goes when its line says more: Hamish's History line also
    held his own reply, which was true. An UNCITED identity field stays;
    another contact field keeps its label and says Unknown.
    """
    # "Unknown" refuted is a gap to fill, not a line to drop: as a substring it
    # matched every Unknown on oo-api's page (2026-10-15).
    wanted = {claim: _claim_key(claim) for claim in claims
              if _claim_key(claim) and not re.fullmatch(r'(?:[^:]{1,40}:)?unknown', _claim_key(claim))}
    head, marker, tail = text.partition('\n## Sources\n')
    head, found = _drop_diagrams(head, wanted)
    kept = []
    for line in head.split('\n'):
        hits = [claim for claim, key in wanted.items() if key in _claim_key(line)]
        found.update(hits)
        if not hits or uncited_field(line):
            kept.append(line)
        elif CONTACT_LINE.match(line):
            kept.append(CONTACT_LINE.match(line).group(0) + ' Unknown')
        else:
            sentences = re.split(r'(?<=[.!?。])\s+', line)
            rest = [s for s in sentences if not any(wanted[c] in _claim_key(s) for c in hits)]
            if rest and len(rest) < len(sentences) and _claim_key(re.sub(r'^[-*\s]*(?:\d{4}-\d{2}-\d{2}:?)?\s*', '', ' '.join(rest))):
                kept.append(' '.join(rest))
    return _fill_emptied_sections('\n'.join(kept)) + marker + tail, [c for c in wanted if c not in found]


FENCE = re.compile(r'^```[^\n]*\n.*?^```[ \t]*$\n?', re.M | re.S)


def _drop_diagrams(head: str, wanted: dict[str, str]) -> tuple[str, set[str]]:
    """A refuted arrow drops its whole diagram: the audit refuted STR's collector -> Postgres
    flow, copied across two lines no single line held, and the page was refused (2026-10-15)."""
    found = set()

    def refuted(match):
        block = ' '.join(_claim_key(line) for line in match[0].splitlines())
        hits = {claim for claim, key in wanted.items()
                if ' '.join(_claim_key(line) for line in claim.splitlines()) in block}
        found.update(hits)
        return '' if hits else match[0]
    return FENCE.sub(refuted, head), found


SOURCE_LINE = re.compile(r'^([ \t]*- \[(\d+)\][ \t]+)([a-z][\w-]*:[^\s]+)(.*)$', re.M)


def source_dates(root: Path, text: str, items: list[dict], zone) -> dict[str, str]:
    """Each cited original's own date, in the notebook's timezone."""
    from .reader_model import cited_context
    from .source import timestamp
    stamps = {i['source']: i.get('timestamp') for i in items if i.get('source') and i.get('timestamp')}
    stamps.update({source: context['time'] for source, context in cited_context(root, [{'text': text}]).items()
                   if context.get('time')})
    return {source: timestamp(stamp).astimezone(zone).date().isoformat() for source, stamp in stamps.items()
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}T[^\s]*(?:Z|[+-]\d{2}:?\d{2})', str(stamp))}


def settle_sources(text: str, dates: dict[str, str]) -> str:
    """One number per source, dated by its original rather than by the writer.

    The audit found the same mail listed twice with two dates, and dates the
    model typed that matched no message; the date is code's to know.
    """
    head, marker, tail = text.partition('\n## Sources\n')
    if not marker:
        return text
    first, merge = {}, {}
    for _, number, source, _ in SOURCE_LINE.findall(tail):
        if source in first:
            merge[number] = first[source]
        else:
            first[source] = number

    def line(match):
        if match[2] in merge:
            return '\0'
        if match[3] in dates:
            return f'{match[1]}{match[3]} — {dates[match[3]]}'
        return match[0]

    tail = SOURCE_LINE.sub(line, tail).replace('\0\n', '').replace('\0', '')
    swap = lambda part: re.sub(r'\[(\d+)\](?!\()', lambda m: f'[{merge.get(m[1], m[1])}]', part)  # noqa: E731
    parts, last = [], 0
    for code in CODE.finditer(head):
        parts += [swap(head[last:code.start()]), code[0]]
        last = code.end()
    return ''.join(parts) + swap(head[last:]) + marker + tail


# A one-page maintenance turn rewrites the whole page, and deletes what it
# cannot re-verify from a batch about something else: projects/connectonion
# went 14,356 -> 4,132 -> (rewritten) 9,610 -> 3,112 -> 2,108 characters in
# two days (2026-10-13/14), each time accepted, because nothing it dropped was
# invalid -- only gone. A turn that keeps less than this share of a page's
# size or of its cited sources keeps the old page instead.
KEEP_SHARE = 0.6
# Below this a page is mostly placeholders and a rewrite is not a loss.
SHRINK_FLOOR = 1000


def _listed_sources(text: str) -> set[str]:
    return set(re.findall(r'(?m)^\s*- \[W?\d+\]\s*:?\s*(\S+)', text.partition('\n## Sources\n')[2]))


def quotes(text: str) -> set[str]:
    """Links may change layout without changing the words the page kept."""
    return set(QUOTE.findall(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", prose(text))))


def dropped(before: str, after: str) -> list[str]:
    """Name each loss so a resumed writer can restore it exactly."""
    return ([f'Dropped quote the page had: “{quote}”' for quote in sorted(quotes(before) - quotes(after))]
            + [f'Dropped source id the page had: {source}'
               for source in sorted(_listed_sources(before) - _listed_sources(after))])


def restore_dropped(before: str, after: str) -> str:
    """Put carried lines back in their sections, using the candidate's source numbers."""
    lost_quotes = quotes(before) - quotes(after)
    lost_sources = _listed_sources(before) - _listed_sources(after)
    sources = dict(re.findall(r'(?m)^\s*- \[(W?\d+)\]\s*:?\s*(\S+)',
                              before.partition('\n## Sources\n')[2]))
    section, seen = '', set()
    for line, visible in zip(before.splitlines(), prose(before).splitlines()):
        if visible.startswith('## '):
            section = visible[3:]
            continue
        if section == 'Sources' or line in seen:
            continue
        cited = {sources.get(number) for number in re.findall(r'\[(W?\d+)\](?!\()', visible)}
        if not (quotes(visible) & lost_quotes or cited & lost_sources):
            continue
        seen.add(line)
        restored, after = _restore_citations(line, after, before)
        if restored and restored not in after.splitlines():
            after = _insert_restored_line(after, section, restored)
    return after


def _shorter_version(text: str, line: str) -> str:
    """The candidate's cut-down copy of a restored line: mostly inside it, and citing nothing it does not.
    Inserted beside it, the 2026-10-20 trial page said its Who-they-are sentence twice."""
    cited = set(re.findall(r'\[(W?\d+)\]', line))
    return next((row for row in text.splitlines() if row.strip() and not row.startswith('#')
                 and set(re.findall(r'\[(W?\d+)\]', row)) <= cited
                 and _contained(row, line) >= 0.8), '')


def _contained(row: str, line: str) -> float:
    """How much of the shorter row is in the line."""
    blocks = difflib.SequenceMatcher(None, row, line, autojunk=False).get_matching_blocks()
    return sum(block.size for block in blocks) / len(row)


def _insert_restored_line(text: str, section: str, line: str) -> str:
    shorter = _shorter_version(text.partition('\n## Sources\n')[0], line)
    if shorter:
        return text.replace(shorter, line, 1)
    visible = prose(text)
    heading = re.search(r'^## ' + re.escape(section) + r'$', visible, re.M) if section else None
    following = re.search(r'^## ', visible[heading.end():], re.M) if heading else None
    sources = re.search(r'^## Sources$', visible, re.M)
    at = heading.end() + following.start() if following else len(text)
    if not heading:
        at = sources.start() if sources else len(text)
    return text[:at].rstrip('\n') + '\n' + line + '\n\n' + text[at:]


def enumeration_only(text: str) -> bool:
    """Only the map's source metadata, with no carried prose quotes."""
    return _listed_sources(text) == {'Enumeration'} and not QUOTE.search(prose(text))


def shrinkage(before: str, after: str) -> str:
    """Why a maintenance rewrite lost too much of the page to be promoted, or ''."""
    if len(before) < SHRINK_FLOOR:
        return ''
    if len(after) < len(before) * KEEP_SHARE:
        return f'Maintenance shrank the page from {len(before):,} to {len(after):,} characters; kept the old page'
    old = _listed_sources(before)
    kept = old & _listed_sources(after)
    if old and len(kept) < len(old) * KEEP_SHARE:
        return f'Maintenance kept {len(kept)} of the page\'s {len(old)} cited sources; kept the old page'
    return ''
