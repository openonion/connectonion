"""CLI routing tests for `co gdrive`."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_bare_gdrive_lists_files():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_list") as handler:
        result = runner.invoke(app, ["gdrive"])

    assert result.exit_code == 0
    handler.assert_called_once_with()


def test_gdrive_list_routes_limit():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_list") as handler:
        result = runner.invoke(app, ["gdrive", "list", "--last", "50"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=50)


def test_gdrive_list_defaults():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_list") as handler:
        result = runner.invoke(app, ["gdrive", "list"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=20)


def test_gdrive_search_routes_query_and_limit():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_search") as handler:
        result = runner.invoke(app, ["gdrive", "search", "report", "-n", "5"])

    assert result.exit_code == 0
    handler.assert_called_once_with("report", last=5)


def test_gdrive_get_routes_id_and_destination():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_get") as handler:
        result = runner.invoke(app, ["gdrive", "get", "3", "--to", "/tmp"])

    assert result.exit_code == 0
    handler.assert_called_once_with("3", dest="/tmp")


def test_gdrive_get_defaults_to_cwd():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_get") as handler:
        result = runner.invoke(app, ["gdrive", "get", "3"])

    assert result.exit_code == 0
    handler.assert_called_once_with("3", dest=".")


def test_gdrive_put_routes_path_and_name():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_put") as handler:
        result = runner.invoke(app, ["gdrive", "put", "report.pdf", "--name", "Q3.pdf"])

    assert result.exit_code == 0
    handler.assert_called_once_with("report.pdf", name="Q3.pdf")


def test_gdrive_rm_routes_id():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_rm") as handler:
        result = runner.invoke(app, ["gdrive", "rm", "2"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2")


def test_gdrive_requires_an_id_to_get():
    with patch("connectonion.cli.commands.gdrive_commands.handle_gdrive_get") as handler:
        result = runner.invoke(app, ["gdrive", "get"])

    assert result.exit_code != 0
    handler.assert_not_called()


def test_gdrive_appears_in_help():
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "gdrive" in result.output


def test_gdrive_help_lists_every_subcommand():
    result = runner.invoke(app, ["gdrive", "--help"])

    assert result.exit_code == 0
    for command in ["list", "search", "get", "put", "rm"]:
        assert command in result.output


def test_unknown_gdrive_subcommand_fails():
    result = runner.invoke(app, ["gdrive", "sync"])

    assert result.exit_code != 0
