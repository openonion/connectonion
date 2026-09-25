"""Each hard rule in `co audit` fails the page it exists to catch (#1735).

A tiny CLI with one defect per command, so a rule that silently stops firing
turns this red, not the real CLI's audit green.
"""

import typer

from connectonion.cli import audit
from connectonion.cli.typer_groups import _OneSuggestion, name_the_way_back

app = typer.Typer(cls=_OneSuggestion)
mail = typer.Typer(cls=_OneSuggestion, help="Mail. Read-only.", epilog="Example:  co mail good")
app.add_typer(mail, name="mail")


@mail.command("good", epilog="Example:  co mail good --limit 3")
def good(limit: int = typer.Option(5, "--limit")):
    """List mail. Read-only."""


@mail.command("no-example")
def no_example():
    """List mail. Read-only."""


@mail.command("no-effect", epilog="Example:  co mail no-effect")
def no_effect():
    """Do a thing to mail."""


@mail.command("bad-flag", epilog="Example:  co mail bad-flag --nope")
def bad_flag():
    """List mail. Read-only."""


@mail.command("other-example", epilog="Example:  co mail good")
def other_example():
    """List mail. Read-only."""


@mail.command("bad-ref", epilog="Example:  co mail bad-ref  |  Next: co mail missing")
def bad_ref():
    """List mail. Read-only."""


@mail.command("private", epilog="Example:  co mail private /Users/aaron/secret.txt")
def private(path: str = typer.Argument(...)):
    """Send a file. Sends it."""


@mail.command("writes", epilog="Example:  co mail writes")
def writes():
    """List mail. Read-only."""


name_the_way_back(app)


def findings(path):
    return {f.check for f in audit.check_page(app, path)}


def test_a_page_that_meets_every_rule_passes():
    assert findings("co mail good") == set()


def test_each_rule_fails_the_page_it_is_for():
    assert findings("co mail no-example") == {"example"}
    assert findings("co mail no-effect") == {"side_effect"}
    assert findings("co mail bad-flag") == {"flags"}
    assert findings("co mail other-example") == {"self_example"}
    assert "refs" in findings("co mail bad-ref")
    assert findings("co mail private") == {"private"}


def test_help_that_writes_a_file_is_caught(monkeypatch):
    real = audit.CliRunner.invoke

    def invoke_and_write(self, cli, args, **kw):
        open("left-behind.txt", "w").close()
        return real(self, cli, args, **kw)

    monkeypatch.setattr(audit.CliRunner, "invoke", invoke_and_write)
    assert "writes" in findings("co mail writes")


def test_a_page_with_no_way_back_is_caught():
    bare = typer.Typer(cls=_OneSuggestion)

    @bare.command("x", epilog="Example:  co x")
    def x():
        """Do x. Read-only."""

    @bare.command("y", epilog="Example:  co y")
    def y():
        """Do y. Read-only."""

    assert {f.check for f in audit.check_page(bare, "co x")} == {"back"}


def test_a_subcommand_missing_from_its_parents_page_is_caught(monkeypatch):
    """Every group page lists its children, so every command is reachable from `co --help`."""
    real = audit.help_page

    def page_without_no_example(cli, path):
        code, text, wrote = real(cli, path)
        return code, text.replace("no-example", "") if path == "co mail" else text, wrote

    monkeypatch.setattr(audit, "help_page", page_without_no_example)
    assert {f.check for f in audit.check_page(app, "co mail")} == {"lists_children"}
