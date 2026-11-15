"""A sync that kept no run record must not point at `co rem logs <id>`.

A no-change batch runs no model and keeps no run (#1846). Its result still
carried an id, and the Next line and the human summary both named
`co rem logs <id>`, which then said the run does not exist.
"""

import json

import pytest
from typer.testing import CliRunner

from connectonion.rem.config import prepare
from connectonion.rem.files import state_path, write_json


@pytest.mark.parametrize('kept', [False, True])
def test_a_sync_names_logs_only_for_a_run_it_kept(tmp_path, monkeypatch, kept):
    from connectonion.cli.main import app
    from connectonion.rem import service
    root = tmp_path / 'notebook'
    prepare(root)
    record = {'id': 'run_abc', 'outcome': 'completed' if kept else 'no_change', 'items': 1 if kept else 0,
              'runner_attempts': 0, 'changed': [], 'warning': ''}
    if kept:
        write_json(state_path(root, 'runs/run_abc.json'), record)
    monkeypatch.setattr(service, 'run_sync', lambda *a, **k: record)

    result = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'sync', '--source', 'codex'])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert str(root) in payload['next']
    assert payload['next'].endswith(' logs run_abc' if kept else ' status')

    text = CliRunner().invoke(app, ['rem', '--root', str(root), 'sync', '--source', 'codex']).output
    assert ('logs run_abc' in text) is kept
