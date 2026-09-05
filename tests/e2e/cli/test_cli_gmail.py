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
        "bob@example.com", "Hi", "Body",
        cc="carol@example.com", bcc=None, attachments=None,
    )


def test_gmail_send_routes_repeated_attachments():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_send") as handler:
        result = runner.invoke(app, [
            "gmail", "send", "bob@example.com", "Hi", "Body",
            "-a", "one.pdf", "--attach", "two.csv",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "bob@example.com", "Hi", "Body",
        cc=None, bcc=None, attachments=["one.pdf", "two.csv"],
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
    handler.assert_called_once_with(
        "bob@example.com", "Hi", "-",
        cc=None, bcc="dan@example.com", attachments=None,
    )


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
    for command in ["inbox", "read", "reply", "send", "sent", "search", "draft"]:
        assert command in result.output


def test_gmail_draft_help_lists_every_subcommand():
    result = runner.invoke(app, ["gmail", "draft", "--help"])

    assert result.exit_code == 0
    for command in ["list", "create", "attach", "remove", "replace", "preview", "send"]:
        assert command in result.output


def test_gmail_draft_list_routes_limit():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_list") as handler:
        result = runner.invoke(app, ["gmail", "draft", "list", "-n", "7"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=7)


def test_gmail_draft_create_routes_headers():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_create") as handler:
        result = runner.invoke(app, [
            "gmail", "draft", "create", "r@example.com", "Report", "Body",
            "--cc", "c@example.com", "--bcc", "b@example.com",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "r@example.com", "Report", "Body", cc="c@example.com", bcc="b@example.com"
    )


def test_gmail_draft_attach_routes_drive_link():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_attach") as handler:
        result = runner.invoke(app, [
            "gmail", "draft", "attach", "2", "3", "--drive", "--link",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with("2", "3", drive=True, link=True)


def test_gmail_draft_remove_routes_attachment_number():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_remove") as handler:
        result = runner.invoke(app, ["gmail", "draft", "remove", "2", "1"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2", 1)


def test_gmail_draft_replace_routes_drive_source():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_replace") as handler:
        result = runner.invoke(app, [
            "gmail", "draft", "replace", "2", "1", "drive-file", "--drive",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with("2", 1, "drive-file", drive=True)


def test_gmail_draft_preview_routes_id():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_preview") as handler:
        result = runner.invoke(app, ["gmail", "draft", "preview", "2"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2")


def test_gmail_draft_send_routes_id_without_a_bypass_flag():
    with patch("connectonion.cli.commands.gmail_commands.handle_gmail_draft_send") as handler:
        result = runner.invoke(app, ["gmail", "draft", "send", "2"])

    assert result.exit_code == 0
    handler.assert_called_once_with("2")

    help_result = runner.invoke(app, ["gmail", "draft", "send", "--help"])
    assert "--yes" not in help_result.output


def test_unknown_gmail_subcommand_fails():
    result = runner.invoke(app, ["gmail", "archive", "3"])

    assert result.exit_code != 0
