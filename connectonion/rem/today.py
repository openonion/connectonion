"""The owner's Today order, shared by the snapshot and the night's draft budget."""

import re
from calendar import monthrange
import sqlite3
from contextlib import closing, nullcontext
from datetime import date, timedelta

from . import census, threads
from .files import Notebook, read_json, state_path
from .service import notebook_today


MONTHS = 'jan feb mar apr may jun jul aug sep oct nov dec'.split()
WRITTEN_DATE = (r'\b(?:(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)'
                r'|(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\s+(\d{1,2}))(?:,?\s+(\d{4}))?\b')


def _valid_day(value):
    year, month, day = map(int, value.split('-'))
    return year > 0 and 1 <= month <= 12 and 1 <= day <= monthrange(year, month)[1]


def _dates(text, today):
    def written(match):
        day, a, b, other, year = match.groups()
        value = f'{year or today.year}-{MONTHS.index((a or b)[:3].lower()) + 1:02}-{int(day or other):02}'
        if not _valid_day(value):
            return match[0]
        if not year and (date.fromisoformat(value) - today).days > 30:
            value = str(today.year - 1) + value[4:]
        return value if _valid_day(value) else match[0]
    # Use the same unambiguous written dates as the page, before reading deadline words.
    normalized = re.sub(WRITTEN_DATE, written, text, flags=re.I)
    due = re.search(r'\b(?:due(?:\s+(?:on|is))?|deadline(?:\s+(?:on|is))?|by)\s*[:：]?\s*(\d{4}-\d{2}-\d{2})', normalized, re.I)
    due = due[1] if due and _valid_day(due[1]) else ''
    dated = re.sub(r'(?:open as of|last moved(?: on)?)\s+\d{4}-\d{2}-\d{2}', '', normalized, flags=re.I)
    after = lambda words: re.search(r'\b(?:' + words + r')\s*[:：]?\s*(\d{4}-\d{2}-\d{2})', normalized, re.I)
    moved, requested = after(r'last moved(?:\s+on)?'), after(r'since|requested(?:\s+on)?|asked(?:\s+on)?')
    days = [day for day in re.findall(census.DAY, dated) if _valid_day(day) and day != due and day <= today.isoformat()]
    moved = moved if moved and _valid_day(moved[1]) else None
    requested = requested if requested and _valid_day(requested[1]) else None
    return (moved[1] if moved else requested[1] if requested else max(days, default='')), due


def _owner_words(body):
    from .languages import own_words
    # Mail adapters may wrap the body in headers; cut these before quoted history.
    body = re.split(r'^\s*(?:-{2,}\s*(?:Email|Message) Body\s*-{2,}|邮件正文[:：])\s*$', body,
                    maxsplit=1, flags=re.I | re.M)[-1]
    body = own_words(body)
    body = re.split(r'^\s*(?:>|On\b[^\n]*\bwrote:|发件人[:：]|Sent from my\b|Get Outlook for\b)',
                    body, maxsplit=1, flags=re.I | re.M)[0]
    body = re.split(r'^\s*(?:--\s*|(?:thanks|thank you|best(?: regards)?|kind regards|regards|cheers|谢谢|此致)[,，!！]?\s*)$',
                    body, maxsplit=1, flags=re.I | re.M)[0]
    body = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', body)
    body = re.sub(r'<?(?:https?://|www\.)[^\s<>]+>?', '', body)
    body = re.sub(r'^\s*(?:hi|hello|dear)\s+[^\n,，]{1,60}[,，]\s*', '', body, count=1, flags=re.I)
    return ' '.join(body.split()).strip()


def _owner_quote(body):
    words = _owner_words(body)
    sentences = re.split(r'(?<=[.!?。！？])(?:\s+|(?=[\u4e00-\u9fff]))', words)
    quote = next((sentence for sentence in sentences if _future_commitment(sentence)), sentences[0])
    if len(quote) <= 90:
        return quote
    cut = quote[:90]
    # Latin words stay whole; unspaced Chinese still gets a bounded excerpt.
    if quote[89:91].isascii() and not quote[90].isspace() and ' ' in cut:
        cut = cut.rsplit(' ', 1)[0]
    return cut.rstrip(' ,;:') + '…'


def _future_commitment(words):
    # Only a first-person future commitment (or sentence-initial "Will send")
    # makes work pending. Ignore third-person "will", negatives and reporting cues;
    # mailbox history/signatures are removed before this rule reads the owner's words.
    return bool(re.search(r"(?<!said )(?<!says )(?<!wrote )\bI(?:['’]ll| will)\s+(?!(?:not|never)\b)\w+|"
                          r'(?:^|[.!?。！？,，]\s*)will\s+(?:send|review|watch|check|share|prepare|write|finish|follow up)\b|'
                          r'我(?:会(?!不)|(?:下周|下星期|明天|后天|稍后|之后|周[一二三四五六日天]))', words, re.I))


def _reply(root, sources, text, owner, db, direction):
    from .reader_model import _cited_row
    from .store_messages import archived_message
    mail = [sources.get(number, '') for number in census.CITATION.findall(text)
            if sources.get(number, '').partition(':')[0] in ('gmail', 'outlook')]
    if not mail:
        return {'state': 'task', 'last_word_yours': False, 'promise': text}
    result = {'state': 'unarchived', 'provider': mail[0].partition(':')[0], 'source': mail[0]}
    cited = [_cited_row(db, source) for source in mail] if db is not None else []
    cited_threads = sorted({row['thread'] for row in cited if row is not None})
    latest = db.execute('select * from messages where thread in (' + ','.join('?' for _ in cited_threads)
                        + ') order by time desc, id desc limit 1', cited_threads).fetchone() if cited_threads else None
    if latest is None:
        return result
    saved = archived_message(root, dict(latest)) or {}
    result.update(provider=latest['source'], thread=latest['thread'], source=latest['id'], since=(latest['time'] or '')[:10])
    if latest['sender'].casefold() in owner:
        body = saved.get('body') or ''
        return {**result, 'state': 'task' if _future_commitment(_owner_words(body)) else 'replied',
                'last_word_yours': True, 'promise': _owner_quote(body)}
    if isinstance(saved.get('body'), str):
        from .mail import _address, _addresses
        if _address(saved.get('reply_to') or saved.get('from', '')) and owner.intersection(
                _addresses(saved.get('to')) + _addresses(saved.get('cc'))):
            result['state'] = 'queued' if direction == 'mine' else 'waiting'
    return result


def _items(records, found, first):
    for record in records:
        entry = found.get(record['path'])
        if not entry or not census.listed(entry) or entry['category'] not in census.THREAD_KINDS:
            continue
        title = record.get('title') or record['text'].splitlines()[0].lstrip('# ')
        for text in census.threads(record['text']):
            if census.direction(text, first) != 'third':
                yield {**record, 'title': title}, text, census._thread_sources(record['text'])


def _source_day(source, db, contexts):
    from .reader_model import _cited_row
    row = _cited_row(db, source) if db is not None else None
    # Canonical metadata is independent of how many body excerpts fit in a reader.
    stamp = (row['time'] if row is not None else contexts.get(source, {}).get('time')) or ''
    return stamp[:10]


def _entries(root, records, today, contexts, states, db):
    from .store_messages import owner_addresses
    mapped = read_json(state_path(root, 'map.json'), {})
    owner = (mapped.get('owner') or {}).get('record')
    title = next((record['text'].splitlines()[0].lstrip('# ') for record in records if record['path'] == owner), '')
    first, addresses = (title.split() or [''])[0], owner_addresses(root)
    found = census.pages(root, records=records)
    rows = []
    for record, text, sources in _items(records, found, first):
        key = threads.done_key(record['path'], text)
        since, due = _dates(text, today)
        times = [_source_day(sources.get(n, ''), db, contexts) for n in census.CITATION.findall(text)]
        times = [day for day in times if day and _valid_day(day) and day <= today.isoformat()]
        returned = states.get(key, {}).get('returned_at')
        since = returned[:10] if returned else max(times, default='') or since
        direction = census.direction(text, first)
        quiet = bool(not returned and since and not due and (today - date.fromisoformat(since)).days > 60)
        rows.append({'key': key, 'keys': [key], 'record': record['path'], 'text': text, 'title': record['title'],
                     'dir': direction, 'since': since, 'due': due, 'quiet': quiet,
                     'closed': threads.blocked(root, key, states=states),
                     'reply': _reply(root, sources, text, addresses, db, direction), 'sources': sources})
    return _grouped(rows)


def _grouped(rows):
    rows.sort(key=lambda row: row['since'], reverse=True)
    rows.sort(key=lambda row: row['due'] or '9999')
    grouped = census._thread_groups([({'path': row['record']}, row['text'], row['sources']) for row in rows])
    lookup = {row['key']: row for row in rows}
    result = []
    for group in grouped:
        members = [lookup[threads.done_key(record['path'], text)] for record, text, _ in group]
        chosen = sorted(members, key=lambda row: (row['dir'] != 'plain', row['since'] or row['due'], len(row['text'])), reverse=True)[0]
        result.append({**chosen, 'keys': [row['key'] for row in members], 'closed': all(row['closed'] for row in members)})
    return result


def _recorded_names(record):
    title = record.get('title') or record['text'].splitlines()[0].lstrip('# ')
    aliases = re.findall(r'^\s*-?\s*(?:also known as|aka|别名)[:：]\s*(.*)$',
                         '\n'.join(record['text'].splitlines()[:40]), re.I | re.M)
    names = [title, *re.findall(r'\(([^()]*)\)', title),
             *(part for line in aliases for part in re.split(r'[,;、]', census.CITATION.sub('', line)))]
    return [census._obligation_words(re.sub(r'\s*\([^()]*\)$', '', name.strip().strip('`'))) for name in names]


def _named_elsewhere(row, records):
    if not row['record'].startswith('people/') or len(row['keys']) > 1:
        return False
    named = re.match(r'^(?:the user|user|you)\s+owes?\s+(.+)', row['text'].replace('**', ''), re.I)
    if not named:
        return False
    words = census._obligation_words(named[1])
    names = [(record['path'], _recorded_names(record))
             for record in records if record['path'].startswith('people/')]
    # Titles nominate a counterpart; aliases can make that identity ambiguous,
    # but an alias alone must never move an obligation onto another page.
    full = [variants[0] for _, variants in names if ' ' in variants[0] and words.startswith(variants[0] + ' ')]
    longest = max(map(len, full), default=0)
    nominated = {name for name in full if len(name) == longest} if full else {
        variants[0].split()[0] for _, variants in names if variants[0] and words.startswith(variants[0].split()[0] + ' ')}
    matches = [path for path, variants in names if any(
        (name if full else name.split()[0]) in nominated for name in variants if name)]
    return len(matches) == 1 and matches[0] != row['record']


def queue(root, *, records=None, contexts=None, states=None, as_of=None):
    """Visible deadline cards, visible morning cards, then the rest; no model or writes."""
    today = as_of or notebook_today(root)
    if records is None:
        book = Notebook(root)
        records = [{'path': path, 'text': book.read(path)} for path in book.list()]
    contexts = contexts or {}
    states = threads.listing(root) if states is None else states
    database = state_path(root, 'rem.db')
    with (closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) if database.is_file() else nullcontext(None)) as db:
        if db is not None:
            db.row_factory = sqlite3.Row
        rows = _entries(root, records, today, contexts, states, db)
    soon = (today + timedelta(days=3)).isoformat()
    due = [row for row in rows if not row['quiet'] and not row['closed'] and row['dir'] in ('mine', 'theirs')
           and (row['due'] <= soon if row['due'] else row['since'] == today.isoformat())]
    pages, morning = set(), []
    for row in rows:
        if row not in due and not row['quiet'] and not row['closed'] and row['dir'] == 'mine' and row['record'] not in pages and not _named_elsewhere(row, records):
            morning.append(row)
            pages.add(row['record'])
            if len(morning) == 3:
                break
    ordered = due[:5] + morning + due[5:] + [row for row in rows if row not in due and row not in morning]
    return [{key: value for key, value in row.items() if key != 'sources'} | {
        'rank': rank, 'section': 'today' if row in due else 'morning' if row in morning else ''}
        for rank, row in enumerate(ordered)]
