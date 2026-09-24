"""Maintain first, then investigate at most one unfinished page within a call cap."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import read_config
from .files import Notebook, WikiError, maintenance_lock, state_path, write_json
from .service import now, run_logs, run_sync, status, subscriptions, mail_client
from .investigate import investigate


def run_daily(root: Path, *, days: int = 30, scheduled: bool = False,
              maintain=None, investigate_one=None) -> dict | None:
    maintenance = (maintain or run_sync)(root, scheduled=True) if scheduled else (maintain or run_sync)(root)
    if maintenance is None:
        return None
    if maintenance['outcome'] not in ('completed', 'no_change'):
        return {'outcome': 'partial', 'maintenance': maintenance, 'investigation': None}
    notebook = Notebook(root)
    from .queue import order
    pages = [p for category in ('people', 'projects', 'orgs') for p in order(root, category) if not p['recent']]
    pages.sort(key=lambda p: -p['weight'])
    if not pages:
        return {'outcome': 'completed', 'maintenance': maintenance, 'investigation': None}
    config = read_config(root)
    from .inquiry import routing
    required = 3 if routing(root) else 1
    with maintenance_lock(root):
        state = status(root)
        zone = ZoneInfo(config['schedule']['timezone']) if config['schedule']['timezone'] else timezone.utc
        if any(record.get('phase') == 'daily-investigation' and
               datetime.fromisoformat(record['started_at']).astimezone(zone).date().isoformat() == state['date']
               for record in run_logs(root)):
            return {'outcome': 'completed', 'maintenance': maintenance, 'investigation': None,
                    'reason': 'already_attempted_today'}
        remaining = config['limits']['runner_calls_per_day'] - state['runner_attempts_today']
        if remaining < required:
            return {'outcome': 'budget_exhausted', 'maintenance': maintenance, 'investigation': None}
        # Keep up to two calls for later maintenance slots. Reserve before starting
        # so an interrupted investigation cannot restart beyond the daily cap.
        allocation = min(remaining, max(required, remaining - 2))
        record = {'id': 'run_' + uuid.uuid4().hex, 'started_at': now().isoformat(),
                  'outcome': 'running', 'runner_attempts': allocation, 'usage': None,
                  'sources': [], 'items': 0, 'changed': [], 'phase': 'daily-investigation'}
        path = state_path(root, f"runs/{record['id']}.json")
        write_json(path, record)
    target = pages[0]['path']
    text = notebook.read(target)
    title = next((line[2:] for line in text.splitlines() if line.startswith('# ')), target)
    person = next((p for p in notebook.people() if p['path'] == target), {})
    handles = list(dict.fromkeys([title, *person.get('emails', []), *person.get('aliases', [])]))
    try:
        sources = subscriptions(root)
        # The same mailboxes `co wiki investigate` reads: every connected one the
        # user did not unsubscribe. Reading only subscribed mailboxes here left the
        # scheduled investigation with no mail -- the #1628 failure, one path over.
        from .service import mail_available
        clients = {kind: mail_client(kind, attachments=True) for kind in ('outlook', 'gmail')
                   if mail_available(kind) and not sources.get(kind, {}).get('unsubscribed')}
        result = (investigate_one or investigate)(root, target, title, handles, days=days,
                      clients=clients, subscriptions=sources, max_calls=allocation)
        record.update(outcome='completed', usage=result.get('usage'), changed=result.get('changed', []))
    except Exception as error:
        record.update(outcome='failed', error=str(error) if isinstance(error, WikiError) else type(error).__name__,
                      usage=getattr(error, 'usage', None))
        result = None
    finally:
        record['finished_at'] = now().isoformat()
        write_json(path, record)
    return {'outcome': 'completed' if result is not None else 'partial',
            'maintenance': maintenance, 'investigation': result, 'run': record}
