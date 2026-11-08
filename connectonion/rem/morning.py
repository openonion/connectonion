"""One deterministic, quiet morning note, claimed before external delivery."""

from datetime import datetime, timedelta
from pathlib import Path
import os
import sys

from . import approvals, service
from .config import read_config
from .files import maintenance_lock, read_json, state_path, write_json


CHANNELS = ('telegram', 'lark', 'whatsapp', 'email')  # Email is the last choice.


def _window(config):
    local = service.now().astimezone(service.notebook_zone(config))
    return local, local.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=1)


def _within(value, start, end):
    if not value:
        return False
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return moment.tzinfo is not None and start <= moment <= end


def counts(root, config):
    local, start = _window(config)
    end = local.replace(hour=6, minute=0, second=0, microsecond=0)
    items = read_json(state_path(root, 'night.json'), {}).get('items', {}).values()
    prepared = {row.get('draft_id') or str(index) for index, entry in enumerate(items)
                if (row := entry.get('outcome', {})).get('kind') == 'prepared'
                and _within(row.get('prepared_at'), start, end)}
    # night.json is a current projection: sent replies may already have left it.
    # Preserve their preparation count from the existing draft receipts.
    for path in state_path(root, 'drafts').glob('*.json'):
        draft = read_json(path, {})
        if draft.get('status') in ('prepared', 'held', 'sent') and _within(draft.get('prepared_at'), start, end):
            prepared.add(draft.get('id') or path.stem)
    queue = read_json(state_path(root, 'approvals.json'), {}).values()
    sent = sum(row.get('kind') == 'reply' and row.get('by') == 'rem' and row.get('status') == 'sent'
               and _within(row.get('release_at'), start, end) for row in queue)
    receipts = [read_json(path, {}) for path in state_path(root, 'tasks').glob('do-*/receipt.json')]
    investigations = read_json(state_path(root, 'investigations/index.json'), {}).get('items', [])
    return {'drafts': len(prepared), 'sent': sent,
            'dispatched': sum(_within(row.get('started_at'), start, end) for row in receipts),
            'finished': sum(row.get('result') == 'completed' and _within(row.get('finished_at'), start, end)
                            for row in receipts),
            'investigations': sum(row.get('status') == 'explained' and _within(row.get('explained_at'), start, end)
                                  for row in investigations)}


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


def _name(row):
    # Titles are user-facing names; never substitute a record, ID, path or failure reason.
    text = ' '.join(str(row.get('title', '')).split())
    if not text or '/' in text or '\\' in text or ':' in text:
        return ''
    return text[:60]


def preview(root):
    config = read_config(root)
    totals, pending = counts(root, config), actionable(root)
    zh = config['language'].lower().startswith('zh')
    names = list(dict.fromkeys(name for row in pending if (name := _name(row))))[:2]
    c = totals
    first = (f"昨夜：备好 {c['drafts']} 封草稿，已发 {c['sent']} 封回复，派出 {c['dispatched']} 项任务、完成 {c['finished']} 项，讲清 {c['investigations']} 项调查。" if zh else
             f"Overnight: {c['drafts']} drafts prepared, {c['sent']} replies sent, {c['dispatched']} tasks dispatched, {c['finished']} finished, {c['investigations']} investigations explained.")
    second = f"{len(pending)} 件等你点一下" if zh else f"{len(pending)} need one click"
    if names:
        second += '：' + '、'.join(names) if zh else ': ' + ', '.join(names)
    message = '\n'.join([first, second, ('打开 Today：' if zh else 'Open Today: ') + today_link(root)])
    return {'channel': config['notify']['channel'], 'message': message if any(totals.values()) or pending else '',
            'counts': totals, 'pending': len(pending)}


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
    if dry_run:
        return preview(root)
    config = read_config(root)
    local, _ = _window(config)
    if local.hour < 6:
        return {'status': 'not_due'}
    date = local.date().isoformat()
    with maintenance_lock(root):
        saved = read_json(state_path(root, 'morning.json'), {})
        if date in saved:
            return saved[date]
        try:
            value = preview(root)
        except Exception as error:
            entry = {'status': 'failed', 'channel': config['notify']['channel'],
                     'checked_at': service.now().isoformat(), 'error': type(error).__name__}
            saved[date] = entry
            write_json(state_path(root, 'morning.json'), saved)
            return entry
        status = 'sending' if value['message'] and value['channel'] != 'none' else 'disabled' if value['message'] else 'quiet'
        entry = {'status': status, 'channel': value['channel'], 'checked_at': service.now().isoformat()}
        saved[date] = entry
        write_json(state_path(root, 'morning.json'), saved)
    if status != 'sending':
        return entry
    try:
        send_message(value['channel'], config['notify']['target'], value['message'])
        entry['status'] = 'sent'
    except (Exception, SystemExit) as error:
        # Delivery can be ambiguous. Never retry; doctor carries the safe diagnosis.
        entry.update(status='failed', error=type(error).__name__)
    with maintenance_lock(root):
        saved = read_json(state_path(root, 'morning.json'), {})
        saved[date] = entry
        write_json(state_path(root, 'morning.json'), saved)
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
    rows = [{'check': 'morning sender ' + item['channel'], 'ok': True,
             'detail': ('configured' if item['configured'] else 'not configured') + '; next: ' + item['next']}
            for item in sender_status()]
    selected = config['notify']['channel']
    rows.append({'check': 'morning channel', 'ok': selected == 'none' or bool(config['notify']['target']),
                 'detail': selected, 'fix': 'co rem config set notify.target YOUR_OWN_CHAT'})
    for date, entry in read_json(state_path(root, 'morning.json'), {}).items():
        if entry['status'] in ('failed', 'sending'):
            rows.append({'check': 'morning delivery', 'ok': False,
                         'detail': f"{date}: {entry['status']}; no automatic retry",
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
