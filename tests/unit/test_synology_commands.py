"""Stable, pipe-safe CLI contracts for ``co syno``."""

import json
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from connectonion.cli.commands import synology_commands
from connectonion.cli.main import app

runner = CliRunner()


def test_syno_help_lists_every_documented_command():
    result = runner.invoke(app, ["syno", "--help"])

    assert result.exit_code == 0
    for command in ("login", "status", "ls", "search", "get", "put", "share", "shares"):
        assert command in result.output


def test_syno_status_routes_json_mode():
    with patch("connectonion.cli.commands.synology_commands.handle_syno_status") as handler:
        result = runner.invoke(app, ["syno", "status", "--json"])

    assert result.exit_code == 0
    handler.assert_called_once_with(json_output=True)


def test_syno_shares_routes_limit_and_json_mode():
    with patch("connectonion.cli.commands.synology_commands.handle_syno_shares") as handler:
        result = runner.invoke(app, ["syno", "shares", "-n", "7", "--json"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=7, json_output=True)


def test_status_json_is_one_stable_document(capsys):
    nas = Mock()
    nas.status.return_value = {
        "connected": True,
        "url": "https://nas.local:5001",
        "account": "aaron",
        "session_cached": True,
        "tls_verification": False,
    }
    with patch.object(synology_commands, "_syno", return_value=nas):
        synology_commands.handle_syno_status(json_output=True)

    output = capsys.readouterr().out
    document = json.loads(output)
    assert output.count("\n") == 1
    assert document == {
        "schema_version": 1,
        "ok": True,
        "command": "co syno status",
        "data": nas.status.return_value,
        "next_command": "co syno ls --json",
    }


def test_status_json_failure_has_stable_code_and_exit(capsys):
    from connectonion.useful_tools.synology import SynologyError

    with patch.object(
        synology_commands,
        "_syno",
        side_effect=SynologyError("Synology NAS not configured", code="not_configured"),
    ):
        with pytest.raises(typer.Exit) as failure:
            synology_commands.handle_syno_status(json_output=True)

    assert failure.value.exit_code == 1
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False
    assert document["error"] == {
        "code": "not_configured",
        "message": "Synology NAS not configured",
    }
    assert document["next_command"] == "co syno login"


def test_piped_synology_listing_ends_with_one_literal_next_command(tmp_path, capsys):
    files = [{
        "path": "/home/report.pdf",
        "name": "report.pdf",
        "type": "file",
        "size": 10,
        "modified": 0,
    }]
    with patch.object(synology_commands, "LIST_CACHE", tmp_path / "list.json"):
        synology_commands._print_listing(files, "NAS")

    output = capsys.readouterr().out
    assert output.rstrip().endswith("Download the first result with: co syno get 1")
    assert output.count("co syno get 1") == 1


def test_shares_json_does_not_drop_private_fields_or_add_styling(capsys):
    nas = Mock()
    nas.list_sharing_links.return_value = [{
        "id": "share-1",
        "path": "/home/report.pdf",
        "url": "https://nas.local/sharing/abc123",
        "expires": "2026-09-30",
        "status": "valid",
    }]
    with patch.object(synology_commands, "_syno", return_value=nas):
        synology_commands.handle_syno_shares(last=20, json_output=True)

    document = json.loads(capsys.readouterr().out)
    assert document["data"][0]["id"] == "share-1"
    assert document["next_command"] == "co syno --help"
