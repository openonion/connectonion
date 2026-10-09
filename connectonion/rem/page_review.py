"""Normalize page shapes and check a candidate before replacing an existing page."""

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
    # ASCII or box-drawing: a real candidate drew its flow with │ and ▼ and the
    # whole page was refused for it.
    if any(re.search(r'->|--|\||^[ \t]*v[ \t]*$|[│┃▼↓→⟶➜─]', block[2], re.M) for block in blocks):
        return []
    return ['Project Overview requires a closed fenced ASCII flow, or an explicit Unknown statement']


SOURCE_ID = re.compile(r'\b(?:codex|claude-code|gmail|outlook|whatsapp|email|reflection|review)'
                       r'(?:-summary)?:[\w.:+-]+')


def _carried_over(value: str, old_sources: str) -> bool:
    ids = [match.rstrip('.,;') for match in SOURCE_ID.findall(value)]
    return bool(ids) and all(source in old_sources for source in ids)


def restore_runner_fields(record: str, candidate: str, original: str) -> str:
    """Put back the lines the runner owns, instead of refusing the page for them.

    The Investigation status line and a project's mapped Sessions / First seen /
    Last seen are written by code that knows their true values. A real
    maintenance pass rewrote them and the whole page was refused; the rest of
    the page was sound. Restoring them is exact, so nothing is guessed.
    """
    if not original:
        return candidate
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


RUN_SOURCES = {"projects/": ("investigation:coverage", "investigation:project-scope", "investigation:project-inventory",
                             "investigation:project-repositories"),
               # The same refusal on a skill page (title-refine, 2026-10-08).
               "skills/": ("skill-runs:", "investigation:page")}
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
        return text
    # "[1, 2]" is two citations; read as neither, both were reported unused
    # and the page was refused. A link's [text](url) is left alone.
    head = re.sub(r'\[(\d+(?:[ \t]*,[ \t]*\d+)+)\](?!\()',
                  lambda m: ''.join(f'[{n.strip()}]' for n in m.group(1).split(',')), head)
    after = re.search(r'^(?:## |Investigation:)', tail, re.M)
    sources, rest = (tail[:after.start()], tail[after.start():]) if after else (tail, '')
    sources = re.sub(r'(?m)^([ \t]*)(\d+)\.[ \t]+', r'\1- [\2] ', sources)
    return head + marker + sources + rest


IDENTITY_LINE = re.compile(r'^(- (?:Email|Phone|Handles|Also known as): )(.*)$', re.M)


def _identity_key(value: str) -> str:
    """A phone compares by its last nine digits (+61 435 ... is 0435 ...); anything else by case-folded text."""
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


# What an investigation hands the model about itself, not about the subject.
# A page that cites only these was written from nothing (#1974).
CONTEXT_SOURCES = ("investigation:page", "investigation:coverage", "investigation:quick-scope",
                   "investigation:project-inventory", "investigation:project-repositories",
                   "investigation:original-evidence",
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


def _identifiable(value: str, *, known, record, original, old_sources, items, pages) -> bool:
    if record.startswith('projects/') and value.strip().startswith(('file:', 'git:')):
        from .project_pages import live_source_snapshot
        source = re.split(r'\s+[—–]\s+', value.strip(), 1)[0]
        return value.strip() in old_sources or live_source_snapshot(original, source) is not None
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


def placeholder_errors(candidate: str) -> list[str]:
    """A page an investigation returns may not keep the map's placeholder (#2008).

    Project pages came back after 0.6-0.9M tokens with five and six sections
    still reading "Unknown — not investigated yet": the page said it had not
    been investigated right after it was. A section becomes what the material
    shows, or a bare `Unknown` when it shows nothing. Only for a page's own
    investigation: an upkeep pass that touched one line of a page is not asked
    to finish the rest.
    """
    content = prose(candidate).partition('\n## Sources\n')[0]
    parts = re.split(r'(?m)^## (.+)$', content)
    left = [parts[i].strip() for i in range(1, len(parts), 2)
            if i + 1 < len(parts) and PLACEHOLDER in parts[i + 1]]
    return ([f'Sections still say "{PLACEHOLDER}" after the investigation: {", ".join(left)}; '
             'write what the material shows, or a bare "Unknown"'] if left else [])


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


def history_errors(candidate: str, original: str) -> list[str]:
    """A History past 8 lines may not grow; one already past may come down in steps."""
    lines, before = len(_history(candidate)), len(_history(original))
    if lines <= HISTORY_LIMIT or lines <= before:
        return []
    return [f'History has {lines} lines (was {before}); keep at most {HISTORY_LIMIT} dated lines, one per thread '
            'with how it ended: fold the oldest into one line per year, and drop sends, reminders and newsletters']


def size_errors(candidate: str, original: str) -> list[str]:
    """A page over the limit may not grow; one already over may come down in steps."""
    if len(candidate) <= PAGE_LIMIT or len(candidate) <= len(original):
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
             owner: bool = False) -> list[str]:
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
    errors += [f'Section must occur once: {h}' for h in headings(record, owner) if counts[h] != 1]
    errors += [f'Duplicate section: {h}' for h, n in counts.items() if n > 1]
    if re.findall(r'^Investigation:.*$', body, re.M) != re.findall(r'^Investigation:.*$', original, re.M):
        errors.append('Investigation status belongs to the runner')
    content, _, sources = body.partition('\n## Sources\n')
    refs = set(re.findall(r'\[(W?\d+)\](?!\()', content))
    definitions = re.findall(r'^\s*(?:- )?\[(W?\d+)\]\s*:?(.*)$', sources, re.M)
    defined = Counter(key for key, _ in definitions)
    errors += [f'Missing or duplicate citation: {key}' for key in refs if defined[key] != 1]
    known = _known_sources(items)
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
        errors += _project_overview_errors(candidate)
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
                    pages=frozenset()) -> tuple[str, dict]:
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
    known = _known_sources(items)
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
