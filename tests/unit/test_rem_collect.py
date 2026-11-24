"""The stage verb reuses the bounded batch, never a daily round."""
import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import daily, service
from connectonion.rem.files import read_json, state_path, write_json
from tests.unit.test_rem_service import rem  # noqa: F401

pytestmark = pytest.mark.usefixtures('rem_clock')


def invoke(root, *words, json_out=False):
    return CliRunner().invoke(app, ['rem', '--root', str(root),
                                  *(['--json'] if json_out else []), *words])


@pytest.mark.parametrize('options', [[], ['--source', 'gmail'], ['--with', 'avery@example.test']])
def test_collect_reuses_exactly_one_batch(rem, monkeypatch, options):
    root, _ = rem
    calls = []
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **k: pytest.fail('collection investigated'))
    def batch(root, **kwargs):
        calls.append(kwargs)
        return {'id': 'batch', 'items': 40, 'changed': [], 'outcome': 'completed',
                'material_remaining': {'gmail': 1288}}
    monkeypatch.setattr(service, 'run_sync', batch)
    result = invoke(root, 'collect', *options)
    assert result.exit_code == 0, result.output
    assert len(calls) == 1 and not calls[0]['all_pending'] and not calls[0]['scheduled']
    assert calls[0]['source'] == ('gmail' if '--source' in options else '')
    assert calls[0]['with_person'] == ('avery@example.test' if '--with' in options else '')
    assert '40 items' in result.output and '1288 left in gmail' in result.output
    expected = f'Next: co rem --root {root} collect' + (' ' + ' '.join(options) if options else '')
    assert result.output.rstrip().endswith(expected)


def test_collect_dry_run_is_read_only_and_keeps_source_in_next(rem, monkeypatch):
    root, _ = rem
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(service, 'collect', lambda *a, **k: pytest.fail('body read'))
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **k: pytest.fail('daily round'))
    result = invoke(root, 'collect', '--source', 'codex', '--dry-run', json_out=True)
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value['data']['dry_run'] and list(value['data']['sources']) == ['codex']
    assert value['next'].endswith('collect --source codex')
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_collect_runs_existing_mail_batch_and_reports_saved_backlog(rem, monkeypatch):
    from tests.unit.test_rem_mail import FakeMail, mail
    root, _ = rem
    service.toggle_source(root, 'gmail', True)
    service.approve_sources(root)
    sources = service.subscriptions(root)
    sources['gmail']['since'] = '2026-09-01T00:00:00Z'
    write_json(state_path(root, 'subscriptions.json'), sources)
    client = FakeMail([mail(i, f'2026-09-02T{8 + i:02}:00:00+00:00') for i in range(4)])
    monkeypatch.setattr(service, 'mail_client', lambda *a, **k: client)
    from connectonion.rem.config import set_config
    set_config(root, ['limits.extract_items_per_batch', '2'])
    original = service.run_sync
    monkeypatch.setattr(service, 'run_sync', lambda root, **k: original(
        root, runner=lambda *a, **k: {'changed': []}, **k))
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **k: pytest.fail('investigated'))
    result = invoke(root, 'collect', '--source', 'gmail', json_out=True)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert data['items'] == 2 and data['material_remaining'] == {'gmail': 2}
    assert len(client.bodies_read) == 2
    assert sum(map(len, read_json(state_path(root, 'progress.json'), {})['gmail']['pending'].values())) == 2


def test_sync_still_uses_daily_round_and_scheduled_deepen(rem, monkeypatch):
    from connectonion.rem import schedule
    root, _ = rem
    calls = []
    monkeypatch.setattr(service, 'run_sync', lambda *a, **k: pytest.fail('sync became collect'))
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **k: calls.append('daily') or {
        'outcome': 'completed', 'maintenance': {'items': 0, 'changed': []}})
    monkeypatch.setattr(service, 'run_scheduled', lambda root, call: call())
    monkeypatch.setattr(schedule, 'deepen_round', lambda *a, **k: calls.append('deepen') or {'rounds': []})
    assert invoke(root, 'sync').exit_code == 0
    assert calls == ['daily']
    assert invoke(root, 'sync', '--scheduled').exit_code == 0
    assert calls == ['daily', 'daily', 'deepen']
