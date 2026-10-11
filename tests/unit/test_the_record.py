"""The record: one append-only line for everything the agent did or declined (#2408).

Context over control means most things are done rather than asked about, so
the record is how the owner finds out what was done. Before it, an EXEC left no
trace at all, a tool call in a chat turn lived only in a session that expires,
and a trust change was written nowhere.
"""

import json

import pytest
from typer.testing import CliRunner

from connectonion import Agent, approvals
from connectonion.core.tool_executor import execute_single_tool
from connectonion.network.host.server import _make_ws_exec
from connectonion.network.trust import TrustAgent
from connectonion.network.trust.tools import block, promote_to_contact
from connectonion.useful_plugins.tool_approval import tool_approval
from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
from tests.utils.mock_helpers import MockLLM

CONTACT = "0x" + "3" * 64
STRANGER = "0x" + "4" * 64


def greet(name: str) -> str:
    """Say hello."""
    return f"hello {name}"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co").mkdir()
    return tmp_path / ".co"


def _lines(co_dir):
    return [json.loads(line) for line in (co_dir / approvals.RECORD).read_text().splitlines()]


def _call(agent, tool, args):
    return execute_single_tool(tool_name=tool, tool_args=args, tool_id="c1",
                               tools=agent.tools, agent=agent, logger=agent.logger)


def _chat_turn(agent, mode="auto"):
    agent.current_session = {"messages": [], "trace": [], "turn": 1, "iteration": 1,
                             "mode": mode, "permissions": {}, "session_id": "s1",
                             "via": "feishu",
                             "requester": {"address": "feishu:ou_1", "level": "open"}}


def test_a_turns_tool_calls_land_in_the_record(project):
    agent = Agent("t", tools=[greet], llm=MockLLM(), co_dir=project)
    _chat_turn(agent)

    _call(agent, "greet", {"name": "bob"})

    [line] = _lines(project)
    assert line["path"] == "turn"
    assert line["who"] == "chat:feishu:ou_1"
    assert line["tool"] == "greet"
    assert line["decision"] == "done" and line["outcome"] == "success"
    assert line["session"] == "s1"


def test_a_declined_call_is_recorded_as_declined(project):
    agent = Agent("t", tools=[greet], plugins=[tool_approval], llm=MockLLM(), co_dir=project)
    _chat_turn(agent, mode="read-only")  # nobody to ask, so the ungranted call is refused

    _call(agent, "greet", {"name": "bob"})

    [line] = _lines(project)
    assert line["decision"] == "declined"
    assert line["reason"]


def _exec(project, tool, caller):
    trust = TrustAgent("careful", co_dir=project)
    promote_to_contact(CONTACT, project)
    permissions = {"greet": {"allowed": True, "source": "config", "reason": "test"}}
    handle = _make_ws_exec(lambda: Agent("t", tools=[greet], llm=MockLLM()), permissions, trust, project)
    return handle(tool, {"name": "bob"}, caller)


def test_every_exec_lands_in_the_record(project):
    assert _exec(project, "greet", CONTACT)["status"] == "success"
    assert _exec(project, "greet", STRANGER)["status"] == "error"

    execs = [line for line in _lines(project) if line["path"] == "exec"]
    assert [(e["who"], e["decision"]) for e in execs] == [
        (f"key:{CONTACT}", "done"),
        (f"key:{STRANGER}", "declined"),
    ]
    assert "forbidden" in execs[1]["reason"]


def test_trust_changes_are_recorded_with_their_reason(project):
    promote_to_contact(CONTACT, project)
    promote_to_contact(CONTACT, project)  # already a contact: no change, no line
    block(STRANGER, reason="spam", co_dir=project)

    assert [(e["tool"], e["who"], e["reason"]) for e in _lines(project)] == [
        ("add to contacts", f"key:{CONTACT}", None),
        ("add to blocklist", f"key:{STRANGER}", "spam"),
    ]


def test_the_agent_cannot_write_its_own_record(project):
    allowed, reason = is_tool_permitted(
        "write", {"path": ".co/approvals.jsonl", "content": ""},
        {"write": {"allowed": True, "source": "config", "reason": "coding agent"}})
    assert not allowed
    assert "approvals.jsonl" in reason or "control" in reason.lower()


def test_co_approvals_filters_by_who(project):
    from connectonion.cli.main import app

    promote_to_contact(CONTACT, project)
    block(STRANGER, reason="spam", co_dir=project)

    result = CliRunner().invoke(app, ["approvals", "--who", STRANGER, "--json"])

    assert result.exit_code == 0, result.output
    assert [e["who"] for e in json.loads(result.stdout)] == [f"key:{STRANGER}"]
