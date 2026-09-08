"""A Drive row cannot move between accounts or concurrent listings."""
from unittest.mock import MagicMock

import pytest

from connectonion.cli.commands import gdrive_commands as drive_cli
from connectonion.cli.commands.gmail_listings import save_listing, ListingError


def test_drive_rows_require_matching_account_and_frozen_provider_listing(tmp_path, monkeypatch):
    monkeypatch.setattr(drive_cli, 'LIST_CACHE', tmp_path/'legacy.json')
    directory = tmp_path/'gdrive-listings'
    first = save_listing(directory, 'one@example.test', 'files', ['file-a'], provider='gdrive')
    second = save_listing(directory, 'one@example.test', 'files', ['file-b'], provider='gdrive')
    drive = MagicMock()
    drive.get_account_email.return_value = 'one@example.test'
    assert drive_cli._resolve_file_id('1', drive, first) == 'file-a'
    assert drive_cli._resolve_file_id('1', drive, second) == 'file-b'
    with pytest.raises(ListingError, match='--listing'):
        drive_cli._resolve_file_id('1', drive)
    drive.get_account_email.return_value = 'two@example.test'
    with pytest.raises(ListingError):
        drive_cli._resolve_file_id('1', drive, first)
    gmail = save_listing(directory, 'two@example.test', 'messages', ['message-a'])
    with pytest.raises(ListingError):
        drive_cli._resolve_file_id('1', drive, gmail)


def test_full_drive_ids_never_consult_a_legacy_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(drive_cli, 'LIST_CACHE', tmp_path/'legacy.json')
    drive_cli.LIST_CACHE.write_text('{"file-a":"wrong"}')
    assert drive_cli._resolve_file_id('file-a') == 'file-a'
