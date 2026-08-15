"""CLI routing tests for `co gmail`."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_bare_gmail_shows_inbox():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_inbox") as handler:
        result = runner.invoke(app, ["gmail"])

    assert result.exit_code == 0
    handler.assert_called_once_with()


def test_gmail_inbox_routes_flags():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_inbox") as handler:
        result = runner.invoke(app, ["gmail", "inbox", "--last", "25", "--unread"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=25, unread=True)


def test_gmail_inbox_defaults():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_inbox") as handler:
        result = runner.invoke(app, ["gmail", "inbox"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=10, unread=False)


def test_gmail_inbox_short_flags():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_inbox") as handler:
        result = runner.invoke(app, ["gmail", "inbox", "-n", "3", "-u"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=3, unread=True)


def test_gmail_read_routes_id():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_read") as handler:
        result = runner.invoke(app, ["gmail", "read", "3"])

    assert result.exit_code == 0
    handler.assert_called_once_with("3", mark_read=False)


def test_gmail_read_routes_explicit_mark_read():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_read") as handler:
        result = runner.invoke(app, ["gmail", "read", "3", "--mark-read"])

    assert result.exit_code == 0
    handler.assert_called_once_with("3", mark_read=True)


def test_gmail_send_routes_arguments():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_send") as handler:
        result = runner.invoke(app, [
            "gmail", "send", "bob@example.com", "Hi", "Body", "--cc", "carol@example.com",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "bob@example.com", "Hi", "Body", cc="carol@example.com", bcc=None
    )


def test_gmail_read_requires_an_id():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_read") as handler:
        result = runner.invoke(app, ["gmail", "read"])

    assert result.exit_code != 0
    handler.assert_not_called()


def test_gmail_reply_routes_id_and_message():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_reply") as handler:
        result = runner.invoke(app, ["gmail", "reply", "2", "Sounds good"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2", "Sounds good")


def test_gmail_reply_routes_stdin_marker():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_reply") as handler:
        result = runner.invoke(app, ["gmail", "reply", "2", "-"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2", "-")


def test_gmail_send_routes_bcc():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_send") as handler:
        result = runner.invoke(app, [
            "gmail", "send", "bob@example.com", "Hi", "-", "--bcc", "dan@example.com",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with("bob@example.com", "Hi", "-", cc=None, bcc="dan@example.com")


def test_gmail_sent_routes_limit():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_sent") as handler:
        result = runner.invoke(app, ["gmail", "sent", "--last", "7"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=7)


def test_gmail_search_routes_query_and_limit():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_search") as handler:
        result = runner.invoke(app, ["gmail", "search", "from:alice@example.com", "-n", "5"])

    assert result.exit_code == 0
    handler.assert_called_once_with("from:alice@example.com", last=5)


def test_gmail_appears_in_help():
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "gmail" in result.output


def test_gmail_help_lists_every_subcommand():
    result = runner.invoke(app, ["gmail", "--help"])

    assert result.exit_code == 0
    for command in ["inbox", "read", "reply", "send", "sent", "search"]:
        assert command in result.output


def test_unknown_gmail_subcommand_fails():
    result = runner.invoke(app, ["gmail", "archive", "3"])

    assert result.exit_code != 0
