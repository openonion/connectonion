"""A fresh agent finds the right `co` command from help pages alone (#1643, #1721).

A text-only model gets a goal and only the help pages it asks for, starting at
`co --help`, and must name one command. It runs no command. The walk is the
same code `co audit` uses (connectonion/cli/audit.py).

    pytest -m real_api tests/e2e/real_api/test_cli_discovery_journeys.py
"""

import re

import pytest

from connectonion.cli import audit
from connectonion.cli.discovery import check
from connectonion.cli.main import app
from connectonion.core.usage import DEFAULT_MODEL

pytestmark = pytest.mark.real_api

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


@pytest.mark.parametrize("goal,accepted", JOURNEYS)
def test_a_fresh_agent_finds_the_command(goal, accepted):
    answer, read = audit.walk(app, goal, DEFAULT_MODEL)
    assert answer, f"no command after reading {read}"
    assert any(answer.startswith(prefix) for prefix in accepted), f"{answer!r} after reading {read}"
    words = [w for w in answer.split() if re.fullmatch(r"co|[a-z][a-z0-9_-]*", w)]
    assert check(app, " ".join(words)) is None, answer
