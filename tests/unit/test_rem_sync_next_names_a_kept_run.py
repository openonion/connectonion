"""A sync or collect that kept no run record must not point at `co rem logs <id>`.

A no-change batch runs no model and keeps no run (#1846). Its result still
carried an id, and the Next line and the human summary both named
`co rem logs <id>`, which then said the run does not exist. sync and collect
share this path; collect keeps its own next step (collect again), and only the
"Full record" line naming the missing run goes.
"""

import json

import pytest
from typer.testing import CliRunner

from connectonion.rem.config import prepare
from connectonion.rem.files import state_path, write_json


def _run(tmp_path, monkeypatch, command, kept):
    from connectonion.cli.main import app
    from connectonion.rem import service
    root = tmp_path / 'notebook'
    prepare(root)
    record = {'id': 'run_abc', 'outcome': 'completed' if kept else 'no_change', 'items': 1 if kept else 0,
              'runner_attempts': 0, 'changed': [], 'warning': ''}
    if kept:
        write_json(state_path(root, 'runs/run_abc.json'), record)
    monkeypatch.setattr(service, 'run_sync', lambda *a, **k: record)
    args = ['rem', '--root', str(root), command, '--source', 'codex']
    as_json = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', *args[3:]])
    text = CliRunner().invoke(app, args)
    return root, as_json, text


@pytest.mark.parametrize('kept', [False, True])
def test_a_sync_names_logs_only_for_a_run_it_kept(tmp_path, monkeypatch, kept):
    root, as_json, text = _run(tmp_path, monkeypatch, 'sync', kept)
    assert as_json.exit_code == 0, as_json.output
    payload = json.loads(as_json.stdout)
    assert str(root) in payload['next']
    assert payload['next'].endswith(' logs run_abc' if kept else ' status')
    assert payload['data'].get('record_kept', True) is kept
    assert text.exit_code == 0, text.output
    assert ('logs run_abc' in text.output) is kept


@pytest.mark.parametrize('kept', [False, True])
def test_collect_keeps_its_next_step_and_names_logs_only_for_a_kept_run(tmp_path, monkeypatch, kept):
    root, as_json, text = _run(tmp_path, monkeypatch, 'collect', kept)
    assert as_json.exit_code == 0, as_json.output
    payload = json.loads(as_json.stdout)
    assert payload['next'].endswith(' collect --source codex')      # unchanged either way
    assert text.exit_code == 0, text.output
    assert ('logs run_abc' in text.output) is kept


@pytest.mark.parametrize('kept', [False, True])
def test_the_daily_round_names_a_full_record_only_for_a_kept_run(tmp_path, monkeypatch, kept):
    """Plain `co rem sync` runs the daily round: its Next is the run list, which always
    opens, but its summary named the batch's own id when the round kept no run."""
    from connectonion.cli.main import app
    from connectonion.rem import daily
    root = tmp_path / 'notebook'
    prepare(root)
    batch = {'id': 'run_abc', 'outcome': 'completed' if kept else 'no_change', 'items': 1 if kept else 0,
             'runner_attempts': 0, 'changed': [], 'warning': ''}
    if kept:
        write_json(state_path(root, 'runs/run_abc.json'), batch)
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **k: {'outcome': 'completed', 'maintenance': batch})

    as_json = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'sync'])
    assert as_json.exit_code == 0, as_json.output
    payload = json.loads(as_json.stdout)
    assert payload['next'].endswith(' logs')                       # the run list, kept or not
    assert payload['data'].get('record_kept', True) is kept
    text = CliRunner().invoke(app, ['rem', '--root', str(root), 'sync'])
    assert text.exit_code == 0, text.output
    assert ('logs run_abc' in text.output) is kept
