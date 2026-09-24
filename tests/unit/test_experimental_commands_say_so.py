"""Preview commands say they are experimental where people meet them: `co --help`.

The 1.8.8 review found `co wiki` and `co claude` listed beside stable commands
with nothing to tell them apart, while every release note said both are
previews aimed at 1.9.0. A label in brackets would not do: Rich reads
`[experimental]` as markup and prints nothing.
"""

import re

from typer.testing import CliRunner

from connectonion.cli import main as cli_main


def listing():
    # On GitHub Actions Rich forces colour, so every row starts with ANSI codes;
    # strip them and the box before reading the command name.
    result = CliRunner().invoke(cli_main.app, ["--help"], env={"COLUMNS": "200"})
    rows = {}
    for line in result.output.splitlines():
        words = re.sub(r"\x1b\[[0-9;]*m", "", line).replace("│", " ").split()
        if len(words) > 1:
            rows.setdefault(words[0], line)
    return rows


def test_wiki_and_claude_are_marked_experimental_in_the_command_list():
    commands = listing()
    for name in ("wiki", "claude", "discord", "tiktok"):
        assert "Experimental:" in commands[name], commands.get(name)


def test_telegram_separates_the_shipped_send_from_the_new_inbox_verbs():
    row = listing()["telegram"]
    assert "send" in row and "Experimental: listen" in re.sub(r"\x1b\[[0-9;]*m", "", row)


def test_stable_commands_are_not():
    commands = listing()
    for name in ("browser", "whatsapp", "gmail"):
        assert "Experimental" not in commands[name]
