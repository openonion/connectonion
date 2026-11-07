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


def _reply(root, sources, text, owner, db, direction):
    from .reader_model import _cited_row, _clip
    from .store_messages import archived_message
    for number in census.CITATION.findall(text):
        source = sources.get(number, '')
        provider = source.partition(':')[0]
        if provider not in ('gmail', 'outlook'):
            continue
        result = {'state': 'unarchived', 'provider': provider, 'source': source}
        cited = _cited_row(db, source) if db is not None else None
        if cited is None:
            return result
        latest = db.execute('select * from messages where thread = ? order by time desc, id desc limit 1', (cited['thread'],)).fetchone()
        if latest is None:
            return result
        saved = archived_message(root, dict(latest)) or {}
        result.update(thread=latest['thread'], source=latest['id'], since=(latest['time'] or '')[:10])
        if latest['sender'].casefold() in owner:
            from .languages import own_words
            return {**result, 'state': 'task', 'last_word_yours': True,
                    'promise': _clip(' '.join(own_words(saved.get('body') or '').split()) or text)}
        if isinstance(saved.get('body'), str):
            from .mail import _address, _addresses
            if _address(saved.get('reply_to') or saved.get('from', '')) and owner.intersection(
                    _addresses(saved.get('to')) + _addresses(saved.get('cc'))):
                result['state'] = 'queued' if direction == 'mine' else 'waiting'
        return result
    return {'state': 'task', 'last_word_yours': False, 'promise': text}


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


def _named_elsewhere(row, records):
    if not row['record'].startswith('people/') or len(row['keys']) > 1:
        return False
    named = re.match(r'^(?:the user|user|you)\s+owes?\s+(.+)', row['text'].replace('**', ''), re.I)
    if not named:
        return False
    words = census._obligation_words(named[1])
    names = [(record['path'], census._obligation_words(record.get('title') or record['text'].splitlines()[0].lstrip('# ')))
             for record in records if record['path'].startswith('people/')]
    full = [(path, name) for path, name in names if words.startswith(name + ' ')]
    if full:
        longest = max(len(name) for _, name in full)
        matches = [path for path, name in full if len(name) == longest]
    else:
        matches = [path for path, name in names if name and words.startswith(name.split()[0] + ' ')]
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
