"""Row references identify an immutable account-bound listing, never today's last list."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def test_another_listing_cannot_retarget_a_row(tmp_path):
    from connectonion.cli.commands.gmail_listings import save_listing, resolve_reference
    first = save_listing(tmp_path, 'one@example.test', 'messages', ['inbox-a'], now=100)
    second = save_listing(tmp_path, 'one@example.test', 'messages', ['sent-b'], now=101)
    assert first != second
    assert resolve_reference(tmp_path, '1', 'one@example.test', 'messages', first, now=102) == 'inbox-a'
    assert resolve_reference(tmp_path, '1', 'one@example.test', 'messages', second, now=102) == 'sent-b'


@pytest.mark.parametrize('account,family,time', [('other@example.test','messages',101),
                                               ('one@example.test','drafts',101),
                                               ('one@example.test','messages',1001)])
def test_wrong_account_family_and_expired_listing_fail(tmp_path, account, family, time):
    from connectonion.cli.commands.gmail_listings import save_listing, resolve_reference, ListingError
    listing = save_listing(tmp_path, 'one@example.test', 'messages', ['mail-a'], now=100)
    with pytest.raises(ListingError):
        resolve_reference(tmp_path, '1', account, family, listing, now=time)


def test_unbound_numbers_never_fetch_a_new_inbox(tmp_path):
    from connectonion.cli.commands.gmail_listings import resolve_reference, ListingError
    with pytest.raises(ListingError, match='--listing'):
        resolve_reference(tmp_path, '1', 'one@example.test', 'messages', None)
    assert not list(tmp_path.iterdir())


def test_full_id_ignores_corrupt_cache_and_needs_no_listing(tmp_path):
    from connectonion.cli.commands.gmail_listings import resolve_reference
    (tmp_path / 'legacy.json').write_text('{broken')
    assert resolve_reference(tmp_path, '18fabcdef123', 'one@example.test', 'messages', None) == '18fabcdef123'


def test_concurrent_listings_have_independent_frozen_rows(tmp_path):
    from connectonion.cli.commands.gmail_listings import save_listing, resolve_reference
    with ThreadPoolExecutor(4) as pool:
        tokens = list(pool.map(lambda i: save_listing(tmp_path, 'one@example.test', 'messages', [f'mail-{i}']), range(8)))
    assert len(set(tokens)) == 8
    for i, token in enumerate(tokens):
        assert resolve_reference(tmp_path, '1', 'one@example.test', 'messages', token) == f'mail-{i}'


def test_missing_corrupt_and_traversal_listing_ids_fail_closed(tmp_path):
    from connectonion.cli.commands.gmail_listings import resolve_reference, ListingError
    for token in ['../secret', 'bad', 'a' * 32]:
        with pytest.raises(ListingError):
            resolve_reference(tmp_path, '1', 'one@example.test', 'messages', token)


def test_sent_emits_its_own_readable_ids_and_listing(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock
    from connectonion.cli.commands import gmail_commands as gm
    gmail = MagicMock()
    gmail.get_account_email.return_value = 'one@example.test'
    gmail.list_search.return_value = [{'id': 'sent-id', 'from': 'one@example.test',
                                      'subject': 'Test', 'date': 'Unknown', 'snippet': '', 'unread': False}]
    gmail._format_dicts.return_value = '1. ID: sent-id'
    monkeypatch.setattr(gm, '_gmail', lambda: gmail)
    monkeypatch.setattr(gm, 'INBOX_CACHE', tmp_path / 'legacy.json')
    gm.handle_gmail_sent()
    output = capsys.readouterr().out
    assert 'sent-id' in output
    assert 'Listing:' in output
    assert 'co gmail read sent-id' in output
    gmail.list_search.assert_called_once_with('in:sent', max_results=10)


def test_read_mark_read_missing_scope_exits_nonzero(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    import typer
    from connectonion.cli.commands import gmail_commands as gm
    gmail = MagicMock()
    gmail.get_email_body.return_value = 'From: one@example.test\n--- Email Body ---\nHello'
    monkeypatch.setattr(gm, '_gmail', lambda: gmail)
    monkeypatch.setenv('GOOGLE_SCOPES', 'gmail.readonly')
    with pytest.raises(typer.Exit) as error:
        gm.handle_gmail_read('full-message-id', mark_read=True)
    assert error.value.exit_code == 1
    gmail.mark_read.assert_not_called()


def test_read_mark_read_unknown_scope_metadata_lets_the_api_decide(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from connectonion.cli.commands import gmail_commands as gm
    gmail = MagicMock()
    gmail.get_email_body.return_value = 'From: one@example.test\n--- Email Body ---\nHello'
    monkeypatch.setattr(gm, '_gmail', lambda: gmail)
    monkeypatch.delenv('GOOGLE_SCOPES', raising=False)
    gm.handle_gmail_read('full-message-id', mark_read=True)
    gmail.mark_read.assert_called_once_with('full-message-id')


def test_account_binding_uses_provider_profile_instead_of_saved_metadata(monkeypatch):
    from unittest.mock import MagicMock
    from connectonion.useful_tools.gmail import Gmail
    client = Gmail.__new__(Gmail)
    service = MagicMock()
    service.users().getProfile().execute.return_value = {'emailAddress': ' Actual@Example.test '}
    monkeypatch.setattr(client, '_get_service', lambda: service)
    monkeypatch.setenv('GOOGLE_EMAIL', 'stale@example.test')
    assert client.get_account_email() == 'actual@example.test'
    assert client.get_account_email() == 'actual@example.test'
    assert service.users().getProfile().execute.call_count == 1


@pytest.mark.parametrize('args', [['read', '1'], ['reply', '1', 'Hello'],
    ['draft', 'preview', '1'], ['draft', 'attach', '1', 'report.pdf'],
    ['draft', 'remove', '1', '1'], ['draft', 'replace', '1', '1', 'report.pdf'], ['draft', 'send', '1']])
@pytest.mark.parametrize("color", [False, True])
def test_numeric_command_help_exposes_listing_selector(args, color, monkeypatch):
    from click import unstyle
    from typer import rich_utils
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", color)
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    commands = args[:2] if args[0] == 'draft' else args[:1]
    result = CliRunner().invoke(app, ['gmail', *commands, '--help'], color=color)
    assert result.exit_code == 0
    if color:
        assert '\x1b[' in result.output
    assert '--listing' in unstyle(result.output)


def test_wrong_account_command_cannot_read_or_mutate(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import gmail_commands as gm
    from connectonion.cli.commands.gmail_listings import save_listing
    token = save_listing(tmp_path / 'gmail-listings', 'previous@example.test', 'messages', ['private-id'])
    gmail = MagicMock()
    gmail.get_account_email.return_value = 'current@example.test'
    monkeypatch.setattr(gm, '_gmail', lambda: gmail)
    monkeypatch.setattr(gm, 'INBOX_CACHE', tmp_path / 'legacy.json')
    result = CliRunner().invoke(app, ['gmail', 'read', '1', '--listing', token, '--mark-read'])
    assert result.exit_code == 1
    assert 'another account' in result.output
    gmail.get_email_body.assert_not_called()
    gmail.mark_read.assert_not_called()


def test_evicted_listing_requires_relisting(tmp_path):
    from connectonion.cli.commands.gmail_listings import save_listing, resolve_reference, ListingError, MAX_LISTINGS
    token = save_listing(tmp_path, 'one@example.test', 'messages', ['first'])
    for i in range(MAX_LISTINGS):
        save_listing(tmp_path, 'one@example.test', 'messages', [f'mail-{i}'])
    assert len(list(tmp_path.glob('*.json'))) == MAX_LISTINGS
    with pytest.raises(ListingError):
        resolve_reference(tmp_path, '1', 'one@example.test', 'messages', token)
