"""One deterministic, quiet morning note, claimed before external delivery."""

from datetime import date, datetime, timedelta
from pathlib import Path
import os
import re
import sys

from . import approvals, service
from .config import read_config
from .files import maintenance_lock, read_json, state_path, write_json


CHANNELS = ('telegram', 'lark', 'whatsapp', 'email')  # Email is the last choice.
# A note is due from 06:00 until 11:00 local. Later it is no longer a morning note: a
# sleeping laptop or schedule.times' own "17:00" slot would otherwise say 「昨夜」 at dusk.
OPENS, CLOSES = 6, 11
KEEP_DAYS = 14
# rem/problems.py verdict states whose explanation the owner can now read.
EXPLAINED = ('explained', 'needs_owner', 'fix_proposed')


def _local(config):
    return service.now().astimezone(service.notebook_zone(config))


def _markers(root):
    return read_json(state_path(root, 'morning.json'), {})


def _previous(saved, day):
    """The latest earlier claim. A missed date reported nothing, so it does not move the window."""
    earlier = [saved[date] for date in sorted(saved) if date < day and saved[date].get('status') != 'missed']
    return earlier[-1] if earlier else None


def _start(local, previous):
    # From the last note to now, so work after 06:00 and before the check is reported once.
    if previous and previous.get('checked_at'):
        return datetime.fromisoformat(previous['checked_at'])
    return local.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=1)


def _within(value, start, end):
    if not value:
        return False
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return moment.tzinfo is not None and start < moment <= end


def counts(root, start, end):
    night = read_json(state_path(root, 'night.json'), {}).get('items', {}).values()
    receipts = {}
    for path in state_path(root, 'drafts').glob('*.json'):
        draft = read_json(path, {})
        receipts[draft.get('id') or path.stem] = draft
    # night.json is a current projection and sent replies may have left it; the
    # draft receipts keep them. A draft is "waiting" only while it is still prepared.
    drafted = {row.get('draft_id') or str(index) for index, entry in enumerate(night)
               if (row := entry.get('outcome', {})).get('kind') == 'prepared'
               and _within(row.get('prepared_at'), start, end)}
    drafted |= {id for id, draft in receipts.items() if draft.get('status') in ('prepared', 'held', 'sent')
                and _within(draft.get('prepared_at'), start, end)}
    queue = read_json(state_path(root, 'approvals.json'), {}).values()
    tasks = [read_json(path, {}) for path in state_path(root, 'tasks').glob('do-*/receipt.json')]
    # rem/problems.py writes {problem key: receipt}; every save() bumps updated_at.
    problems = read_json(state_path(root, 'investigations/index.json'), {}).values()
    return {'sent': sum(row.get('kind') == 'reply' and row.get('by') == 'rem' and row.get('status') == 'sent'
                        and _within(row.get('release_at'), start, end) for row in queue),
            'drafted': sum(receipts.get(id, {}).get('status', 'prepared') == 'prepared' for id in drafted),
            'finished': sum(row.get('result') == 'completed' and _within(row.get('finished_at'), start, end)
                            for row in tasks),
            'explained': sum(row.get('state') in EXPLAINED and _within(row.get('updated_at'), start, end)
                             for row in problems)}


def actionable(root):
    """Only current, unblocked owner actions; held replies need no click."""
    return [row for row in approvals.outcomes(root) if not row.get('blocked')]


def today_link(root):
    from ..project import project_identity
    from .reader import LIVE_REM_URL, host_online
    # Only the default notebook is exposed by the Host's /rem route.
    if Path(root).resolve() == (Path.home() / '.co/rem').resolve():
        identity = project_identity()
        address = identity.get('address') if identity else None
        if address and host_online(address):
            return LIVE_REM_URL.format(address=address)
    return 'co rem open'


def _plain(value, limit):
    # Owner-facing words only: never an address, a record path or an ID.
    text = ' '.join(str(value or '').split())
    if '@' in text or '\\' in text or re.search(r'(^|\s)[~/]|\.md\b|\b[0-9a-f]{16,}\b', text):
        return ''
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _summary(c, zh):
    if zh:
        replies = [f"替你发出 {c['sent']} 封回复" if c['sent'] else '',
                   (f"另拟好 {c['drafted']} 封待你看" if c['sent'] else f"拟好 {c['drafted']} 封回复待你看") if c['drafted'] else '']
        work = [f"跑完 {c['finished']} 项任务" if c['finished'] else '', f"查清 {c['explained']} 个问题" if c['explained'] else '']
        return '昨夜：' + '；'.join('，'.join(filter(None, group)) for group in (replies, work) if any(group)) + '。'
    replies = [_plural(c['sent'], 'reply', 'replies') + ' sent for you' if c['sent'] else '',
               (f"{c['drafted']} more" if c['sent'] else _plural(c['drafted'], 'reply', 'replies')) + ' drafted for you to check'
               if c['drafted'] else '']
    work = [_plural(c['finished'], 'task', 'tasks') + ' finished' if c['finished'] else '',
            _plural(c['explained'], 'problem', 'problems') + ' explained' if c['explained'] else '']
    return 'Overnight: ' + '; '.join(', '.join(filter(None, group)) for group in (replies, work) if any(group)) + '.'


def _decision(row, zh):
    """One clause from the row's own kind and words; the cost comes first."""
    who, words = _plain(row.get('title'), 60), _plain(row.get('text') or row.get('subject'), 40)
    if row.get('kind') == 'reply':
        if zh:
            return '以你的名义回' + (f' {who}' if who else '复') + (f'（{words}）' if words else '') + '——用我拟的稿？'
        return 'Reply' + (f' to {who}' if who else '') + ' as you' + (f' ({words})' if words else '') + ' — send my draft?'
    if row.get('kind') == 'task':
        subject = who or words or ('一项任务' if zh else 'A task')
        return f'{subject}——花一次 Codex 运行去做，还是先放着？' if zh else f'{subject} — spend one Codex run on it, or leave it?'
    subject = who or words or ('一件事' if zh else 'One thread')
    return f'{subject}——不用再回了，标为已处理？' if zh else f'{subject} — no reply needed; mark it done?'


def compose(root, config, local, saved, link):
    """Read-only: the exact note for `local`, given earlier markers; '' means stay quiet."""
    zh = config['language'].lower().startswith('zh')
    previous = _previous(saved, local.date().isoformat())
    totals, pending = counts(root, _start(local, previous), local), actionable(root)
    ids = sorted(row.get('id', '') for row in pending)
    lines = [_summary(totals, zh)] if any(totals.values()) else []
    if pending:
        n = len(pending)
        lines.append(f'{n} 件要你拍板：' if zh else f"{n} decision{'s' if n > 1 else ''}:")
        lines += ['· ' + _decision(row, zh) for row in pending[:2]]
        if n > 2:
            lines.append(f'还有 {n - 2} 件在 Today' if zh else f'{n - 2} more in Today')
    # Nothing new overnight and the same open decisions as last time: say nothing again.
    repeat = not any(totals.values()) and previous is not None and previous.get('pending') == ids
    if lines and not repeat:
        lines.append(('打开 Today：' if zh else 'Open Today: ') + link)
    return {'channel': config['notify']['channel'], 'message': '' if repeat else '\n'.join(lines),
            'counts': totals, 'pending': ids}


def preview(root):
    config = read_config(root)
    return compose(root, config, _local(config), _markers(root), today_link(root))


def _plan(local, entry, value):
    """What a real run would do now, in one line, for --dry-run."""
    if entry:
        at = datetime.fromisoformat(entry['checked_at']).astimezone(local.tzinfo).strftime('%H:%M')
        return f'already sent {at}' if entry['status'] == 'sent' else \
            f"already checked {at} ({entry['status']}): nothing more today"
    if value['channel'] == 'none':
        return 'channel none: nothing will be sent'
    if local.hour < OPENS:
        return f'not due until {OPENS:02d}:00'
    if local.hour >= CLOSES:
        return f'outside the morning window ({OPENS:02d}:00–{CLOSES:02d}:00): nothing will be sent today'
    return f"would send now via {value['channel']}" if value['message'] else 'quiet: nothing to send'


def _record(root, day, entry):
    """Write one date's marker and keep only the last KEEP_DAYS days."""
    oldest = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
    saved = {key: value for key, value in _markers(root).items() if key >= oldest}
    saved[day] = entry
    write_json(state_path(root, 'morning.json'), saved)


def send_message(channel, target, message):
    """Use precisely the existing CLI send paths, including their test seams."""
    from contextlib import redirect_stdout
    from io import StringIO
    from .files import RemError
    if not target.strip():
        raise RemError('Set notify.target to your own chat or personal email address')
    # Existing handlers own formatting, listener startup, transport and send receipts.
    with redirect_stdout(StringIO()):
        if channel == 'telegram':
            from ..cli.commands.telegram_commands import handle_telegram_send
            handle_telegram_send(target, message)
        elif channel == 'email':
            from ..useful_tools.send_email import send_email
            result = send_email(target, 'REM · Today', message)
            if not result.get('success'):
                raise RemError('Email delivery not confirmed; inspect co email sent')
        else:
            from ..cli.commands.listen_commands import handle_send
            handle_send(channel, target, message, plain=True)


def run(root, *, dry_run=False):
    config = read_config(root)
    local = _local(config)
    day = local.date().isoformat()
    if dry_run:
        saved = _markers(root)
        value = compose(root, config, local, saved, today_link(root))
        return {**value, 'plan': _plan(local, saved.get(day), value)}
    if local.hour < OPENS:
        return {'status': 'not_due'}
    if day in (saved := _markers(root)):
        return saved[day]
    # host_online may wait 3s on the network: decide the link before taking the write lock.
    link = today_link(root) if local.hour < CLOSES else ''
    with maintenance_lock(root):
        saved = _markers(root)
        if day in saved:
            return saved[day]
        entry = {'status': 'missed', 'channel': config['notify']['channel'], 'checked_at': service.now().isoformat()}
        if local.hour < CLOSES:
            # An error here claims nothing: scheduled_check reports it and the next tick retries.
            value = compose(root, config, local, saved, link)
            entry.update(status='sending' if value['message'] and value['channel'] != 'none'
                         else 'disabled' if value['message'] else 'quiet', pending=value['pending'])
        _record(root, day, entry)
    if entry['status'] != 'sending':
        return entry
    try:
        send_message(value['channel'], config['notify']['target'], value['message'])
        entry['status'] = 'sent'
    except (Exception, SystemExit) as error:
        # Delivery can be ambiguous. Never retry; doctor carries the safe diagnosis.
        entry.update(status='failed', error=type(error).__name__)
    with maintenance_lock(root):
        _record(root, day, entry)
    return entry


def sender_status():
    from ..inbox import provider
    from ..environment import load_environment
    load_environment()
    result = []
    for channel in CHANNELS:
        if channel == 'email':
            configured = bool(os.environ.get("OPENONION_API_KEY"))
            fix = 'co auth login'
        else:
            sender = provider(channel)
            configured = not (sender.linked() if channel == 'whatsapp' else sender.missing())
            fix = f'co {channel} check'
        result.append({'channel': channel, 'configured': configured,
                       'next': f'co rem config set notify.target YOUR_OWN_CHAT notify.channel {channel}' if configured else fix})
    return result


def doctor(root):
    config = read_config(root)
    senders = sender_status()
    rows = [{'check': 'morning sender ' + item['channel'], 'ok': True,
             'detail': ('configured' if item['configured'] else 'not configured') + '; next: ' + item['next']}
            for item in senders]
    selected = config['notify']['channel']
    sender = next((item for item in senders if item['channel'] == selected), {})
    ready = bool(config['notify']['target']) and sender.get('configured', False)
    rows.append({'check': 'morning channel', 'ok': selected == 'none' or ready,
                 'detail': selected if selected == 'none' or ready else selected + '; setup incomplete',
                 'fix': sender.get('next', 'co rem morning --help')})
    saved = _markers(root)
    latest = max(saved, default=None)  # A later good morning supersedes an old failure.
    if latest and saved[latest]['status'] in ('failed', 'sending'):
        rows.append({'check': 'morning delivery', 'ok': False,
                     'detail': f"{latest}: {saved[latest]['status']}; no automatic retry",
                     'fix': 'co rem morning --dry-run; co rem doctor'})
    return rows


def scheduled_check(root):
    """Notification IO must never stop the round (including a busy writer)."""
    try:
        return run(root)
    except Exception as error:
        # A claimed date remains visible in doctor even if receipt finalization fails.
        print(f"REM morning check unavailable ({type(error).__name__}); next: co rem doctor", file=sys.stderr)
        return {'status': 'unavailable'}
