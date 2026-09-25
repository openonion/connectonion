"""`co --help` starts where a new user starts, and bare `co` labels previews the same way.

Found on 1.8.8b7 by a first-run tester: the only guidance block in
`co --help` was "Build or improve a skill: 1. co benchmark --help…", which is
step five for someone who has not made an agent yet, while bare `co` opened
with Quick Start. And bare `co` listed discord, telegram's inbox verbs and
wiki with unlabelled summaries, where `co --help` said "Experimental:".
"""

import re

from typer.testing import CliRunner

from connectonion.cli import main as cli_main

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _output(args):
    result = CliRunner().invoke(cli_main.app, args, env={"COLUMNS": "200"})
    return _ANSI.sub("", result.output)


def test_help_has_a_start_block_before_the_benchmark_one():
    text = _output(["--help"])

    assert "Start here" in text
    start = text.index("Start here")
    assert start < text.index("Build or improve a skill")
    for command in ("co init", "co create my-agent", "co auth"):
        assert command in text[start:text.index("Build or improve a skill")], command


def _bare_rows():
    rows = {}
    lines = _output([]).splitlines()
    for line in lines[lines.index("Commands:") + 1:]:
        if not line.strip():
            break
        rows[line.split()[0]] = line
    return rows


def test_bare_co_labels_the_same_commands_experimental():
    rows = _bare_rows()
    for name in ("wiki", "claude", "discord", "tiktok"):
        assert "Experimental:" in rows[name], rows[name]
    assert "plus experimental listen" in rows["telegram"], rows["telegram"]


def test_bare_co_does_not_label_stable_commands():
    rows = _bare_rows()
    for name in ("browser", "whatsapp", "gmail", "create"):
        assert "Experimental" not in rows[name], rows[name]


def test_bare_co_and_help_give_the_same_start_and_nothing_wraps():
    # 1.8.8b9: `co --help` said init/create/auth, bare `co` said
    # init/create/run/benchmark/eval, and at 80 columns bare co's eval line
    # wrapped into a stray "rerun" on a line of its own.
    narrow = _ANSI.sub("", CliRunner().invoke(cli_main.app, [], env={"COLUMNS": "80"}).output)
    helped = _output(["--help"])

    for title, lines in cli_main.START_HERE:
        assert title in narrow and title in helped
        for line in lines:
            assert line in narrow, line
            assert line in helped, line
    assert "Quick Start" not in narrow
