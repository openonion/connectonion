"""`co wiki` help is the agreed design (#1656), printed verbatim, and true to the code.

The pages were written and reviewed before the code, so the test runs in that
direction: every page in wiki_help.md is what its command prints, every
command has a page, and every command and flag a page shows exists. A page
that names a flag the parser does not have is the failure #1643 exists to
stop -- an agent copies the example, and it does not run.
"""

import re
import shlex

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.commands.wiki_help import pages
from connectonion.cli.main import app

runner = CliRunner()
WIKI = get_command(app).commands["wiki"]
ROOT_COMMANDS = ["init", "investigate", "open", "list", "show", "search", "start", "stop", "status",
                 "sync", "sources", "config", "logs", "doctor"]
ADVANCED = ["scan", "map-skills", "stub", "reflect", "reflections", "propose", "review", "abstract", "capture"]
OLD_NAMES = {"unfinished": "investigate", "people": "list people --aliases", "daily": "sync",
             "subscriptions": "sources", "subscribe": "sources add", "unsubscribe": "sources remove",
             "route": "config set", "usage": "logs --usage"}


def resolve(words):
    """The click command a `co wiki ...` word list reaches, and the words left over."""
    command, rest = WIKI, list(words)
    while rest and hasattr(command, "commands") and rest[0] in command.commands:
        command = command.commands[rest.pop(0)]
    return command, rest


def help_of(words):
    return runner.invoke(app, ["wiki", *words, "--help"], terminal_width=200).stdout


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_page_is_what_its_command_prints(name):
    words = name.split()[2:]
    assert help_of(words).rstrip("\n") == pages()[name].rstrip("\n")


def test_every_command_and_subcommand_has_a_page():
    names = set(pages())
    for command in [*ROOT_COMMANDS, *ADVANCED, "advanced"]:
        assert f"co wiki {command}" in names, command
    for group in ("sources", "config"):
        for sub in WIKI.commands[group].commands:
            assert f"co wiki {group} {sub}" in names, (group, sub)


def test_the_root_page_lists_exactly_the_visible_commands():
    listed = re.findall(r"^  ([a-z][a-z-]*)\s{2,}\S", pages()["co wiki"], re.M)
    visible = [name for name, command in WIKI.commands.items() if not command.hidden]
    assert listed == ROOT_COMMANDS
    assert sorted(visible) == sorted(ROOT_COMMANDS)
    assert re.findall(r"^  ([a-z][a-z-]*)\s{2,}\S", pages()["co wiki advanced"], re.M) == ADVANCED


def _commands_in(text):
    """Every `co wiki ...` a page asks the reader to type, placeholders dropped."""
    for line in text.splitlines():
        for found in re.findall(r"co wiki(?: [^()\[\]|`]*)?", line):
            words = [w.rstrip(",.;") for w in shlex.split(found.replace("...", "").replace("\\", ""))[2:]]
            yield line, [w for w in words if not re.fullmatch(r"[A-Z][A-Z_]*|<[^>]+>", w)]


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_command_and_flag_on_a_page_exists(name):
    for line, words in _commands_in(pages()[name]):
        command, rest = resolve(words)
        options = {"--help"} | {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}
        for word in rest:
            if word.startswith("--"):
                assert word.split("=")[0] in options, f"{name}: {word} in: {line.strip()}"


@pytest.mark.parametrize("name", sorted(set(pages()) - {"co wiki"}))
def test_every_leaf_names_its_way_back(name):
    back = re.search(r"^Back:\s+(co wiki[^\n]*?)(?: --help)?$", pages()[name], re.M)
    assert back, name
    parent = back.group(1).strip()
    assert parent in pages(), (name, parent)


def test_help_never_runs_the_command(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.wiki.investigate.investigate", lambda *a, **k: pytest.fail("model called"))
    result = runner.invoke(app, ["wiki", "--root", str(tmp_path), "investigate", "people", "--help"])
    assert result.exit_code == 0 and result.stdout.startswith("co wiki investigate —")
    assert not (tmp_path / ".state").exists()


@pytest.mark.parametrize("old,new", sorted(OLD_NAMES.items()))
def test_an_old_name_still_works_and_says_its_new_name(tmp_path, old, new):
    args = {"subscribe": ["codex"], "unsubscribe": ["codex"]}.get(old, [])
    result = runner.invoke(app, ["wiki", "--root", str(tmp_path), old, *args])
    assert f"is now `co wiki --root {tmp_path} {new.split(' --')[0]}" in result.stderr \
        or f"is now `co wiki --root {tmp_path} {new}" in result.stderr, result.stderr


def test_a_wrapper_sees_its_own_name_in_help(monkeypatch):
    monkeypatch.setenv("CO_WIKI_PROGRAM", "remi")
    output = help_of(["investigate"])
    assert output.startswith("remi investigate —") and "co wiki" not in output
