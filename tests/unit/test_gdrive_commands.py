"""Unit tests for connectonion/cli/commands/gdrive_commands.py

Tests cover:
- _gdrive() credential/scope guard (prints 'co auth google' hint, exits 1)
- _size/_kind/_when column rendering
- listing: table in a terminal, tab-separated full ids when piped, numbering cache
- _resolve_file_id() short-number resolution
- get/put/rm handlers
"""

import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest
import typer
from rich.console import Console

from connectonion.cli.commands import gdrive_commands
from connectonion.cli.commands.gdrive_commands import (
    _gdrive,
    _kind,
    _resolve_file_id,
    _size,
    _when,
    handle_gdrive_get,
    handle_gdrive_list,
    handle_gdrive_put,
    handle_gdrive_rm,
    handle_gdrive_search,
)

CONNECTED_ENV = {
    "GOOGLE_SCOPES": "gmail.send,gmail.readonly,gmail.modify,calendar,drive",
    "GOOGLE_ACCESS_TOKEN": "test-token",
    "GOOGLE_REFRESH_TOKEN": "test-refresh",
    "GOOGLE_EMAIL": "aaron@example.com",
}

# A token issued before Drive was added to the OAuth scopes.
PRE_DRIVE_ENV = {**CONNECTED_ENV, "GOOGLE_SCOPES": "gmail.send,gmail.readonly,gmail.modify,calendar"}


def plain(text):
    """Strip ANSI colour codes so assertions match what a user reads."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def sample_files(n):
    return [{
        "id": f"file-{i}",
        "name": f"Document {i}.pdf",
        "type": "application/pdf",
        "modified": "2026-07-26T14:30:00.000Z",
        "size": 2048 * i,
        "link": f"https://drive.google.com/file/d/file-{i}/view",
    } for i in range(1, n + 1)]


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.co/gdrive_last_list.json."""
    monkeypatch.setattr(gdrive_commands, "LIST_CACHE", tmp_path / ".co" / "gdrive_last_list.json")


class TestGDriveGuard:

    def test_missing_access_token_exits_with_hint(self, capsys):
        with patch.dict(os.environ, {"GOOGLE_ACCESS_TOKEN": "", "GOOGLE_SCOPES": "drive"}, clear=False):
            with pytest.raises(typer.Exit):
                _gdrive()

        output = capsys.readouterr().out
        assert "Google account not connected" in output
        assert "co auth google" in output

    def test_pre_drive_token_gets_reconnect_hint(self, capsys):
        """Drive was added after Gmail/Calendar — old tokens lack it."""
        with patch.dict(os.environ, PRE_DRIVE_ENV, clear=False):
            with pytest.raises(typer.Exit):
                _gdrive()

        output = capsys.readouterr().out
        assert "Drive permission missing" in output
        assert "co auth google" in output

    def test_connected_returns_gdrive_instance(self):
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            result = _gdrive()

        from connectonion.useful_tools.gdrive import GDrive
        assert isinstance(result, GDrive)


class TestColumns:

    def test_size_renders_units(self):
        assert _size(512) == "512B"
        assert _size(2048) == "2.0KB"
        assert _size(5 * 1024 * 1024) == "5.0MB"

    def test_sizeless_files_show_a_dash(self):
        """Folders, shortcuts and Google-native docs report no size."""
        assert _size(0) == "-"

    def test_kind_shortens_native_types(self):
        assert _kind("application/vnd.google-apps.spreadsheet") == "spreadsheet"

    def test_kind_shortens_binary_types(self):
        assert _kind("application/pdf") == "pdf"

    def test_when_renders_rfc3339_with_fractional_seconds(self):
        assert re.fullmatch(r"[A-Z][a-z]{2} \d{2} \d{2}:\d{2}", _when("2026-07-26T14:30:00.000Z"))

    def test_when_renders_rfc3339_without_fractional_seconds(self):
        assert re.fullmatch(r"[A-Z][a-z]{2} \d{2} \d{2}:\d{2}", _when("2026-07-26T14:30:00Z"))

    def test_when_handles_empty(self):
        assert _when("") == ""


class TestHandleList:

    def test_empty_listing_message(self, capsys):
        drive = MagicMock()
        drive.list_files.return_value = []

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_list()

        assert "no files" in capsys.readouterr().out

    def test_empty_listing_writes_no_cache(self):
        """An empty listing must not clobber the numbering from the last one."""
        drive = MagicMock()
        drive.list_files.return_value = []

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_list()

        assert not gdrive_commands.LIST_CACHE.exists()

    def test_table_and_cache(self, monkeypatch, capsys):
        monkeypatch.setattr(gdrive_commands, "console", Console(force_terminal=True, width=120))
        drive = MagicMock()
        drive.list_files.return_value = sample_files(3)

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_list(last=3)

        output = plain(capsys.readouterr().out)
        assert "Document 1.pdf" in output
        assert "co gdrive get" in output
        assert json.loads(gdrive_commands.LIST_CACHE.read_text()) == {
            "1": "file-1", "2": "file-2", "3": "file-3",
        }

    def test_piped_output_carries_full_ids(self, monkeypatch, capsys):
        monkeypatch.setattr(gdrive_commands, "console", Console(force_terminal=False, width=120))
        drive = MagicMock()
        drive.list_files.return_value = sample_files(2)

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_list(last=2)

        output = capsys.readouterr().out
        assert "file-1" in output and "file-2" in output
        # Real tabs, not Rich's space-expanded ones — `cut -f4` must work.
        assert output.splitlines()[0].split("\t") == [
            "Document 1.pdf", "application/pdf", "2048", "file-1",
        ]

    def test_limit_reaches_the_tool(self):
        drive = MagicMock()
        drive.list_files.return_value = []

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_list(last=50)

        drive.list_files.assert_called_once_with(last=50)


class TestHandleSearch:

    def test_no_matches_explains_prefix_matching(self, capsys):
        """Drive matches word prefixes, so a 'no results' needs that caveat."""
        drive = MagicMock()
        drive.search_files.return_value = []

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_search("report", last=5)

        output = capsys.readouterr().out
        assert "no files matching" in output
        assert "prefix" in output
        drive.search_files.assert_called_once_with("report", last=5)


class TestResolveFileId:

    def test_number_resolves_through_cache(self):
        gdrive_commands.LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gdrive_commands.LIST_CACHE.write_text(json.dumps({"1": "file-a", "2": "file-b"}))

        assert _resolve_file_id("2") == "file-b"

    def test_full_id_passes_through(self):
        assert _resolve_file_id("1A2b3C4d5E6f7G8h") == "1A2b3C4d5E6f7G8h"

    def test_number_missing_from_cache_returns_empty(self):
        gdrive_commands.LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gdrive_commands.LIST_CACHE.write_text(json.dumps({"1": "file-a"}))

        assert _resolve_file_id("7") == ""


class TestGetPutRm:

    def test_get_downloads_resolved_id(self, capsys):
        gdrive_commands.LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gdrive_commands.LIST_CACHE.write_text(json.dumps({"1": "file-a"}))
        drive = MagicMock()
        drive.download.return_value = "Downloaded to /tmp/Report.pdf"

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_get("1", dest="/tmp")

        drive.download.assert_called_once_with("file-a", dest="/tmp")
        assert "Report.pdf" in plain(capsys.readouterr().out)

    def test_get_unknown_number_exits(self, capsys):
        drive = MagicMock()

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            with pytest.raises(typer.Exit):
                handle_gdrive_get("9")

        drive.download.assert_not_called()
        assert "No file #9" in capsys.readouterr().out

    def test_put_uploads_and_shows_the_link(self, tmp_path, capsys):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        drive = MagicMock()
        drive.upload.return_value = {
            "id": "file-1", "name": "report.pdf", "type": "application/pdf",
            "modified": "", "size": 4, "link": "https://drive.google.com/file/d/file-1/view",
        }

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_put(str(local))

        drive.upload.assert_called_once_with(str(local), name=None)
        output = plain(capsys.readouterr().out)
        assert "Uploaded" in output
        assert "drive.google.com" in output

    def test_put_missing_file_exits_before_touching_drive(self, tmp_path, capsys):
        with patch.object(gdrive_commands, "_gdrive") as guard:
            with pytest.raises(typer.Exit):
                handle_gdrive_put(str(tmp_path / "nope.pdf"))

        guard.assert_not_called()
        assert "File not found" in capsys.readouterr().out

    def test_rm_trashes_resolved_id(self, capsys):
        gdrive_commands.LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gdrive_commands.LIST_CACHE.write_text(json.dumps({"1": "file-a"}))
        drive = MagicMock()

        with patch.object(gdrive_commands, "_gdrive", return_value=drive):
            handle_gdrive_rm("1")

        drive.delete.assert_called_once_with("file-a")
        assert "trash" in plain(capsys.readouterr().out)
