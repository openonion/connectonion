"""Invented sessions: compare the shared pass with the separate readers byte for byte."""

import json
import os
import shutil
from collections import Counter
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.rem import investigate, project_material, scan, service, session_pass, sessions, skill_usage, source, store
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path
from test_rem_project_workspace import NOW, claude_session, codex_session, exec_command, ws


@pytest.fixture
def invented(ws, monkeypatch):
    for sub in ws.subs.values():
        sub['consented'] = True
    codex_session(ws.codex / 'rollout-owner.jsonl', ws.p('alpha'), [
        ('$example tighten the parser', 1, [('exec', exec_command('cat /skills/example/SKILL.md'))]),
        ('Keep the failure visible', 0.5, []),
    ], session='owner-12345678')
    codex_session(ws.codex / 'rollout-workspace.jsonl', str(ws.projects), [
        ('Fix the worktree', 2, [('exec', exec_command('pytest', workdir=ws.p('alpha/.claude/worktrees/fix')))]),
        ('Now beta', 1, [('cwd', ws.p('beta')), ('exec', exec_command('git -C beta status'))]),
    ])
    codex_session(ws.codex / 'rollout-rem.jsonl', str(ws.root / '.state/tasks/run'), [
        ('$example write the notebook', 1, [])])
    exec_path = ws.codex / 'rollout-exec.jsonl'
    codex_session(exec_path, ws.p('alpha'), [
        ('$example quoted program request', 1, [('exec', exec_command('cat /skills/example/SKILL.md'))])])
    rows = exec_path.read_text().splitlines()
    meta = json.loads(rows[0])
    meta['payload']['source'] = 'exec'
    exec_path.write_text('\n'.join([json.dumps(meta), *rows[1:]]) + '\n')
    codex_session(ws.codex / 'rollout-old.jsonl', ws.p('alpha'), [('$example older work', 300, [])])
    codex_session(ws.codex / 'rollout-expired.jsonl', ws.p('alpha'), [('expired work', 800, [])])
    claude_session(ws.claude / 'command.jsonl', [
        (ws.p('alpha'), '<command-name>/example</command-name>', 1, []),
        (str(ws.projects), 'Read beta first', 0.5, [('Read', {'file_path': ws.p('beta/src/x.py')}, str(ws.projects))]),
    ])
    for path in [*ws.codex.glob('*.jsonl'), *ws.claude.glob('*.jsonl')]:
        age = 800 if 'expired' in path.name else 300 if 'old' in path.name else 1
        stamp = (NOW - timedelta(days=age)).timestamp()
        os.utime(path, (stamp, stamp))
    monkeypatch.setattr(service, 'subscriptions', lambda root: ws.subs)
    monkeypatch.setattr(sessions, 'time', SimpleNamespace(monotonic=lambda: 1))
    monkeypatch.setattr(store, 'time', SimpleNamespace(monotonic=lambda: 1))
    monkeypatch.setattr(sessions, 'project_exclusion', lambda path: '')
    return ws


def artifacts(root, *names):
    paths = []
    for name in names:
        path = root / name
        paths.extend([path] if path.is_file() else sorted(path.rglob('*')))
    return {str(path.relative_to(root)): path.read_bytes() for path in paths if path.is_file()}


def separate_window(sub, since):
    scoped = {**sub, 'enabled': True, 'consented': True, 'since': since.isoformat()}
    items, cursor, unfamiliar = [], {}, 0
    while True:
        batch = source.collect(scoped, cursor, 4_000, 20_000_000)
        items.extend(batch.items)
        unfamiliar += batch.unrecognised
        if batch.progress == cursor:
            break
        cursor = batch.progress
    identity, _ = investigate.session_window_cache(Path('/unused'), scoped)
    return {'version': investigate.SESSION_WINDOW_VERSION, 'subscription': identity,
            'since': since.isoformat(), 'items': items, 'progress': cursor, 'unfamiliar': unfamiliar}


def test_rem_session_pass_matches_all_four_consumers(invented, monkeypatch):
    ws = invented
    since = NOW - timedelta(days=180)
    widest = NOW - timedelta(days=investigate.SESSION_WIDEST_DAYS)
    original = artifacts(ws.root, 'projects')
    counts = skill_usage.usage(ws.subs, ['example'], root=ws.root, now=NOW)
    skill_cache = state_path(ws.root, skill_usage.CACHE).read_bytes()
    messages = project_material.session_messages(ws.subs, since=since, rem_root=ws.root,
                                                folders=project_material.page_folders(ws.notebook))
    filing = project_material.extract(ws.root, ws.subs, now=NOW, full=True)
    filing_files = artifacts(ws.root, 'projects', '.state/projects')
    imported = sessions.import_sessions(ws.root, now=NOW, consented_only=True)
    import_files = artifacts(ws.root, 'sessions', '.state/sessions.json', '.state/session-sources')
    windows = {name: separate_window(sub, widest) for name, sub in ws.subs.items()}
    discovery = scan.scan_projects(ws.subs, 180, ws.root)

    shutil.rmtree(ws.root)
    prepare(ws.root)
    for name, data in original.items():
        path = ws.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    said = []
    prefetched = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180, progress=said.append)
    assert said == ['reading coding sessions: 7/7']
    assert state_path(ws.root, skill_usage.CACHE).read_bytes() == skill_cache
    assert skill_usage.usage(ws.subs, ['example'], root=ws.root, sessions=prefetched) == counts
    assert state_path(ws.root, skill_usage.CACHE).read_bytes() == skill_cache
    assert counts['counts']['example']['count'] == 3
    assert project_material.session_messages(ws.subs, since=since, rem_root=ws.root,
        folders=project_material.page_folders(ws.notebook), sessions=prefetched) == messages
    assert project_material.extract(ws.root, ws.subs, full=True, sessions=prefetched) == filing
    assert artifacts(ws.root, 'projects', '.state/projects') == filing_files
    assert sessions.import_sessions(ws.root, consented_only=True, sessions=prefetched) == imported
    assert artifacts(ws.root, 'sessions', '.state/sessions.json', '.state/session-sources') == import_files
    assert scan.scan_projects(ws.subs, 180, ws.root, sessions=prefetched) == discovery
    for name, path in prefetched.windows.items():
        expected = json.dumps(windows[name], ensure_ascii=False, indent=2) + '\n'
        assert path.read_bytes() == expected.encode()
    real_open = Path.open
    def cached_only(path, *args, **kwargs):
        assert path not in {p for paths in prefetched.files.values() for p in paths}
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', cached_only)
    for name, sub in ws.subs.items():
        said = []
        scoped = {**sub, 'enabled': True, 'consented': True, 'since': widest.isoformat()}
        assert investigate._session_window(scoped, name, lambda *args: said.append(args), ws.root) == (
            windows[name]['items'], windows[name]['unfamiliar'])
        assert said == []
    assert not any('expired' in key for key in prefetched.imports)
    assert any('older work' in item['text'] for item in windows['codex']['items'])
    assert imported['skipped'] == {'exec_or_subagent': 1, 'outside_window': 2, 'rem_task': 1}


def test_rem_init_map_opens_each_session_only_once(invented, monkeypatch):
    from connectonion.rem.map import build_map
    ws = invented
    paths = {path for sub in ws.subs.values() for path in source.source_files(sub)}
    opened = Counter()
    real_open = Path.open

    def tracked(path, *args, **kwargs):
        if path in paths:
            opened[path] += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', tracked)
    report = build_map(ws.root, ws.subs, {}, skill_directories=[])
    sessions.import_sessions(ws.root, consented_only=True, sessions=report.sessions)
    from connectonion.cli.commands.rem_commands import _first_project_rows
    _first_project_rows(ws.root, None, sessions=report.sessions)
    assert opened and max(opened.values()) == 1
    assert opened[ws.codex / 'rollout-expired.jsonl'] == 0
    assert len(opened) == len(paths) - 1


@pytest.mark.parametrize('about', ['', 'alpha'])
def test_rem_window_pass_preserves_byte_cap_interleaving(tmp_path, monkeypatch, about):
    root, store = tmp_path / 'rem', tmp_path / 'codex'
    prepare(root)
    for name in ('a', 'b', 'c'):
        codex_session(store / f'rollout-{name}.jsonl', '/work/alpha', [
            (f'alpha turn {index} in {name}', 1, [('output', 'x' * 400)]) for index in range(8)])
    sub = {'kind': 'codex', 'root': str(store), 'enabled': True, 'consented': True, 'about': about}
    monkeypatch.setattr(source, 'SCAN_BYTES_PER_PASS', 1_000)
    expected = separate_window(sub, NOW - timedelta(days=730))
    result = session_pass.read_sessions(root, {'codex': sub}, now=NOW, days=180)
    assert json.loads(result.windows['codex'].read_bytes()) == expected


def test_rem_pass_keeps_imports_180_days_when_mapping_all_history(invented):
    ws = invented
    path = ws.codex / 'rollout-mixed.jsonl'
    codex_session(path, ws.p('alpha'), [('Old request', 300, []), ('Recent request', 1, [])])
    expected = sessions._read_session(path, 'codex', NOW - timedelta(days=180))
    result = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=36500, import_days=180)
    assert result.imports[str(path)] == expected
    assert [m['text'] for m in expected[0]['messages']] == ['Recent request']
    assert [m['text'] for _, m in result.filing[str(path)]['messages']] == ['Old request', 'Recent request']


@pytest.mark.parametrize('bad', [b'not metadata\n', b'{"type":"session_meta","payload":{}}\n{"message": "role"\n'])
def test_rem_pass_keeps_the_warmers_source_level_parse_guard(invented, bad):
    ws = invented
    (ws.codex / 'rollout-bad.jsonl').write_bytes(bad)
    result = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180)
    assert 'codex' not in result.windows
    assert len(list(state_path(ws.root, 'session-windows').glob('*.json'))) == 1
    imported = sessions.import_sessions(ws.root, sessions=result, consented_only=True)
    assert imported['imported'] > 0


def test_rem_pass_reads_overlapping_subscriptions_once_and_preserves_scopes(invented, monkeypatch):
    ws = invented
    sub = {**ws.subs['codex'], 'about': 'parser', 'project': ws.p('alpha')}
    ws.subs['scoped'] = sub
    paths = {path for subscription in ws.subs.values() for path in source.source_files(subscription)}
    opened, real_open = Counter(), Path.open

    def tracked(path, *args, **kwargs):
        if path in paths:
            opened[path] += 1
        return real_open(path, *args, **kwargs)

    expected = separate_window(sub, NOW - timedelta(days=730))
    monkeypatch.setattr(Path, 'open', tracked)
    result = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180)
    assert max(opened.values()) == 1
    assert json.loads(result.windows['scoped'].read_bytes()) == expected


def test_rem_pass_reports_each_500_files_without_opening_expired_sessions(tmp_path, monkeypatch):
    store = tmp_path / 'codex'
    store.mkdir()
    for index in range(1001):
        path = store / f'rollout-{index:04}.jsonl'
        path.touch()
        os.utime(path, (0, 0))
    monkeypatch.setattr(Path, 'read_bytes', lambda path: pytest.fail('read an expired session'))
    said = []
    session_pass.read_sessions(tmp_path / 'rem', {'codex': {'kind': 'codex', 'root': str(store)}},
                               now=NOW, days=180, progress=said.append)
    assert said == ['reading coding sessions: 500/1001', 'reading coding sessions: 1000/1001',
                    'reading coding sessions: 1001/1001']


def test_rem_consumers_use_the_read_snapshot_when_a_live_session_grows(invented, monkeypatch):
    ws = invented
    path = ws.codex / 'rollout-owner.jsonl'
    original = path.read_bytes()
    expected = skill_usage.usage(ws.subs, ['example'], root=ws.root, now=NOW)
    prefetched = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180)
    later = {'type': 'response_item', 'timestamp': NOW.isoformat(), 'payload': {
        'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '$example Later turn'}]}}
    path.write_bytes(original + (json.dumps(later) + '\n').encode())
    paths = {p for files in prefetched.files.values() for p in files}
    real_open = Path.open

    def snapshot_only(path, *args, **kwargs):
        assert path not in paths
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', snapshot_only)
    assert skill_usage.usage(ws.subs, ['example'], root=ws.root, sessions=prefetched) == expected
    report = sessions.import_sessions(ws.root, sessions=prefetched)
    assert report['imported'] > 0
    saved = json.loads(state_path(ws.root, 'sessions.json').read_bytes())
    assert saved['files'][str(path)]['size'] == len(original)
    assert 'Later turn' not in ''.join(Notebook(ws.root).read(record) for record in Notebook(ws.root).list('sessions'))
