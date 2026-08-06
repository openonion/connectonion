"""Mistyping a command suggests the same fix twice.

    $ co skil
    No such command 'skil'. Did you mean 'skills'? Did you mean 'skills'?

    $ co server lst
    No such command 'lst'. Did you mean 'ls'? Did you mean 'ls'?

Two layers each append one. Click builds the message with its own suggestion,
and Typer's TyperGroup.resolve_command appends a second to whatever Click
produced:

    message = e.message.rstrip(".")
    e.message = f"{message}. Did you mean {suggestions}?"

Cosmetic, but on the path every new user takes — getting the name wrong is how
anyone learns a CLI — and it reads like the program is stuttering.

Typer's own switch turns its layer off (`suggest_commands`), leaving Click's,
which is the one that would still be there if Typer were dropped tomorrow. That
is why the fix disables ours rather than Click's.

This asserts against the real app object and every sub-app registered on it, not
against a copy of the command list: the doubling was at every level, and a test
naming one command would have passed once the top level was fixed.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app


runner = CliRunner()


def _invoke(*args):
    result = runner.invoke(app, list(args))
    # Rich wraps the error box; join so a suggestion split across lines is seen.
    return " ".join(result.output.split())


class TestOneSuggestionPerTypo:

    @pytest.mark.parametrize(
        "typo,expected",
        [("skil", "skills"), ("depoly", "deploy"), ("serv", "server")],
    )
    def test_a_top_level_typo_is_answered_once(self, typo, expected):
        output = _invoke(typo)

        assert output.count("Did you mean") == 1, output

    @pytest.mark.parametrize(
        "typo,expected", [("skil", "skills"), ("depoly", "deploy")]
    )
    def test_the_suggestion_is_still_the_right_one(self, typo, expected):
        assert expected in _invoke(typo)

    def test_a_subcommand_typo_is_answered_once(self):
        output = _invoke("server", "lst")

        assert output.count("Did you mean") == 1, output

    def test_the_subcommand_suggestion_is_right(self):
        assert "ls" in _invoke("server", "lst")


class TestEverySubAppBehavesTheSame:
    """The doubling was at every level, so every registered group must be fixed."""

    def _groups(self):
        """Every group, at every depth — `co outlook contact` is one too."""
        import click

        from connectonion.cli.main import app as main_app

        found = []

        def walk(name, command):
            if not isinstance(command, click.Group):
                return
            found.append((name, command))
            for child_name, child in command.commands.items():
                walk(f"{name} {child_name}", child)

        walk("co", typer_main_group(main_app))
        return found

    def test_there_are_sub_apps_to_check(self):
        assert len(self._groups()) > 5

    def test_a_nested_group_is_included(self):
        assert any(name.endswith("contact") for name, _ in self._groups())

    def test_none_of_them_add_a_second_suggestion(self):
        offenders = [
            name
            for name, group in self._groups()
            if getattr(group, "suggest_commands", False)
        ]

        assert offenders == [], (
            f"these still append Typer's own suggestion on top of Click's: {offenders}"
        )


def typer_main_group(typer_app):
    """The click.Group Typer builds for an app."""
    import typer.main

    return typer.main.get_command(typer_app)


class TestNothingElseAboutTheErrorChanged:

    def test_it_still_names_the_bad_command(self):
        assert "skil" in _invoke("skil")

    def test_it_still_exits_nonzero(self):
        assert runner.invoke(app, ["skil"]).exit_code != 0

    def test_a_typo_with_no_near_match_says_no_such_command(self):
        output = _invoke("zzzzzzzz")

        assert "No such command" in output
        assert "Did you mean" not in output
