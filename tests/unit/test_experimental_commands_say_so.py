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
    assert "send, plus experimental listen" in re.sub(r"\x1b\[[0-9;]*m", "", row)


def test_co_commands_and_each_group_help_say_it_too():
    # `co commands` reads each group's own help, not the --help listing's
    # short_help, so a label only in short_help vanished from the register
    # and from `co discord --help` (found testing 1.8.8b7).
    register = CliRunner().invoke(cli_main.app, ["commands"]).output
    lines = {line.split("  ")[0].strip(): line for line in register.splitlines() if line.startswith("co ")}
    for name in ("claude", "discord", "tiktok"):
        assert "Experimental" in lines[f"co {name}"], lines.get(f"co {name}")
        page = CliRunner().invoke(cli_main.app, [name, "--help"], env={"COLUMNS": "200"}).output
        assert "Experimental" in re.sub(r"\x1b\[[0-9;]*m", "", page)
    assert "plus experimental" in lines["co telegram"]


def test_stable_commands_are_not():
    commands = listing()
    for name in ("browser", "whatsapp", "gmail"):
        assert "Experimental" not in commands[name]


def test_the_wiki_overview_and_claude_run_pages_say_it_too():
    # `co --help` said Experimental, but `co wiki`, `co wiki --help` and
    # `co claude run --help` -- the pages people actually read -- never did.
    for args in (["wiki"], ["wiki", "--help"], ["claude", "run", "--help"]):
        page = CliRunner().invoke(cli_main.app, args, env={"COLUMNS": "200"}).output
        assert "Experimental" in re.sub(r"\x1b\[[0-9;]*m", "", page), args
