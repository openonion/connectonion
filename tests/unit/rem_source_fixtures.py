"""Synthetic contract providers; no real clients, credentials, vaults or network."""

from datetime import datetime, timezone
from hashlib import sha256
import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from connectonion.rem import service, source_hooks as hooks
from connectonion.rem.config import prepare
from connectonion.rem.files import read_json, state_path, write_json
from connectonion.rem.source import Batch


def citation(kind, version=1, account='account'):
    if kind == 'summaries':
        digest = sha256(str(version).encode()).hexdigest()
        return f'adapter:docs/summaries/daily/2026/11/19.jsonl#summaries:{account}:note?version={digest}'
    if kind == 'tasks':
        return f'tasks:{account}:task:2026-11-19.jsonl:{version}'
    return f'notes:{account}:note:{version}'


def identity(kind, target):
    if kind == 'summaries':
        return target.partition('#')[2].partition('?version=')[0] if '?version=' in target else None
    return ':'.join(target.split(':')[:3]) if target.startswith(kind + ':') else None


@pytest.fixture
def shared_sources(tmp_path, monkeypatch):
    root = tmp_path / 'book'
    monkeypatch.setattr(service, 'mail_available', lambda kind: False)
    monkeypatch.setattr(service, 'codex_sessions_root', lambda: tmp_path / 'missing-codex')
    monkeypatch.setattr(service, 'claude_projects_root', lambda: tmp_path / 'missing-claude')
    prepare(root)
    for name in ('codex', 'claude-code', 'gmail', 'outlook', 'whatsapp'):
        service.toggle_source(root, name, False)
    modules, loaded, events, current, failures = {}, [], [], {}, {}
    for kind in ('notes', 'tasks', 'summaries'):
        module = ModuleType('synthetic_rem_' + kind)
        module.kind, module.skill = kind, 'rem-source-' + kind
        modules[kind] = module
        current[kind] = 1
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(hooks, 'MODULES', {kind: mod.__name__ for kind, mod in modules.items()})
    original = importlib.import_module

    def load(name, package=None):
        if name.startswith('synthetic_rem_'):
            loaded.append(name)
        return original(name, package)

    monkeypatch.setattr(hooks.importlib, 'import_module', load)

    def install(kind, module):
        def store():
            return state_path(root, 'synthetic-' + kind + '.json')

        def configure(notebook, **options):
            events.append((kind, 'configure', options))
            hooks.reject_options({key: value for key, value in options.items()
                                  if key not in ('folders', 'project', 'vault', 'config', 'connect', 'replace')})
            return {'kind': kind, 'account': 'account', 'folders': options.get('folders') or ['Work']}

        def fetch(notebook, sub):
            events.append((kind, 'fetch'))
            if kind in failures:
                raise failures[kind]
            with hooks.acquisition_guard(notebook, sub)():
                saved = read_json(store(), {})
                target = citation(kind, current[kind])
                added = target not in saved
                saved[target] = {'source': target, 'source_kind': kind, 'role': 'original',
                                 'timestamp': datetime.now(timezone.utc).isoformat(),
                                 'text': f'Atlas saved version {current[kind]}', 'folder': 'Work'}
                write_json(store(), saved)
                write_json(state_path(root, 'synthetic-index-' + kind + '.json'), {'latest': target})
            return {'added': int(added), 'unchanged': int(not added)}

        def pending(notebook, sub, progress):
            events.append((kind, 'pending'))
            index = read_json(state_path(root, 'synthetic-index-' + kind + '.json'), {})
            return {'body_reads': False, 'count': None if not index else int(progress.get('last') != index['latest'])}

        def collect(notebook, sub, progress, max_items, max_chars):
            events.append((kind, 'collect'))
            saved = read_json(store(), {})
            latest = next(reversed(saved), None)
            if latest is None or latest == progress.get('last'):
                return Batch([], progress)
            items, _ = hooks.bounded([saved[latest]], max_items, max_chars)
            progress['last'] = latest
            return Batch(items, progress)

        def gather(notebook, sub, handles, **options):
            events.append((kind, 'gather', options))
            saved = read_json(store(), {})
            rows = list(saved.values())[-1:]
            rows = [row for row in rows if options['start'] <= datetime.fromisoformat(row['timestamp'])
                    and (options['end'] is None or datetime.fromisoformat(row['timestamp']) < options['end'])]
            rows, limited = hooks.bounded(rows, options['max_items'], options['max_chars'])
            return rows, [kind + ': saved matches' + ('; limited' if limited else '')]

        def cited(notebook, sub, target):
            events.append((kind, 'cited'))
            row = read_json(store(), {}).get(target)
            if not row or row['folder'] not in sub['folders']:
                return None
            return {'excerpt': row['text'], 'truncated': False, 'time': row['timestamp'],
                    'sender': '', 'thread': '', 'source': target, 'subject': 'Atlas'}

        module.configure, module.fetch, module.pending = configure, fetch, pending
        module.collect, module.gather, module.cited = collect, gather, cited
        module.record_of = lambda target: identity(kind, target)
        module.status = lambda sub: {'folders': sub['folders']}
        module.consent = lambda sub: 'Read ' + ', '.join(sub['folders'])

    for kind, module in modules.items():
        install(kind, module)

    def select(*kinds, approve=True):
        for kind in kinds:
            hooks.configure(root, kind)
        if approve:
            service.approve_sources(root)
        loaded.clear()
        events.clear()

    return SimpleNamespace(root=root, modules=modules, loaded=loaded, events=events,
                           current=current, failures=failures, select=select)
