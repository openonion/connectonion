"""Synthetic acceptance for safe Granola import and command guidance."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import granola_commands as cli
from connectonion.useful_tools.granola import GranolaClient, GranolaIncompleteRead
from connectonion.useful_tools.adapter import granola_notes_to_records
from tests.unit.granola_fixtures import NOTE_FULL, FOLDERS_PAGE, FOLDER_ID


def client_fixture(monkeypatch):
    client = Mock()
    client.list_folders.return_value = FOLDERS_PAGE['folders']
    client.list_notes.return_value = [{'id': 'not_note1'}, {'id': 'not_note2'}]
    client.hydrate_notes.return_value = [copy.deepcopy(NOTE_FULL)]
    monkeypatch.setattr(cli, '_granola', lambda: client)
    return client


def test_hydration_partial_is_saved_without_refetch(monkeypatch, tmp_path):
    client = client_fixture(monkeypatch)
    client.hydrate_notes.side_effect = GranolaIncompleteRead('second detail unavailable', [[NOTE_FULL]])
    result = CliRunner().invoke(app, ['granola', 'import', FOLDER_ID, '--output', str(tmp_path), '--json'])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload['mapped'] == 1 and payload['complete'] is False
    assert Path(payload['jsonl']).is_file()
    assert client.hydrate_notes.call_count == 1


def test_daily_updates_append_and_repeats_skip(tmp_path):
    first = granola_notes_to_records([NOTE_FULL], 'fixture', selected_folder_id=FOLDER_ID).records
    _, count = cli._place_records(first, tmp_path, None, {})
    assert count == 1
    edited = copy.deepcopy(NOTE_FULL)
    edited['title'] = 'Updated meeting'
    second = granola_notes_to_records([edited], 'fixture', selected_folder_id=FOLDER_ID).records
    target, count = cli._place_records(second, tmp_path, None, {})
    assert count == 1
    assert cli._place_records(second, tmp_path, None, {})[1] == 0
    assert len(target.read_text().splitlines()) == 2


@pytest.mark.parametrize('data', [{}, {'notes': None}, {'notes': [], 'hasMore': 'false'}, {'notes': [], 'error': 'failed'}])
def test_malformed_verify_never_claims_success(monkeypatch, data):
    monkeypatch.setenv('GRANOLA_API_KEY', 'fixture-only')
    client = GranolaClient(_http=Mock())
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: data)
    with pytest.raises((ValueError, GranolaIncompleteRead)):
        client.verify()


def test_invalid_profile_fails_before_remote(monkeypatch, tmp_path):
    client = client_fixture(monkeypatch)
    result = CliRunner().invoke(app, ['granola', 'import', FOLDER_ID, '--profile', 'invalid:profile', '--output', str(tmp_path), '--json'])
    assert result.exit_code == 1 and not client.list_folders.called
    assert not list(tmp_path.iterdir())


def test_source_metadata_not_changed_when_record_write_fails(monkeypatch, tmp_path):
    client = client_fixture(monkeypatch)
    monkeypatch.setattr(cli, '_place_records', Mock(side_effect=OSError('disk')))
    result = CliRunner().invoke(app, ['granola', 'import', FOLDER_ID, '--output', str(tmp_path), '--json'])
    assert result.exit_code == 1
    assert not client.write_source_yaml.called


def test_literal_titles_and_quoted_executable_next(monkeypatch):
    client = client_fixture(monkeypatch)
    client.list_folders.return_value = [{'id': 'folder space', 'name': '[red]:rocket: 中文', 'space_id': None}]
    result = CliRunner().invoke(app, ['granola', 'folders'])
    assert result.exit_code == 0 and '[red]:rocket: 中文' in result.output
    assert "Next: co granola notes 'folder space'" in result.output
    assert result.output.count('Next:') == 1


def test_failure_selected_env_has_single_runnable_recovery(monkeypatch, tmp_path):
    client = client_fixture(monkeypatch)
    from connectonion.useful_tools.granola import GranolaAuthError
    client.verify.side_effect = GranolaAuthError('Unauthorized')
    env = tmp_path / 'co notes.env'
    env.write_text('')
    result = CliRunner().invoke(app, ['--env-file', str(env), 'granola', 'verify'])
    assert result.exit_code == 1
    assert result.output.count('Next:') == 1
    assert f"co --env-file '{env}' granola verify --help" in result.output


def test_long_retry_after_is_bounded_without_early_retry(monkeypatch):
    from connectonion.useful_tools.granola import _TransientError
    monkeypatch.setenv('GRANOLA_API_KEY', 'fixture-only')
    client = GranolaClient(_http=Mock())
    monkeypatch.setattr(client, '_request_once', Mock(side_effect=_TransientError(429, '86400')))
    sleep = Mock(side_effect=AssertionError('must not sleep a day'))
    monkeypatch.setattr('connectonion.useful_tools.granola.time.sleep', sleep)
    with pytest.raises(GranolaIncompleteRead, match='Retry-After'):
        client._request('/notes', partial_pages=[[NOTE_FULL]])
    assert not sleep.called


def test_busy_lock_preserves_json(monkeypatch, tmp_path):
    client_fixture(monkeypatch)
    from connectonion.rem.files import maintenance_lock
    with maintenance_lock(tmp_path):
        result = CliRunner().invoke(app, ['granola', 'import', FOLDER_ID, '--output', str(tmp_path), '--json'])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['error_code'] == 'storage_error'


def test_corrupt_stored_record_preserved_and_rejected(monkeypatch, tmp_path):
    client_fixture(monkeypatch)
    from datetime import date
    path = tmp_path / 'daily' / date.today().strftime('%Y/%m/%d.jsonl')
    path.parent.mkdir(parents=True)
    path.write_text('{"bad":"invalid record"}\n')
    result = CliRunner().invoke(app, ['granola', 'import', FOLDER_ID, '--output', str(tmp_path), '--json'])
    assert result.exit_code == 1 and json.loads(result.stdout)['error_code']
    assert path.read_text() == '{"bad":"invalid record"}\n'


@pytest.mark.parametrize('failure', [ValueError('Note unavailable'), GranolaIncompleteRead('Network failure', [])])
def test_detail_failure_preserves_preceding_success(monkeypatch, failure):
    monkeypatch.setenv('GRANOLA_API_KEY', 'fixture-only')
    client = GranolaClient(_http=Mock())
    client.get_note = Mock(side_effect=[NOTE_FULL, failure])
    with pytest.raises(GranolaIncompleteRead) as error:
        client.hydrate_notes([{'id': 'not_note1'}, {'id': 'not_note2'}])
    assert error.value.partial_pages == [[NOTE_FULL]]


def test_cross_date_no_change_never_reports_nonexistent_jsonl(monkeypatch, tmp_path):
    client_fixture(monkeypatch)
    words = ['granola', 'import', FOLDER_ID, '--output', str(tmp_path), '--json']
    first = CliRunner().invoke(app, words)
    path = Path(json.loads(first.stdout)['jsonl'])
    other = tmp_path / 'daily/2000/01/01.jsonl'
    other.parent.mkdir(parents=True)
    path.rename(other)
    repeated = CliRunner().invoke(app, words)
    report = json.loads(repeated.stdout)
    assert repeated.exit_code == 0 and report['appended'] == 0
    assert report['jsonl'] is None or Path(report['jsonl']).is_file()
    assert len(list(tmp_path.glob('daily/*/*/*.jsonl'))) == 1


def test_transport_pagination_keeps_prior_pages(monkeypatch):
    import httpx
    monkeypatch.setenv('GRANOLA_API_KEY', 'fixture-only')
    http = Mock()
    http.get.side_effect = [Mock(status_code=200, json=lambda: {'notes': [{'id': 'first'}], 'hasMore': True, 'cursor': 'later'}),
                            httpx.ConnectError('private network detail')]
    client = GranolaClient(_http=http)
    with pytest.raises(GranolaIncompleteRead) as error:
        client.list_notes(folder_id=FOLDER_ID)
    assert error.value.partial_pages == [[{'id': 'first'}]]
    assert 'private network detail' not in str(error.value)
