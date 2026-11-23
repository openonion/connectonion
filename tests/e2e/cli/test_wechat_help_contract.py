"""`co wechat` help is printed verbatim from wechat_help.md (#3355), and true to the code.

The same contract as `co rem` (test_rem_help_contract): every page is what its command prints, every command
has a page, every flag a page names exists, and every leaf names its way back. An agent copies the example; it
must run.
"""
import re
import shlex

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.commands.wechat_help import pages
from connectonion.cli.main import app

runner = CliRunner()
WECHAT = get_command(app).commands["wechat"]


def resolve(words):
    command, rest = WECHAT, list(words)
    while rest and hasattr(command, "commands") and rest[0] in command.commands:
        command = command.commands[rest.pop(0)]
    return command, rest


def help_of(words):
    return runner.invoke(app, ["wechat", *words, "--help"], terminal_width=200).stdout


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_page_is_what_its_command_prints(name):
    assert help_of(name.split()[2:]).rstrip("\n") == pages()[name].rstrip("\n")


def test_every_command_and_subcommand_has_a_page():
    names = set(pages())
    for command in WECHAT.commands:
        assert f"co wechat {command}" in names, command
    for sub in WECHAT.commands["key"].commands:
        assert f"co wechat key {sub}" in names, sub


def test_the_root_page_lists_every_command():
    listed = set(re.findall(r"^  ([a-z][a-z-]*)\s{2,}\S", pages()["co wechat"], re.M))
    assert listed == set(WECHAT.commands)


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_command_and_flag_on_a_page_exists(name):
    for line in pages()[name].splitlines():
        for found in re.findall(r"co wechat(?: [^()\[\]|`]*)?", line):
            words = [w.rstrip(",.;:") for w in shlex.split(found.replace("...", ""))[2:]]
            command, rest = resolve([w for w in words if not re.fullmatch(r"[A-Z][A-Z_]*|<[^>]+>", w)])
            options = {"--help"} | {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}
            for word in rest:
                if word.startswith("--"):
                    assert word.split("=")[0] in options, f"{name}: {word} in: {line.strip()}"


@pytest.mark.parametrize("name", sorted(pages()))
def test_every_page_says_what_it_changes_and_has_an_example_and_a_way_back(name):
    page = pages()[name]
    assert re.search(r"^Usage:", page, re.M) and re.search(r"^Example:", page, re.M), name
    assert re.search(r"\b(Read-only|Writes)\b", page), name
    assert re.search(r"^Back:\s+co ", page, re.M) and re.search(r"^Next:\s+co ", page, re.M), name


def test_help_is_plain_in_a_pipe_no_box_drawing():
    for name in pages():
        assert not re.search(r"[╭╮╰╯│─]", help_of(name.split()[2:])), name
