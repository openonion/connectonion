"""Synthetic checks for Granola command guidance and client failure handling."""
import copy
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import granola_commands as cli
from connectonion.useful_tools.granola import GranolaClient, GranolaIncompleteRead
from tests.unit.granola_fixtures import NOTE_FULL, FOLDERS_PAGE, FOLDER_ID


def client_fixture(monkeypatch):
    client = Mock()
    client.list_folders.return_value = FOLDERS_PAGE['folders']
    client.list_notes.return_value = [{'id': 'not_note1'}, {'id': 'not_note2'}]
    client.hydrate_notes.return_value = [copy.deepcopy(NOTE_FULL)]
    monkeypatch.setattr(cli, '_granola', lambda: client)
    return client


@pytest.mark.parametrize('data', [{}, {'notes': None}, {'notes': [], 'hasMore': 'false'}, {'notes': [], 'error': 'failed'}])
def test_malformed_verify_never_claims_success(monkeypatch, data):
    monkeypatch.setenv('GRANOLA_API_KEY', 'fixture-only')
    client = GranolaClient(_http=Mock())
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: data)
    with pytest.raises((ValueError, GranolaIncompleteRead)):
        client.verify()


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
