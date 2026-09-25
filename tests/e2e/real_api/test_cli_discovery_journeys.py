"""A fresh agent finds the right `co` command from help pages alone (#1643, #1721).

A text-only model gets a goal and only the help pages it asks for, starting at
`co --help`, and must name one command. Help is the prompt an agent reads
before it acts, so this is the test of whether that prompt works. It runs no
command and needs no account beyond the model call.

    pytest -m real_api tests/e2e/cli/../real_api/test_cli_discovery_journeys.py
"""

import re

import pytest
from typer.testing import CliRunner

from connectonion import llm_do
from connectonion.cli.discovery import check
from connectonion.cli.main import app

pytestmark = pytest.mark.real_api
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MAX_PAGES = 8
PROMPT = """You operate a CLI named `co` and can only read its help pages. Goal: {goal}
Pages you have read so far:
{pages}
Reply with exactly one line:
HELP <command path>   to read that command's --help (e.g. HELP co gmail), or
RUN <full command>    when you know the command that achieves the goal."""

JOURNEYS = [
    ("Start a new agent project from scratch", ["co create"]),
    ("Add ConnectOnion to the existing folder I am in", ["co init"]),
    ("Put my agent on my own server so it keeps running", ["co deploy", "co server"]),
    ("Receive messages that people send my agent's Feishu bot", ["co feishu listen", "co feishu receive"]),
    ("Take a screenshot of a web page in a real browser", ["co browser"]),
    ("Something is broken with my setup; diagnose it", ["co doctor"]),
    ("Check how much credit my account has left", ["co status"]),
    ("Send an email with an attachment from my own Gmail", ["co gmail send"]),
    ("Stop my agent's weekly report job from running for now", ["co schedule pause"]),
    ("See the unread emails in my Outlook", ["co outlook inbox", "co outlook"]),
    ("Give another agent permission to call my agent", ["co trust add"]),
    ("Set an API key that all my projects use", ["co env set"]),
    ("Install the skills that another person published at address 0xabc", ["co sub"]),
    pytest.param("Find a published skill someone else wrote and add it to this project", ["co sub", "co skills copy"],
                 marks=pytest.mark.xfail(reason="two steps, co sub sync then co skills copy --to-project; "
                                                "co sub sync --help names the second as its Next")),
    pytest.param("Write a brand-new skill for my agent and test it before relying on it", ["co benchmark"],
                 marks=pytest.mark.xfail(reason="the answer is a workflow (write cases, check, write "
                                                "SKILL.md, eval); this harness accepts one command")),
]


def page(path, runner=CliRunner()):
    result = runner.invoke(app, [*path.split()[1:], "--help"], terminal_width=120)
    return ANSI.sub("", result.stdout) if result.exit_code == 0 else f"(no such command: {path})"


@pytest.mark.parametrize("goal,accepted", JOURNEYS)
def test_a_fresh_agent_finds_the_command(goal, accepted, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")
    pages, answer = {"co": page("co")}, None
    for _ in range(MAX_PAGES):
        read = "\n\n".join(f"$ {path} --help\n{text}" for path, text in pages.items())
        reply = str(llm_do(PROMPT.format(goal=goal, pages=read), model="co/gemini-3.7-flash"))
        reply = reply.strip().splitlines()[0].strip("` ")
        if reply.startswith("HELP "):
            path = reply[5:].strip()
            path = path if path.startswith("co") else f"co {path}"
            pages[path] = page(path)
            continue
        answer = reply.removeprefix("RUN ").strip()
        break
    assert answer, f"no command after reading {list(pages)}"
    assert any(answer.startswith(prefix) for prefix in accepted), f"{answer!r} after reading {list(pages)}"
    words = [w for w in answer.split() if re.fullmatch(r"co|[a-z][a-z0-9_-]*", w)]
    assert check(app, " ".join(words)) is None, answer
