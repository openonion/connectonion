"""One local, unsent reply per mail thread waiting on the notebook owner."""

import hashlib
import json
import re
from contextlib import closing
from urllib.parse import quote
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

from .files import Notebook, RemError, read_json, state_path, write_json
from .mail import _address, _addresses
from .service import mail_client, now
from . import threads
from ..skills_catalog import useful_skills_dir


CHANNELS = ('mail', 'lark', 'whatsapp')


def path(root, draft_id):
    if not re.fullmatch(r'[0-9a-f]{32}', draft_id):
        raise RemError('Invalid reply draft id')
    return state_path(root, f'drafts/{draft_id}.json')


def _waiting_sources(root, records=None):
    from .census import CITATION, _thread_items, direction, pages
    owner = (read_json(state_path(root, 'map.json'), {}).get('owner') or {}).get('record')
    book = Notebook(root)
    title = book.read(owner).splitlines()[0].lstrip('# ') if owner and book.exists(owner) else ''
    first = (title.split() or [''])[0]
    found = {}
    if records is None:
        items = _thread_items(book, pages(root), first)
    else:
        from .census import _thread_sources, threads
        items = [(record, text, _thread_sources(record['text'])) for record in records
                 if record['category'] in ('people', 'orgs', 'projects')
                 and not (record.get('needs_review') or record.get('service'))
                 for text in threads(record['text'])]
    for record, text, sources in items:
        if direction(text, first) != 'mine':
            continue
        for number in CITATION.findall(text):
            source = sources.get(number, '')
            if source.startswith(('gmail:', 'outlook:')):
                found.setdefault(source, []).append({'record': record['path'], 'text': text})
    return found


def candidates(root, *, refresh_index=True, records=None):
    """Resolve cited mail to its latest archived thread; a newer owner reply closes it."""
    from .store import refresh
    from .reader_model import _cited_row
    from .store_messages import archived_message, owner_addresses
    if refresh_index:
        refresh(root)
    if not state_path(root, 'rem.db').is_file():
        return []
    owner, ignored = owner_addresses(root), threads.ignored_senders(root)
    found = {}
    with closing(sqlite3.connect(state_path(root, 'rem.db'))) as db:
        db.row_factory = sqlite3.Row
        for source, obligations in _waiting_sources(root, records).items():
            cited = _cited_row(db, source)
            if cited is None:
                continue
            thread = cited['thread']
            messages = [dict(row) for row in db.execute(
                'select * from messages where thread = ? order by time desc, id desc limit 12', (thread,))]
            if not messages or messages[0]['sender'].casefold() in owner:
                continue
            latest = messages[0]
            saved = archived_message(root, latest)
            if not saved or not isinstance(saved.get('body'), str):
                continue
            sender = _address(saved.get('reply_to') or saved.get('from', ''))
            mailbox = next((a for a in _addresses(saved.get('to')) + _addresses(saved.get('cc')) if a.casefold() in owner), '')
            # The owner ignored this sender from Today: the night writes them nothing either.
            if not sender or not mailbox or {sender.casefold(), _address(saved.get('from', '')).casefold()} & set(ignored):
                continue
            draft_id = hashlib.sha256(thread.encode()).hexdigest()[:32]
            cc = sorted(set(_addresses(saved.get('to')) + _addresses(saved.get('cc'))) - owner - {sender})
            material = [{'source': row['id'], 'message': archived_message(root, row)} for row in reversed(messages)]
            entry = found.setdefault(draft_id, {
                'id': draft_id, 'thread': thread, 'provider': latest['source'], 'from': mailbox,
                'to': sender, 'cc': ','.join(cc), 'subject': 'Re: ' + re.sub(r'^(?:Re:\s*)+', '', saved.get('subject', ''), flags=re.I),
                'in_reply_to': latest['id'].partition(':')[2], 'version': latest['id'],
                'time': latest['time'], 'material': material, 'obligations': []})
            entry['obligations'].extend(obligations)
            entry['private'] = entry.get('private', False) or bool(re.search(
                r'[\[［](?:personal|sensitive)[\]］]', json.dumps([material, obligations], ensure_ascii=False), re.I))
    return sorted(found.values(), key=lambda row: row['time'], reverse=True)


def queue(root):
    rows = candidates(root)
    states = threads.listing(root)
    from .today import queue as today_queue
    ranks = {key: entry['rank'] for entry in today_queue(root, states=states) for key in entry['keys']}
    pending = [row for row in rows if not closed(root, row, states=states)
               and read_json(path(root, row['id']), {}).get('version') != row['version']]
    return sorted(pending, key=lambda row: min((ranks.get(threads.done_key(item['record'], item['text']), float('inf'))
                                             for item in row['obligations']), default=float('inf')))


def closed(root, row, *, states=None):
    states = threads.listing(root) if states is None else states
    return bool(row['obligations']) and all(threads.blocked(root, threads.done_key(item['record'], item['text']), states=states)
                                            for item in row['obligations'])


def listing(root, *, include_pending=False, records=None):
    found = []
    for row in candidates(root, refresh_index=False, **({'records': records} if records is not None else {})):
        saved = read_json(path(root, row['id']), {})
        if saved.get('version') == row['version'] and (include_pending or saved.get('status') not in ('discarded', 'skipped')):
            found.append({**saved, "private": saved.get("private", False) or row["private"]})
        elif include_pending:
            found.append({key: row[key] for key in ('id', 'thread', 'provider', 'private', 'version')} |
                         {'status': 'skipped' if saved.get('version') == row['version'] else 'pending'})
    return found


def owner_skill(name):
    """The owner's own skill of this name, from the coding agents' skill folders, if they have one."""
    for folder in ('.claude', '.codex', '.cursor', '.co'):
        candidate = Path.home() / folder / 'skills' / name / 'SKILL.md'
        if candidate.is_file():
            return candidate
    return None


def _page_excerpt(root, record, sections, limit=1800):
    """The sections of a page a writer needs, trimmed; the page path is kept for `co rem show`."""
    book = Notebook(root)
    if not record or not book.exists(record):
        return {}
    text = book.read(record)
    found = {'page': record, 'name': text.splitlines()[0].lstrip('# ').strip()}
    for title in sections:
        match = re.search(r'^## ' + re.escape(title) + r'\n(.*?)(?=^## |\Z)', text, re.S | re.M)
        if match:
            found[title.lower().replace(' ', '_')] = match.group(1).strip()[:limit]
            if title == 'Facts':
                permission = re.search(r'^- Direct send: (partner|close|none)\b', match.group(1), re.M)
                found['direct_send'] = permission.group(1) if permission else 'none'
    return found


def _identities(root, row):
    mapped = read_json(state_path(root, 'map.json'), {})
    owner = (mapped.get('owner') or {}).get('record')
    person = next((item['record'] for item in row.get('obligations', []) if item.get('record') and item['record'] != owner), None)
    identities = {'owner': _page_excerpt(root, owner, ('Facts', 'Who they are', 'How they communicate'), 1200),
                  'person': _page_excerpt(root, person, ('Facts', 'Who they are', 'Our relationship', 'How they communicate',
                                                         'Open threads', 'How the user writes to them'))}
    identities['person'].setdefault('direct_send', 'none')
    addresses = [address.casefold() for item in mapped.get('people', []) if item.get('record') == person
                 for address in [item.get('address', ''), *item.get('addresses', [])]]
    addresses += [address for line in re.findall(r'^- Email: (.+)$', identities['person'].get('facts', ''), re.M)
                  for address in _addresses(line)]
    if row.get('to', '').casefold() not in addresses:
        identities['person']['direct_send'] = 'none'
    return identities


def _owner_samples(root, row):
    """Recent archived mail to this recipient, in the thread's language first, unmodified."""
    from .languages import language_of, own_words
    from .store_messages import archived_message, owner_addresses
    owner = owner_addresses(root)
    database = state_path(root, 'rem.db')
    if not owner or not row.get('to') or not database.is_file():
        return []
    latest = next((item.get('message') or {} for item in reversed(row.get('material', [])) if item.get('message')), {})
    language = language_of(own_words(latest.get('body', '')))
    matching, other = [], []
    with closing(sqlite3.connect(f'file:{database}?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        messages = db.execute('select * from messages where source in (\'gmail\', \'outlook\') '
                              'and lower(sender) in (' + ','.join('?' for _ in owner) + ') '
                              'and exists (select 1 from json_each(messages.recipients) where lower(value) = ?) '
                              'order by time desc, id desc', (*sorted(owner), row['to'].casefold()))
        for message in messages:
            saved = archived_message(root, dict(message))
            if not saved or not isinstance(saved.get('body'), str) or not saved['body'].strip():
                continue
            target = matching if language and language_of(own_words(saved['body'])) == language else other
            if len(target) < 3:
                target.append({'source': message['id'], 'message': saved})
            if len(matching) == 3 or (not language and len(other) == 3):
                break
    return (matching + other)[:3]


def prepare(root, row, config, *, directory):
    from .languages import owner_languages
    from .runner import today_note
    material = directory / 'reply-material.json'
    identities = _identities(root, row)
    if not (directory / 'verdict.json').exists():
        # The owner's tier on the People page is the permission; the writer may only lower it.
        tier = identities['person']['direct_send']
        write_json(directory / 'verdict.json', {'kind': 'reply', 'send': 'now' if tier in ('partner', 'close') else 'owner'})
    write_json(material, {**row, 'channel': row.get('channel', 'mail'), **identities, 'owner_samples': _owner_samples(root, row)})
    candidate = directory / 'candidate.json'
    language = next(iter(owner_languages(root)['languages']), config['language'])
    skill = useful_skills_dir() / 'rem-reply-draft' / 'SKILL.md'
    voice = owner_skill('email-writing')
    prompt = (f'Read {skill} and follow it. '
              + (f'The owner\'s own writing skill is {voice}; it comes first for voice and wording. ' if voice else '')
              + f'The material is {material}; the owner\'s language is {language}. '
              + today_note(root) + ' '
              f'Write JSON to {candidate} as the skill says. Never send or contact anyone. Reply DONE.')
    return {'row': row, 'person': identities['person'], 'verdict': read_json(directory / 'verdict.json', {}),
            'prompt': prompt, 'candidate': str(candidate), 'input_paths': [str(material)]}


def _check_send(task, value, body, needs_owner):
    send = value.get('send', 'owner')
    fix = f'Fix {task.get("candidate", "candidate.json")}.'
    if send not in ('now', 'owner'):
        raise RemError(f'Reply draft send must be now or owner. {fix}')
    if send == 'now':
        if task.get('verdict', {}).get('send') != 'now':
            raise RemError(f'The writer cannot raise send to now. {fix}')
        if '【需要你' in body:
            raise RemError(f'Direct send body must have no owner slot. {fix}')
        if needs_owner:
            raise RemError(f'Direct send needs_owner must be empty. {fix}')
        if task.get('person', {}).get('direct_send') not in ('partner', 'close'):
            raise RemError(f'Direct send requires person.direct_send partner or close. {fix}')
    return send


BRACKETED = re.compile(r'\[[^\]]*\]|［[^］]*］|【[^】]*】')
OWNER_SLOT = re.compile(r'【需要你：\S(?:[^【】\n]*\S)? — \S(?:[^【】\n]*\S)?】')


def has_slots(body):
    return bool(re.search(r'[\[\]［］【】]', body))


def check(task, output):
    value = json.loads(output['result'])
    allowed = {item['source'] for item in task['row']['material']}
    if not isinstance(value, dict):
        raise RemError('Reply draft needs a JSON object')
    verdict, body = value.get('verdict', 'reply'), value.get('body', '')
    if verdict not in ('reply', 'no_reply'):
        raise RemError('Reply draft verdict must be reply or no_reply')
    if (not isinstance(body, str) or (verdict != 'no_reply' and not body.strip())
            or not isinstance(value.get('sources'), list) or not value['sources']
            or any(not isinstance(source, str) or source not in allowed for source in value['sources'])):
        raise RemError('Reply draft needs a body and cited sources from its thread')
    if (has_slots(BRACKETED.sub('', body))
            or any(not OWNER_SLOT.fullmatch(slot) for slot in BRACKETED.findall(body))):
        raise RemError(f'Reply draft slot must use 【需要你：<what> — <by when or date not agreed>】. Fix {task.get("candidate", "candidate.json")}.')
    needs_owner = value.get('needs_owner', [])
    if not isinstance(needs_owner, list) or any(not isinstance(slot, str) for slot in needs_owner):
        raise RemError('Reply draft needs_owner must be a list of slots')
    send = _check_send(task, value, body, needs_owner)
    notes = {key: value[key].strip() for key in ('gist', 'why') if isinstance(value.get(key), str) and value[key].strip()}
    return {key: val for key, val in task['row'].items() if key not in ('material', 'obligations')} | {
        'body': body, 'sources': value['sources'], 'verdict': verdict, 'send': send, 'needs_owner': needs_owner} | notes


def prepared_status(draft):
    return 'no_reply' if draft.get('verdict') == 'no_reply' else 'prepared'


def promote(root, draft):
    saved = read_json(path(root, draft['id']), {})
    if saved.get('version') == draft.get('version'):
        _not_held(saved)
    write_json(path(root, draft['id']), {**draft, 'status': prepared_status(draft), 'prepared_at': now().isoformat()})


def _current(root, draft_id, refresh_index=True):
    saved = read_json(path(root, draft_id), {})
    row = next((row for row in candidates(root, refresh_index=refresh_index) if row['id'] == draft_id), None)
    if not row or saved.get('version') != row['version']:
        raise RemError('This reply draft is no longer current; the next round will prepare a fresh one')
    return saved


def _not_held(saved):
    if saved.get('status') == 'held':
        raise RemError('This reply is held; Undo it before changing it')


def open_provider(root, draft_id):
    """Create only an unsent provider draft, and reuse it on subsequent clicks."""
    from .files import maintenance_lock
    with maintenance_lock(root):
        saved = _current(root, draft_id)
        _not_held(saved)
        if saved.get('status') == 'no_reply' or saved.get('verdict') == 'no_reply':
            raise RemError('This thread needs no reply')
        if not saved['body'].strip():
            raise RemError('The reply body is empty')
        if saved.get('provider_draft'):
            return saved['provider_draft']
        client = mail_client(saved['provider'])
        if saved['provider'] == 'gmail':
            result = client.create_draft(saved['to'], saved['subject'], saved['body'], cc=saved['cc'] or None,
                                         in_reply_to=saved['in_reply_to'])
            link = 'https://mail.google.com/mail/u/' + quote(saved['from'], safe='') + '/#drafts'
        else:
            result = client.reply(saved['in_reply_to'], saved['body'], cc=saved['cc'] or None, draft=True)
            link = result.get('web_link') if isinstance(result, dict) else result.rsplit('Open it in Outlook: ', 1)[-1]
        receipt = {'url': link}
        write_json(path(root, draft_id), {**saved, 'provider_draft': receipt})
        return receipt


def _write_now(root, row, channel):
    """One drafting turn for one thread, the same path the night turn takes."""
    from . import runner
    from .config import read_config
    from .inquiry import stage_config
    config = stage_config(root, read_config(root), 'reply-draft')
    state_path(root, 'tasks').mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=state_path(root, 'tasks')) as directory:
        task = prepare(root, {**row, 'channel': channel}, config, directory=Path(directory))
        runner.run_task(Path(directory), task['prompt'], config, 'reply-draft')
        plan = check(task, {'result': Path(task['candidate']).read_text(encoding='utf-8')})
    promote(root, {**plan, 'channel': channel, 'phone': _phone(_identities(root, row)['person'])})
    return read_json(path(root, row['id']), {})


# The owner's clicks below run while a scheduled REM round may hold the
# notebook lock for an hour.  They take no lock: they read the existing index
# (never rebuild it) and write only their own draft file, atomically.
def redraft(root, draft_id, channel):
    """Write the same reply for another channel: a chat message is not a mail body."""
    if channel not in CHANNELS:
        raise RemError(f'Unknown channel {channel!r}; expected one of {", ".join(CHANNELS)}')
    _not_held(_current(root, draft_id, refresh_index=False))
    row = next(row for row in candidates(root, refresh_index=False) if row['id'] == draft_id)
    return _write_now(root, row, channel)


def prepare_now(root, provider, thread):
    """Draft one waiting reply on the owner's click, now, instead of waiting for the night."""
    row = next((row for row in candidates(root, refresh_index=False)
                if row['provider'] == provider and row['thread'] == thread), None)
    if row is None:
        raise RemError('This thread cannot be drafted yet: its latest message is not archived, or the last word was yours')
    _not_held(read_json(path(root, row['id']), {}))
    return _write_now(root, row, 'mail')


def _phone(person):
    match = re.search(r'^- Phone: \+?([\d][\d ()-]{6,})', person.get('facts', ''), re.M)
    return re.sub(r'\D', '', match.group(1)) if match else ''


def _lark_open_id(found):
    if isinstance(found, dict):
        if isinstance(found.get('open_id'), str):
            return found['open_id']
        return next((hit for value in found.values() if (hit := _lark_open_id(value))), '')
    if isinstance(found, list):
        return next((hit for value in found if (hit := _lark_open_id(value))), '')
    return ''


def _cli(command):
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        raise RemError((completed.stderr or completed.stdout).strip()[:400] or f'{command[0]} failed')
    return json.loads(completed.stdout or '{}')


def _send_chat(saved, text):
    if saved['channel'] == 'lark':
        open_id = _lark_open_id(_cli(['lark-cli', 'contact', '+search-user', '--as', 'user', '--keyword', saved['to'], '--json']))
        if not open_id:
            raise RemError(f'{saved["to"]} was not found in Lark')
        return _cli(['lark-cli', 'im', '+messages-send', '--as', 'user', '--user-id', open_id, '--text', text, '--json'])
    if not saved.get('phone'):
        raise RemError('The notebook has no phone number for this person, so there is no WhatsApp chat to send to')
    return _cli(['co', 'whatsapp', '--json', 'send', saved['phone'] + '@s.whatsapp.net', text])


def send(root, draft_id, body=None):
    """Send the prepared reply in its own thread; the click in the reader is the approval.
    An edited body replaces the prepared one and is kept with the receipt."""
    from .files import maintenance_lock
    if body is not None and not body.strip():
        raise RemError('The reply body is empty')
    with maintenance_lock(root):
        return _send_locked(root, draft_id, body)


def _send_locked(root, draft_id, body=None, *, held=False):
    saved = _current(root, draft_id)
    if saved.get('status') == 'held' and not held:
        raise RemError('This reply is held; Undo it before sending again')
    if saved.get('status') in ('skipped', 'discarded'):
        raise RemError('Restore this skipped reply before sending')
    if saved.get('status') == 'no_reply' or saved.get('verdict') == 'no_reply':
        raise RemError('This thread needs no reply')
    if saved.get('status') == 'sent':
        raise RemError('This reply was already sent; nothing was sent again')
    text = body if body is not None else saved['body']
    if not text.strip():
        raise RemError('The reply body is empty')
    if has_slots(text):
        raise RemError('Fill the marked part first / 先填好标出的部分')
    if saved.get('channel', 'mail') != 'mail':
        receipt = _send_chat(saved, text)
    else:
        client = mail_client(saved['provider'])
        receipt = (client.reply(saved['in_reply_to'], text, cc=saved['cc'] or None) if saved['provider'] == 'outlook'
                   else client.reply(saved['in_reply_to'], text))
    write_json(path(root, draft_id), {**saved, 'body': text, 'status': 'sent', 'sent_at': now().isoformat(), 'sent_receipt': receipt})
    return {'status': 'sent'}


def discard(root, draft_id):
    from .files import maintenance_lock
    with maintenance_lock(root):
        saved = _current(root, draft_id)
        _not_held(saved)
        if saved.get('status') == 'sent':
            raise RemError('This reply was already sent')
        row = next(row for row in candidates(root, refresh_index=False) if row['id'] == draft_id)
        keys = [threads.done_key(item['record'], item['text']) for item in row['obligations']]
        stamp = now().isoformat()
        for key in keys:
            threads._set_state(root, key, 'skipped', at=stamp, keys=keys)
        return {'status': 'skipped'}
