"""Source recovery and CLI experience acceptance; synthetic Graph only."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import onenote_source_commands as cli
from connectonion.useful_tools.onenote_source import OneNoteSource, sync_onenote
from onenote_source_fixtures import graph, HTML


def test_all_failed_does_not_create_even_lock_state(graph, tmp_path):
    result = sync_onenote(OneNoteSource(), 'nb-fixture', 'section-fixture', ['page-gone'], tmp_path)
    assert result['errors'] and not list(tmp_path.iterdir())


def test_scope_failure_does_not_create_lock_state(graph, tmp_path):
    with pytest.raises(ValueError):
        sync_onenote(OneNoteSource(), 'nb-fixture', 'unknown', ['page-good'], tmp_path)
    assert not list(tmp_path.iterdir())


def test_full_recovers_unchanged_timestamp_without_duplicate_versions(graph, tmp_path):
    routes, _ = graph
    args = (OneNoteSource(), 'nb-fixture', 'section-fixture', ['page-good'], tmp_path)
    first = sync_onenote(*args)
    target = Path(first['jsonl'])
    old = target.read_text()
    routes['/me/onenote/pages/page-good/content'] = '<html><body>Recovered edit</body></html>'
    assert sync_onenote(*args)['written'] == 0
    assert sync_onenote(*args, full=True)['written'] == 1
    assert target.read_text().startswith(old)
    assert sync_onenote(*args, full=True)['written'] == 0
    assert len(target.read_text().splitlines()) == 2


def test_full_deduplicates_across_dates(graph, tmp_path, monkeypatch):
    from connectonion.useful_tools import onenote_storage
    args = (OneNoteSource(), 'nb-fixture', 'section-fixture', ['page-good'], tmp_path)
    sync_onenote(*args)
    monkeypatch.setattr(onenote_storage, 'prepare_import', lambda *args: tmp_path / 'daily/2099/01/01.jsonl')
    result = sync_onenote(*args, full=True)
    assert result['written'] == 0 and result['skipped'] == 1
    assert not (tmp_path / 'daily/2099').exists()


def test_other_driver_cannot_be_overwritten(graph, tmp_path):
    sync_onenote(OneNoteSource(), 'nb-fixture', 'section-fixture', ['page-good'], tmp_path)
    path = tmp_path / 'source.yaml'
    saved = yaml.safe_load(path.read_text())
    saved['driver'] = 'jira'
    path.write_text(yaml.safe_dump(saved))
    original = path.read_bytes()
    with pytest.raises(ValueError, match='another account or scope'):
        sync_onenote(OneNoteSource(), 'nb-fixture', 'section-fixture', ['page-empty'], tmp_path)
    assert path.read_bytes() == original


@pytest.mark.parametrize('args,method,result,next_command', [
    (['verify'], 'verify_connection', {'read_only': True, 'account': 'fixture'}, 'co onenote source notebooks'),
    (['notebooks'], 'notebooks', [{'id': 'nb space', 'displayName': '[red]:rocket: 中文'}], "co onenote source sections 'nb space'"),
    (['sections', 'nb space'], 'sections', [{'id': 'section space', 'displayName': 'Section'}], "co onenote source pages 'nb space' 'section space'"),
    (['pages', 'nb', 'sec'], 'pages', {'pages': [{'id': 'page space', 'title': 'Page'}], 'truncated': False}, "co onenote source sync nb sec 'page space'"),
])
def test_discovery_outputs_single_next_and_literal_data(monkeypatch, args, method, result, next_command):
    source = Mock()
    getattr(source, method).return_value = result
    monkeypatch.setattr(cli, '_source', lambda: source)
    output = CliRunner().invoke(app, ['onenote', 'source', *args])
    assert output.exit_code == 0, output.output
    assert output.output.count('Next:') == 1
    assert next_command in output.output
    if method == 'notebooks':
        assert '[red]:rocket: 中文' in output.output


@pytest.mark.parametrize('args', [['verify'], ['notebooks'], ['pages', 'nb', 'sec']])
def test_json_does_not_gain_generic_tip(monkeypatch, args):
    source = Mock()
    source.verify_connection.return_value = {'read_only': True}
    source.notebooks.return_value = []
    source.pages.return_value = {'pages': [], 'truncated': False}
    monkeypatch.setattr(cli, '_source', lambda: source)
    result = CliRunner().invoke(app, ['onenote', 'source', *args, '--json'])
    assert result.exit_code == 0
    assert json.loads(result.stdout) is not None and not result.stderr


def test_failure_has_one_real_selected_environment_recovery(monkeypatch, tmp_path):
    source = Mock()
    source.pages.side_effect = ValueError('Ambiguous selection')
    monkeypatch.setattr(cli, '_source', lambda: source)
    env = tmp_path / 'co notes.env'
    env.write_text('')
    result = CliRunner().invoke(app, ['--env-file', str(env), 'onenote', 'source', 'pages', 'nb', 'sec'])
    assert result.exit_code == 1
    assert result.output.count('Next:') == 1
    assert f"co --env-file '{env}' onenote source pages --help" in result.output


def test_partial_has_one_recovery_and_preserves_valid_result(graph, tmp_path):
    result = CliRunner().invoke(app, ['onenote', 'source', 'sync', 'nb-fixture', 'section-fixture',
                                    'page-good', 'page-gone', '--output', str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert result.output.count('Next:') == 1
    assert 'Valid records retained:' in result.output
    assert 'Next: co onenote source sync --help' in result.output


def test_malformed_verify_probe_is_failure(graph):
    routes, _ = graph
    routes['/me/onenote/notebooks'] = {'unexpected': []}
    with pytest.raises(ValueError, match='malformed'):
        OneNoteSource().verify_connection()


def test_browsing_missing_scope_names_auth_recovery(monkeypatch):
    from connectonion.cli.commands import onenote_commands
    def denied():
        raise ValueError('Notes.ReadWrite is required. Run co auth microsoft')
    monkeypatch.setattr(onenote_commands, '_onenote', denied)
    result = CliRunner().invoke(app, ['onenote', 'ls'])
    assert result.exit_code == 1
    assert result.output.count('Next:') == 1
    assert 'Next: co auth microsoft' in result.output
