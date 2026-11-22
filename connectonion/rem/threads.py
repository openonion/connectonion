"""Owner thread decisions shared by the reader and both night-run paths."""
import hashlib
import platform
import re
import sqlite3
from contextlib import closing

from .files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from .service import now


def done_key(record, text):
    """Match reader.html doneKey, including its display shortening of long IDs."""
    return re.sub(r'\b([0-9a-f]{12})[0-9a-f]{28,}\b', r'\1…', record + '\n' + text, flags=re.I)


def _mail_versions(root, key):
    from .census import CITATION, _thread_sources
    from .reader_model import _cited_row
    record, _, text = key.partition('\n')
    book = Notebook(root)
    if not book.exists(record) or not state_path(root, 'rem.db').is_file():
        return {}
    sources = _thread_sources(book.read(record))
    found = {}
    with closing(sqlite3.connect(state_path(root, 'rem.db'))) as db:
        db.row_factory = sqlite3.Row
        for number in CITATION.findall(text):
            row = _cited_row(db, sources.get(number, ''))
            if row is not None:
                latest = db.execute('select id, time from messages where thread = ? order by time desc, id desc limit 1',
                                    (row['thread'],)).fetchone()
                if latest:
                    found[row['thread']] = dict(latest)
    return found


def observed_versions(root, records):
    """Latest cited versions from one read-only metadata scan, without rereading pages."""
    from .census import _thread_sources
    file = state_path(root, 'rem.db')
    if not file.is_file():
        return {}
    with closing(sqlite3.connect(file.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('select id, time, thread, source, body_path from messages')]
    by_id = {row['id']: row for row in rows}
    aliases, latest = {}, {}
    for row in rows:
        thread = row['thread']
        if thread not in latest or (row['time'] is not None, row['time'] or '', row['id']) > (latest[thread]['time'] is not None, latest[thread]['time'] or '', latest[thread]['id']):
            latest[thread] = row
        if row['source'] in ('gmail', 'outlook'):
            digest = hashlib.sha256(row['id'].removeprefix(row['source'] + ':').encode()).hexdigest()[:12]
            body = row['body_path']
            if body is None or body.endswith('.json') and any(body.startswith(f'mail/{folder}/{row["source"]}/{digest}') for folder in ('messages', 'observed')):
                aliases.setdefault(row['source'] + ':' + digest, []).append(row)
    sources = {source for record in records for source in _thread_sources(record['text']).values()}
    resolved = [by_id.get(source) or (aliases[source][0] if len(aliases.get(source, [])) == 1 else None)
                for source in sources]
    return {row['thread']: latest[row['thread']]['id'] for row in resolved if row and row['thread'] is not None}


def listing(root):
    found = read_json(state_path(root, 'threads.json'), {})
    found.update(_backfilled(root, found))
    found.update(_carried(root, found))
    for key, value in found.items():
        if value.get('moved_from'):
            continue  # its return was decided where it was carried
        # Done and put off come back when the other person writes again on the thread (#3174); ignored is the
        # owner saying he does not want it, so it stays closed (ignoring the sender stops their mail altogether).
        if value['state'] in ('done', 'skipped'):
            newer = newer_inbound(root, key, value)
            if newer:
                value.update(returned_at=max(row['time'] for row in newer), reason='new_mail', reopened_by=newer[-1])
            elif value['state'] == 'skipped' and put_off_over(value):
                value['returned_at'] = value['until']
    return found


# Mail that reopens a closed item (#3174): a new message on its thread from the counterpart. The owner's own
# reply, an auto-reply and a notification or newsletter answer nothing the owner owes, so they reopen nothing.
AUTO_SUBJECT = re.compile(r'^\s*(?:automatic reply|auto[- ]?reply|out of office|自动回复|自動回覆|不在办公室)', re.I)


def _inbound(row, owner):
    from .mail import AUTOMATED_SENDER
    sender = (row['sender'] or '').casefold()
    return bool(sender) and sender not in owner and not AUTOMATED_SENDER.search(sender) \
        and not AUTO_SUBJECT.search(row['subject'] or '')


def newer_inbound(root, key, value):
    """[{time, sender}] of counterpart messages on the item's cited threads newer than the mail it was closed on."""
    from .store_messages import owner_addresses
    record, _, text = key.partition('\n')
    book, file = Notebook(root), state_path(root, 'rem.db')
    if not book.exists(record) or not file.is_file():
        return []
    owner, found, versions = owner_addresses(root), [], value.get('versions', {})
    with closing(sqlite3.connect(file)) as db:
        db.row_factory = sqlite3.Row
        # Only the threads the item was closed on (their latest message then is in versions), as before #3174.
        for thread, seen in sorted(versions.items()):
            seen_time = (db.execute('select time from messages where id = ?', (seen,)).fetchone() or [None])[0]
            for row in db.execute('select id, time, sender, subject from messages where thread = ? order by time, id', (thread,)):
                if row['id'] == seen or not row['time'] or (seen_time and row['time'] <= seen_time):
                    continue
                if _inbound(row, owner):
                    found.append({'time': row['time'], 'sender': row['sender']})
    return sorted(found, key=lambda row: row['time'])


def _backfilled(root, found):
    """Sources for marks saved before #3098 recorded them (#3174), read from the line they closed: the same
    line if the page still has it, else the open line on that page citing the same mail threads, else the
    most similar open line. In memory only; `migrate_marks` writes the same answer at night."""
    from difflib import SequenceMatcher
    from .census import threads as open_lines
    book, out, pages = Notebook(root), {}, {}
    for key, value in found.items():
        record, _, text = key.partition('\n')
        if value.get('sources') or value['state'] not in ('done', 'ignored', 'skipped') or not book.exists(record):
            continue
        page = pages.setdefault(record, book.read(record))
        lines = {done_key(record, line): line for line in open_lines(page)}
        match = lines.get(key)
        if match is None:
            wanted = set(value.get('versions', {}))
            plain = lambda line: re.sub(r'\[W?\d+\]', '', line).strip()  # noqa: E731
            scored = []
            for line_key, line in lines.items():
                overlap = len(wanted & set(_mail_versions(root, line_key))) if wanted else 0
                similar = SequenceMatcher(None, plain(text), plain(line)).ratio()
                if overlap or similar >= 0.6:
                    scored.append((overlap, similar, line))
            match = max(scored)[2] if scored else None
        if match is not None:
            out[key] = {**value, 'sources': line_sources(page, match), 'backfilled': True}
        else:
            out[key] = {**value, 'unmatched': True}
    return out


def migrate_marks(root):
    """Write the backfilled sources into threads.json once (idempotent); the caller holds the writer lock.
    Returns {migrated, unmatched}. An unmatched mark is kept as it was and counted, never dropped."""
    found = read_json(state_path(root, 'threads.json'), {})
    filled = _backfilled(root, found)
    migrated = {key: {k: v for k, v in value.items() if k not in ('backfilled', 'unmatched')}
                for key, value in filled.items() if value.get('sources')}
    if migrated:
        write_json(state_path(root, 'threads.json'), {**found, **migrated})
    return {'migrated': len(migrated), 'unmatched': sum(1 for value in filled.values() if value.get('unmatched'))}


def unmatched_marks(root):
    """Closed items whose line the page no longer has in any form: counted in status."""
    return sum(1 for value in _backfilled(root, read_json(state_path(root, 'threads.json'), {})).values()
               if value.get('unmatched'))


def closed_on(root, record):
    """The items the owner closed on one page and that stay closed: [{state, at, line, sources}]."""
    out = []
    for key, value in listing(root).items():
        page, _, line = key.partition('\n')
        if page == record and value.get('state') in ('done', 'ignored', 'skipped') and not value.get('returned_at'):
            out.append({'state': value['state'], 'at': value.get('at', ''), 'line': line, 'sources': value.get('sources', [])})
    return out


CLOSED_WORDS = {'done': 'marked done', 'ignored': 'ignored', 'skipped': 'put off'}


def closed_note(root, record):
    """What a page writer is told about the items the owner closed on this page (#3174)."""
    items = closed_on(root, record)
    if not items:
        return ''
    lines = '\n'.join(f'- {CLOSED_WORDS[item["state"]]} by the owner on {item["at"][:10]}: {item["line"]}' for item in items)
    return ('The owner closed these items in the reader. Do not write any of them as open again. Move each one '
            'still under Open threads to History as "<date>: <what it was> — closed by you on <closed date>", '
            'or leave it where it is if it is already in History. Only a newer message from the other person on '
            'the same thread may reopen one, and then say what that message asked.\n' + lines)


def closed_errors(root, record, candidate):
    """A draft that writes a closed item back under Open threads, with no newer inbound mail, is refused."""
    from .census import threads as open_lines
    errors = []
    items = [item for item in closed_on(root, record) if item['sources']]
    for line in open_lines(candidate):
        cited = line_sources(candidate, line)
        for item in items:
            if cited and cited == item['sources']:
                errors.append(f'Closed by the owner on {item["at"][:10]} but written as open again: "{line[:160]}". '
                              'Move it to History as closed by you on that date.')
    return errors


def line_sources(page, text):
    """The source ids a page line cites, through the page's own Sources list: what the line rests on."""
    from .census import CITATION, _thread_sources
    sources = _thread_sources(page)
    return sorted({sources[number] for number in CITATION.findall(text) if number in sources})


def _carried(root, found):
    """Marks carried onto the night's rewording of the line they closed (#3098).

    A mark is keyed by its line's exact words, and the night rewrites pages ("open as of 9 Nov" becomes
    "open as of 17 Nov"), so the item came back as new. A mark that no longer finds its line follows it to the
    line on the same page that cites the same sources; it stays closed unless the thread has a newer message
    than the one it was closed on, and then it says so (reason "new_mail"). Nothing is written: the carried
    key exists only in what this returns, and a mark set on it later is a mark of its own."""
    from .census import threads as open_lines
    book, carried, pages = Notebook(root), {}, {}
    for key, value in found.items():
        record, _, text = key.partition('\n')
        if not value.get('sources') or value['state'] not in ('done', 'ignored', 'skipped') or not book.exists(record):
            continue
        page = pages.setdefault(record, book.read(record))
        lines = {done_key(record, line): line for line in open_lines(page)}
        if key in lines:
            continue
        for new_key, line in lines.items():
            if new_key in found or new_key in carried or line_sources(page, line) != value['sources']:
                continue
            moved = {**value, 'moved_from': key}
            newer = newer_inbound(root, new_key, value) if value['state'] != 'ignored' else []
            if newer:
                moved.update(returned_at=newer[-1]['time'], reason='new_mail', reopened_by=newer[-1])
            elif value['state'] == 'skipped' and put_off_over(value):
                moved['returned_at'] = value['until']
            carried[new_key] = moved
            break
    return carried


def put_off_over(value) -> bool:
    """A Not now with a date is over once that moment has passed (#3072); new mail still returns it sooner.

    The mark stays in threads.json as it was written: `at` is when it was put off and `until` when
    it comes back, so the card that returns can say both. Before this a skipped item had no date and
    came back only with new mail on its thread."""
    until = value.get('until')
    return bool(until) and _moment(until) <= now()


def _moment(text):
    from datetime import datetime, timezone
    moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def blocked(root, key, *, states=None):
    value = (listing(root) if states is None else states).get(key, {})
    return value.get('state') in ('done', 'skipped', 'ignored') and not value.get('returned_at')


class UnknownThread(RemError):
    """The mark names no thread of this notebook. Sent again it is refused again, so the Host answers
    400; its 409 is kept for a notebook that is only busy, which the reader waits out."""


def set_state(root, key, state, *, device=None, versions=None, keys=None, until=None):
    """Open removes the decision and restores its preserved draft, at any time.

    until: for skipped only, the ISO moment the item returns to Today (put_off_over)."""
    requested = list(dict.fromkeys([key, *(keys or [])]))
    # ignored closes like done; it is its own word so the owner's history says 已忽略, not 已完成.
    if (state not in ('done', 'skipped', 'ignored', 'open') or any(
            not isinstance(item, str) or '\n' not in item or len(item) > 32000
            or not Notebook(root).exists(item.partition('\n')[0]) for item in requested)):
        raise UnknownThread('Expected a notebook thread key and state done, skipped, ignored or open')
    with maintenance_lock(root):
        keys = list(dict.fromkeys(item for requested_key in requested for item in _matching_keys(root, requested_key)))
        stamp = now().isoformat()
        for item in keys:
            value = _set_state(root, item, state, device=device, versions=versions, at=stamp, keys=keys, until=until)
        from . import owner_today
        owner_today.record(root, 'mark', key=key, state=state, **({'until': until} if until else {}))
        return {**listing(root).get(key, value), 'keys': keys}


def _matching_keys(root, key):
    from .census import _thread_groups, _thread_items, pages
    book = Notebook(root)
    owner = (read_json(state_path(root, 'map.json'), {}).get('owner') or {}).get('record')
    title = book.read(owner).splitlines()[0].lstrip('# ') if owner and book.exists(owner) else ''
    items = _thread_items(book, pages(root), (title.split() or [''])[0])
    saved = read_json(state_path(root, 'threads.json'), {})
    previous = saved.get(key)
    linked = previous.get('keys', [key]) if previous else [key]
    for group in _thread_groups(items):
        keys = [done_key(record['path'], text) for record, text, sources in group]
        if key in keys:
            return list(dict.fromkeys([*keys, *linked]))
    return linked


def _set_state(root, key, state, *, device=None, versions=None, at=None, keys=None, until=None):
    from . import drafts
    found = read_json(state_path(root, 'threads.json'), {})
    found.pop(key, None)
    value = {'state': state, 'at': at or now().isoformat(), 'device': device or platform.node()}
    if state != 'open':
        if keys and len(keys) > 1:
            value['keys'] = keys
        if state == 'skipped' and until:
            value['until'] = _moment(until).isoformat()
        # What the line rests on, so the mark can follow the night's rewording of it (#3098).
        record, _, text = key.partition('\n')
        if Notebook(root).exists(record):
            value['sources'] = line_sources(Notebook(root).read(record), text)
        # The page names the mail it showed; a cited thread it could not place is held at the notebook's latest.
        value['versions'] = {**{thread: row['id'] for thread, row in _mail_versions(root, key).items()}, **(versions or {})}
        found[key] = value
    for row in drafts.candidates(root, refresh_index=False):
        if not any(done_key(item['record'], item['text']) == key for item in row['obligations']):
            continue
        saved = read_json(drafts.path(root, row['id']), {})
        if (saved.get('version') != row['version'] or saved.get('status') in ('sent', 'held')
                or state == 'skipped' and versions is not None and row['thread'] in versions and versions[row['thread']] != row['version']):
            continue
        if state != 'open':
            value['draft_id'] = row['id']
            value.setdefault('draft_statuses', {})[row['id']] = {
                'status': saved.get('status_before_skip', saved['status']), 'version': saved['version']}
        if state == 'skipped' and saved['status'] != 'skipped':
            saved['status_before_skip'] = saved['status']
        status = saved['status']
        if state == 'skipped':
            status = 'skipped'
        elif state == 'open' and status in ('skipped', 'discarded'):
            status = saved.pop('status_before_skip', drafts.prepared_status(saved))
        write_json(drafts.path(root, row['id']), {**saved, 'status': status})
    write_json(state_path(root, 'threads.json'), found)
    return value


# 忽略 on a Today row can also stop its sender (owner, 2026-11-13: «广告要忽略»). One dated address per line in
# the notebook's state, beside threads.json, so the owner can read the list and delete a line by hand.
IGNORED = 'ignored-senders.txt'
IGNORED_HEAD = ('# Senders ignored in the REM reader: their mail stays out of Today and gets no draft.\n'
                '# One per line: "2026-11-13 news@example.com", a bare address, or "Name <news@example.com>". Delete a line to see them again.')


def ignored_senders(root):
    """{address: day ignored, or '' for a hand-written line without one}, addresses casefolded."""
    from .files import EMAIL
    file = state_path(root, IGNORED)
    lines = file.read_text(encoding='utf-8').splitlines() if file.is_file() else []
    found = {}
    for line in lines:
        address = EMAIL.search(line) if not line.lstrip().startswith('#') else None
        if address:
            day = re.match(r'\s*(\d{4}-\d{2}-\d{2})\s', line)
            found[address[0].casefold()] = day[1] if day else ''
    return found


# 不是人 / 是人 (rc35 check: an assistant that writes from its company's domain led People). The owner's word on
# whether an address is a person outranks every rule, in the reader and at night (census.pages). One dated line per
# address beside ignored-senders.txt, readable and deletable by hand.
PERSON_MARKS = 'people-marks.txt'
PERSON_MARKS_HEAD = ("# Who is and is not a person in REM People: the owner's word, which every rule follows.\n"
                     '# One per line: "2026-11-20 not-person assistant@example.com" or "2026-11-20 person ana@example.com". Delete a line to undo.')


def person_marks(root):
    """{handle: 'person' or 'not-person'}: mail addresses and chat handles, casefolded; the last line wins."""
    from .files import person_handle
    file = state_path(root, PERSON_MARKS)
    found = {}
    for line in file.read_text(encoding='utf-8').splitlines() if file.is_file() else []:
        mark = re.match(r'\s*(?:\d{4}-\d{2}-\d{2}\s+)?(not-person|person)\s+(\S+)', line)
        # A mail address or a chat handle (a WeChat id): a WeChat-only contact can be 不是人 too (#3339).
        if mark and not line.lstrip().startswith('#') and person_handle(mark[2]):
            found[mark[2].casefold()] = mark[1]
    return found


def mark_person(root, address, *, person):
    """person True (是人), False (不是人), or None (undo: the rules decide again); the whole map comes back."""
    from .files import atomic_write
    from .service import notebook_today
    with maintenance_lock(root):
        file = state_path(root, PERSON_MARKS)
        kept = [line for line in (file.read_text(encoding='utf-8').splitlines() if file.is_file() else [])
                if not line.lstrip().startswith('#') and address.casefold() not in line.casefold().split()]
        if person is not None:
            kept.append(f"{notebook_today(root).isoformat()} {'person' if person else 'not-person'} {address.casefold()}")
        atomic_write(file, '\n'.join([PERSON_MARKS_HEAD, *kept]) + '\n')
    return person_marks(root)


def ignore_sender(root, address, *, ignored=True):
    """Add the sender with today's date, or remove it; the whole list comes back for the reader."""
    from .files import atomic_write
    from .service import notebook_today
    with maintenance_lock(root):
        found = ignored_senders(root)
        found.pop(address.casefold(), None)
        if ignored:
            found[address.casefold()] = notebook_today(root).isoformat()
        atomic_write(state_path(root, IGNORED), '\n'.join([IGNORED_HEAD, *(f'{day} {who}'.strip() for who, day in found.items())]) + '\n')
        return found
