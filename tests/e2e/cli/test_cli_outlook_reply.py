"""CLI routing tests for `co outlook reply`."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_outlook_reply_routes_without_attachments():
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_reply"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "reply", "3", "Sounds good",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with("3", "Sounds good", attachments=None, at=None, cc=None, bcc=None, listing=None)


def test_outlook_reply_collects_repeated_attach_flags():
    """--attach and -a are repeatable, like `co outlook send`."""
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_reply"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "reply", "3", "Both attached",
            "--attach", "report.pdf", "-a", "chart.png",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "3", "Both attached",
        attachments=["report.pdf", "chart.png"], at=None, cc=None, bcc=None, listing=None,
    )


def test_outlook_reply_routes_attachments_with_schedule():
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_reply"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "reply", "3", "Tomorrow",
            "-a", "report.pdf", "--at", "+2h",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "3", "Tomorrow", attachments=["report.pdf"], at="+2h", cc=None, bcc=None, listing=None,
    )


def test_outlook_reply_routes_cc_and_bcc():
    """#1247: a copied third person rides on the threaded reply, not a new send."""
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_reply"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "reply", "3", "Looping in Sam",
            "--cc", "sam@example.com", "--bcc", "me@example.com",
        ])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        "3", "Looping in Sam", attachments=None, at=None,
        cc="sam@example.com", bcc="me@example.com", listing=None,
    )


def test_outlook_reply_passes_the_listing_a_number_came_from():
    """#1754: a row number travels with the token of the listing that showed it."""
    with patch(
        "connectonion.cli.commands.outlook_commands.handle_outlook_reply"
    ) as handler:
        result = runner.invoke(app, [
            "outlook", "reply", "3", "Sounds good", "--listing", "a" * 32,
        ])

    assert result.exit_code == 0
    assert handler.call_args.kwargs["listing"] == "a" * 32
