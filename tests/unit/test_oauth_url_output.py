"""OAuth URLs remain one copyable line even in a narrow terminal."""

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from connectonion.cli.commands.auth_commands import _print_oauth_url


def test_a_long_oauth_url_is_not_hard_wrapped():
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + "scope=x&" * 100
    output = StringIO()
    narrow_console = Console(file=output, width=24, color_system=None)

    with patch(
        "connectonion.cli.commands.auth_commands.console", narrow_console
    ):
        _print_oauth_url(auth_url)

    lines = output.getvalue().splitlines()
    assert lines == ["    URL:", auth_url, ""]
