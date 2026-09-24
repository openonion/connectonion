"""Preview commands say they are experimental where people meet them: `co --help`.

The 1.8.8 review found `co wiki` and `co claude` listed beside stable commands
with nothing to tell them apart, while every release note said both are
previews aimed at 1.9.0. A label in brackets would not do: Rich reads
`[experimental]` as markup and prints nothing.
"""

from typer.testing import CliRunner

from connectonion.cli import main as cli_main


def listing():
    result = CliRunner().invoke(cli_main.app, ["--help"], env={"COLUMNS": "200"})
    return {line.split()[1]: line for line in result.output.splitlines()
            if line.startswith("│ ") and len(line.split()) > 2}


def test_wiki_and_claude_are_marked_experimental_in_the_command_list():
    commands = listing()
    for name in ("wiki", "claude"):
        assert "Experimental:" in commands[name], commands.get(name)


def test_stable_commands_are_not():
    commands = listing()
    for name in ("browser", "whatsapp", "gmail"):
        assert "Experimental" not in commands[name]
