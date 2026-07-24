"""CLI routing tests for `co outlook contact`."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_outlook_contact_add_routes_arguments():
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_contact_add"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "contact", "add",
            "Zhou Yifei", "zhouyifei0428@gmail.com",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "Zhou Yifei", "zhouyifei0428@gmail.com"
    )


def test_outlook_contact_list_routes_limit():
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_contact_list"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "contact", "list", "--last", "50",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=50)


def test_outlook_contact_search_routes_query_and_limit():
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_contact_search"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "contact", "search", "yifei", "-n", "5",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with("yifei", last=5)
