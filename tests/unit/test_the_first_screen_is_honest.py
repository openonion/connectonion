"""Bare `co` prints the register, and the register is complete.

History: the first screen used to be a hand-typed list under "Common
commands:". It named 16 of 24 — `ai`, `announce`, `call`, `reset`, `server`,
`setup`, `skills` and `sub` were all real and absent — and the only defence
was a test that every *listed* name existed, which says nothing about the
names that were not listed. A hand-typed list has no way to notice the ninth
omission.

The list is now read from the Typer app itself, so the property to lock is
the other direction: every registered top-level command is on the first
screen, with the summary its own --help carries. Same for the two pointers
below it, `co commands` and `co <command> --help`, which are how the reader
gets from this screen to everything else.
"""

import re

import pytest
import typer.main
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.discovery import command_tree


runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _real_commands():
    return set(typer.main.get_command(cli_main.app).commands)


def _bare_co() -> str:
    """What bare `co` prints, colour codes removed — Rich still emits them
    under CliRunner, and `[32mai[0m` is not the word `ai`."""
    return _ANSI.sub("", runner.invoke(cli_main.app, []).output)


@pytest.fixture
def output():
    return " ".join(_bare_co().split())


class TestTheFirstScreenIsTheRegister:

    def test_every_registered_command_is_on_it(self, output):
        missing = [c for c in sorted(_real_commands()) if f" {c} " not in f" {output} "]
        assert missing == [], f"bare `co` omits registered commands: {missing}"

    def test_each_carries_its_own_summary(self, output):
        for entry in command_tree(cli_main.app):
            if entry.path.count(" ") == 1:
                assert entry.summary in output, (
                    f"{entry.path} is listed without its --help summary {entry.summary!r}"
                )

    def test_it_no_longer_calls_itself_a_selection(self, output):
        assert "Common commands:" not in output
        assert "Commands:" in output


class TestItSaysWhereTheRestAre:

    def test_it_points_at_the_subcommand_list(self, output):
        assert "co commands" in output

    def test_it_points_at_per_command_help(self, output):
        assert "co <command> --help" in output

    def test_the_full_list_really_does_have_them_all(self):
        """The pointer is only honest if --help is complete."""
        result = runner.invoke(cli_main.app, ["--help"])
        rendered = " ".join(result.output.split())

        missing = [c for c in _real_commands() if c not in rendered]
        assert missing == [], f"co --help omits {missing}"


class TestTheFirstScreenStillWorks:

    def test_it_still_leads_with_create(self, output):
        assert "co create" in output

    def test_it_still_shows_the_docs_link(self, output):
        assert "docs.connectonion.com" in output

    def test_it_exits_zero(self):
        assert runner.invoke(cli_main.app, []).exit_code == 0

    def test_one_line_per_command_even_when_piped(self):
        """Rich wraps at 80 columns in a pipe; a wrapped summary reads as two
        commands. Every non-blank line under Commands: must start with a name."""
        lines = _bare_co().splitlines()
        start = lines.index("Commands:") + 1
        listing = []
        for line in lines[start:]:
            if not line.strip():
                break
            listing.append(line)
        assert len(listing) == len(_real_commands())
        for line in listing:
            assert line.startswith("  ") and line.split()[0] in _real_commands(), line


def test_first_screen_explains_explicit_project_configuration():
    output = " ".join(_bare_co().split())
    assert "~/.co/keys.env" in output
    assert "co init ./" in output
    assert "co --env-file .env <command>" in output
