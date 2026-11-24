"""Bounded archive evidence for prepared replies in the owner's reader."""

from contextlib import closing
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import sqlite3

from .files import KEY_SHAPES, Notebook, state_path
from .languages import own_words
from .mail import _address, _addresses
from .reader_model import CITATION, SOURCE, _cited_row, _level, _not_sources
from .store_messages import archived_message, has_message_index, owner_addresses


def _page_citations(path, text):
    from .project_pages import private
    if 'gmail:' not in text and 'outlook:' not in text:
        return ()
    sources = [(n, source) for n, source in SOURCE.findall(text) if source.startswith(('gmail:', 'outlook:'))]
    if not sources:
        return ()
    # Privacy labels may span several lines. A marked page cannot establish
    # that an unmarked piece of mail is suitable as an example.
    level = _level(text)
    if ((path.startswith('projects/') and private(path, text))
            or (path.startswith('orgs/') and '- Kind: personal' in text)):
        level = 'sensitive'
    cited = set(CITATION.findall(_not_sources(text)))
    return tuple((source.split()[0], level) for n, source in sources if level or n in cited)


@lru_cache(maxsize=8192)
def _file_citations(root, path, fingerprint):
    # Today omits sessions, notes and logs. Keep their references, never their text.
    return _page_citations(path, Notebook(root).read(path))


def _citation_levels(root, records, omitted):
    book = Notebook(root)
    levels = {}

    def collect(citations):
        for source, level in citations:
            previous = levels.get(source, '')
            levels[source] = 'sensitive' if 'sensitive' in (previous, level) else previous or level

    for record in records or ():
        collect(_page_citations(record['path'], record['text']))
    paths = book.list() if records is None else (p for category in omitted for p in book.list(category))
    for path in paths:
        stat = book.path(path).stat()
        collect(_file_citations(root, path, (stat.st_ino, stat.st_size, stat.st_ctime_ns, stat.st_mtime_ns)))
    return levels


def _source_level(levels, row, resolve):
    # Page citations use either the provider id or its 12-hex archive digest.
    provider, raw = row['id'].split(':', 1)
    short = provider + ':' + sha256(raw.encode()).hexdigest()[:12]
    marks = {levels[row['id']]} if row['id'] in levels else set()
    # A short id may collide or be an exact provider id itself. It can
    # restrict either message, but only authorizes its verified archive row.
    if short in levels and (levels[short] or resolve(short) == row['id']):
        marks.add(levels[short])
    return next((mark for mark in ('sensitive', 'personal', '') if mark in marks), None)


def _message(row, saved, level, limit, *, sample=False):
    body = saved['body'].partition('--- Email Body ---')
    words = (body[2] if body[1] else body[0]).strip()
    if sample:
        words = own_words(words).strip()

    def clean(text):
        return KEY_SHAPES.sub('[redacted]', text or '')

    words = clean(words)
    return {'sender': clean(_address(saved.get('from')))[:254], 'time': (row['time'] or '')[:64], 'subject': clean(saved.get('subject'))[:256],
            'excerpt': words[:limit], 'truncated': len(words) > limit, 'level': level}


def _writer_sources(root, db, draft, level_for, owners):
    row = db.execute('SELECT * FROM messages WHERE id = ? AND thread = ? AND source = ?',
                     (draft['version'], draft['thread'], draft['provider'])).fetchone()
    if row is None or not owners or (row['sender'] or '').casefold() in owners:
        return {}
    saved = archived_message(root, dict(row))
    if not saved or not isinstance(saved.get('body'), str):
        return {}
    sender = _address(saved.get('from'))
    if not sender or sender in owners or _address(saved.get('reply_to') or sender) != draft['to'].casefold():
        return {}
    # Unclassified originals can be revealed individually by their owner. A raw
    # archived message is always private in the reader's screen-sharing mode.
    level = level_for(row)
    if level is None or draft.get('private') or _level(str(saved)):
        level = 'sensitive'
    original = _message(row, saved, level or 'personal', 16384)
    return {'original': original, 'examples': _examples(root, db, draft['to'].casefold(), row['time'], level_for, owners)}


def _examples(root, db, recipient, before, level_for, owners):
    senders = ','.join('?' for _ in owners)
    candidates = db.execute(f"""SELECT * FROM messages WHERE source IN ('gmail', 'outlook')
                                AND sender IN ({senders}) AND time != '' AND time < ?
                                AND EXISTS (SELECT 1 FROM json_each(recipients) WHERE lower(value) = ?)
                                ORDER BY time DESC, id DESC LIMIT 48""", (*owners, before, recipient))
    examples = []
    for row in candidates:
        if level_for(row) != '':
            continue
        mail = archived_message(root, dict(row))
        if not mail or not isinstance(mail.get('body'), str) or _level(str(mail)) or KEY_SHAPES.search(str(mail)):
            continue
        if _address(mail.get('from')) not in owners or recipient not in _addresses(mail.get('to')):
            continue
        example = _message(row, mail, 'personal', 1200, sample=True)
        if example['excerpt']:
            examples.append(example)
        if len(examples) == 3:
            break
    return examples


def attach_writer_mail(root: Path, drafts, records=None, omitted=()):
    prepared = [draft for draft in drafts if draft['status'] == 'prepared']
    if not prepared:
        return
    owners = owner_addresses(root)
    file = state_path(root, 'rem.db')
    if not has_message_index(file):
        return
    with closing(sqlite3.connect(file.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        levels = _citation_levels(root, records, omitted)

        @lru_cache(maxsize=None)
        def resolve(source):
            row = _cited_row(db, source)
            return row['id'] if row else None

        def level_for(row):
            return _source_level(levels, row, resolve)

        for draft in prepared:
            draft['writer_mail'] = _writer_sources(root, db, draft, level_for, owners)
