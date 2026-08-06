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

The two arrive by different routes. Click 8.4's NoSuchCommand keeps
`possibilities` and appends its clause when the message is *rendered*; Typer
writes a copy into `.message` first. So the fix drops the text copy exactly when
the exception will render one of its own.

Switching Typer's `suggest_commands` off was the first attempt. It fixed typer
0.20 and, on 0.27 — where Click is handed no possibilities and Typer's copy is
the only clause — left plain `No such command 'skil'.` with no suggestion at
all. CI runs 0.27, this machine had 0.20, and pyproject asks for
`typer>=0.20.0`, so neither version may be assumed.

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


class TestWhichClauseSurvives:
    """The two arrive by different routes, and only one of them is text.

    Click 8.4 keeps `possibilities` on the exception and appends the clause when
    the message is rendered; Typer writes a copy into `.message` first. So the
    text copy is dropped exactly when the exception will render one itself.

    Turning Typer's `suggest_commands` off instead fixed typer 0.20 and left
    `No such command 'skil'.` with no suggestion on 0.27, where Click is handed
    no possibilities and Typer's copy is the only one. CI runs 0.27, this
    machine had 0.20, and pyproject allows both — so neither may be assumed.
    """

    def _resolve(self, possibilities, monkeypatch):
        """Drive the real _OneSuggestion.resolve_command.

        The layer underneath is stubbed to raise what Typer hands up — a message
        already carrying Typer's text copy, and Click's `possibilities` set or
        not. The production method is the thing under test; an earlier version of
        this test reimplemented it, which would have passed no matter what the
        code did.
        """
        import click
        import typer.core

        from connectonion.cli.main import _OneSuggestion

        def raise_no_such_command(self, ctx, args):
            raise click.exceptions.NoSuchCommand(
                "skil",
                message="No such command 'skil'. Did you mean 'skills'?",
                possibilities=possibilities,
            )

        monkeypatch.setattr(
            typer.core.TyperGroup, "resolve_command", raise_no_such_command
        )

        group = _OneSuggestion(name="root")
        with pytest.raises(click.UsageError) as excinfo:
            group.resolve_command(click.Context(group), ["skil"])
        return excinfo.value

    def test_the_rendered_message_has_one_clause(self, monkeypatch):
        error = self._resolve(["skills", "status"], monkeypatch)

        assert error.format_message().count("Did you mean") == 1

    def test_the_rendered_message_still_suggests_something(self, monkeypatch):
        error = self._resolve(["skills", "status"], monkeypatch)

        assert "skills" in error.format_message()

    def test_without_possibilities_the_text_copy_is_kept(self, monkeypatch):
        """typer 0.27's case: Click renders nothing, so Typer's must stay."""
        error = self._resolve(None, monkeypatch)

        assert error.format_message().count("Did you mean") == 1


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

    def test_every_group_collapses_repeats(self):
        """Not "has the flag off" — that was the version-dependent fix."""
        from connectonion.cli.main import _OneSuggestion

        offenders = [
            name for name, group in self._groups()
            if not isinstance(group, _OneSuggestion)
        ]

        assert offenders == [], (
            f"these groups were built with a plain typer.Typer, so a typo there "
            f"is still answered twice: {offenders}"
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
