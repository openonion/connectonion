"""Maintain first, then investigate at most one unfinished page within a call cap."""

import uuid
from pathlib import Path

from .config import read_config
from .files import Notebook, WikiError, maintenance_lock, state_path, write_json
from .service import now, run_sync, status, subscriptions, mail_client
from .investigate import investigate


def run_daily(root: Path, *, days: int = 30, maintain=None, investigate_one=None) -> dict:
    maintenance = (maintain or run_sync)(root)
    if maintenance['outcome'] not in ('completed', 'no_change'):
        return {'outcome': 'partial', 'maintenance': maintenance, 'investigation': None}
    notebook = Notebook(root)
    pages = [p for p in notebook.unfinished() if p['path'].startswith(('people/', 'projects/', 'orgs/'))]
    if not pages:
        return {'outcome': 'completed', 'maintenance': maintenance, 'investigation': None}
    config = read_config(root)
    from .inquiry import routing
    required = 3 if routing(root) else 1
    with maintenance_lock(root):
        remaining = config['limits']['runner_calls_per_day'] - status(root)['runner_attempts_today']
        if remaining < required:
            return {'outcome': 'budget_exhausted', 'maintenance': maintenance, 'investigation': None}
        # Reserve the entire remainder before starting; a crash cannot reset the quota.
        record = {'id': 'run_' + uuid.uuid4().hex, 'started_at': now().isoformat(),
                  'outcome': 'running', 'runner_attempts': remaining, 'usage': None,
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
        clients = {s['kind']: mail_client(s['kind'], attachments=True) for s in sources.values()
                   if s.get('enabled') and s.get('kind') in ('gmail', 'outlook')}
        result = (investigate_one or investigate)(root, target, title, handles, days=days,
                      clients=clients, subscriptions=sources, max_calls=remaining)
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
