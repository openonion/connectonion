"""Bare `co` prints a hand-written command list under the heading "Commands:".

It names 16. The CLI registers 24:

    ai  announce  call  reset  server  setup  skills  sub

are all real and none of them appear. `co ai`, `co call`, `co server`,
`co skills` and `co sub` are the network story this release is about, and the
first screen a new user sees does not mention them.

Unlike docs/connectonion.md's template list (#724) or the model lists (#726),
nothing here promises something that does not exist — `co --help` is generated
from the real commands and shows all 24. So this is a curation choice, not a
broken promise, and which of the eight deserve the first screen is a product
question rather than a bug.

What is fixable without answering that question: say the list is a selection,
and say where the rest are. And lock the invariant that is true today and is the
one that would actually hurt — that every name on the first screen is a command
you can run. That is the failure mode this release has hit four times.
"""

import inspect
import re

import pytest
import typer.main
from typer.testing import CliRunner

from connectonion.cli import main as cli_main


runner = CliRunner()


def _listed_commands():
    """The names printed by _show_help, as the user reads them."""
    return set(re.findall(r"\[green\]([a-z-]+)\[/green\]",
                          inspect.getsource(cli_main._show_help)))


def _real_commands():
    return set(typer.main.get_command(cli_main.app).commands)


class TestEveryNameOnTheFirstScreenIsReal:
    """The #724 failure mode, applied here before it happens."""

    def test_nothing_is_advertised_that_cannot_be_run(self):
        phantom = _listed_commands() - _real_commands()

        assert phantom == set(), (
            f"bare `co` names commands that do not exist: {sorted(phantom)}"
        )

    def test_the_list_is_not_empty(self):
        assert len(_listed_commands()) > 5


class TestItSaysWhereTheRestAre:

    @pytest.fixture
    def output(self):
        return " ".join(runner.invoke(cli_main.app, []).output.split())

    def test_it_does_not_claim_to_be_the_whole_list(self, output):
        # "Commands:" reads as all of them while eight are missing.
        assert "Commands:" not in output or "Common commands:" in output

    def test_it_points_at_the_full_list(self, output):
        assert "co --help" in output

    def test_the_full_list_really_does_have_them_all(self):
        """The pointer is only honest if --help is complete."""
        result = runner.invoke(cli_main.app, ["--help"])
        rendered = " ".join(result.output.split())

        missing = [c for c in _real_commands() if c not in rendered]
        assert missing == [], f"co --help omits {missing}"


class TestTheFirstScreenStillWorks:

    @pytest.fixture
    def output(self):
        return " ".join(runner.invoke(cli_main.app, []).output.split())

    def test_it_still_leads_with_create(self, output):
        assert "co create" in output

    def test_it_still_shows_the_docs_link(self, output):
        assert "docs.connectonion.com" in output

    def test_it_exits_zero(self):
        assert runner.invoke(cli_main.app, []).exit_code == 0
