"""#3026: revoking a requester stops their running turn, connected or not.

The socket check only runs when the requester's socket sends a frame. A
requester who closed the tab sends none, so their turn has to be stopped by
the Host itself, before its next tool or model step.
"""
import pytest

from connectonion import Agent
from connectonion.cli.commands.trust_commands import handle_trust_block
from connectonion.network.host import server
from connectonion.network.host.session import SessionStorage
from connectonion.network.io.websocket import WebSocketIO
from connectonion.network.trust import TrustAgent
from tests.utils.mock_helpers import LLMResponseBuilder, MockLLM

CALLER = "0x" + "c4" * 32
HOST = "0x" + "a1" * 32


def hosted_turn(tmp_path, monkeypatch, responses):
    """Run one requester turn through the Host's real route handlers."""
    monkeypatch.chdir(tmp_path)
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    trust = TrustAgent("careful", co_dir=co_dir)
    trust.promote_to_contact(CALLER)
    ran = []

    def first_step() -> str:
        """Do the first step."""
        ran.append("first")
        # The admin revokes while the turn runs. Nothing arrives from the
        # requester afterwards: no socket frame will ever trigger the old check.
        handle_trust_block(CALLER)
        return "first done"

    def second_step() -> str:
        """Do the second step."""
        ran.append("second")
        return "second done"

    llm = MockLLM(responses=responses)
    create_agent = lambda: Agent("host", llm=llm, tools=[first_step, second_step],
                                 co_dir=co_dir, log=False, quiet=True)
    routes = server._create_route_handlers(create_agent, {"name": "host", "address": HOST},
                                           3600, trust, {})
    return routes, SessionStorage(co_dir / "sessions.jsonl"), ran, llm


@pytest.mark.parametrize("batched", [False, True])
def test_revoked_requester_turn_stops_before_the_next_step_without_a_socket_frame(
        tmp_path, monkeypatch, capsys, batched):
    build = LLMResponseBuilder
    if batched:
        responses = [build.multi_tool_response([{"name": "first_step", "arguments": {}},
                                                {"name": "second_step", "arguments": {}}]),
                     build.text_response("finished")]
    else:
        responses = [build.tool_call_response("first_step", {}, "call_1"),
                     build.tool_call_response("second_step", {}, "call_2"),
                     build.text_response("finished")]
    routes, storage, ran, llm = hosted_turn(tmp_path, monkeypatch, responses)

    routes["ws_input"](storage, "do both steps", WebSocketIO(), {"session_id": "s1"},
                       requester_address=CALLER)

    assert ran == ["first"]
    # The next model step never reached the model.
    assert llm._call_count == 1
    assert "access was revoked" in capsys.readouterr().out


def test_requester_who_keeps_access_runs_every_step(tmp_path, monkeypatch):
    build = LLMResponseBuilder
    routes, storage, ran, llm = hosted_turn(tmp_path, monkeypatch, [
        build.tool_call_response("second_step", {}, "call_1"),
        build.tool_call_response("second_step", {}, "call_2"),
        build.text_response("finished")])

    result = routes["ws_input"](storage, "do it twice", WebSocketIO(), {"session_id": "s1"},
                                requester_address=CALLER)

    assert ran == ["second", "second"]
    assert result["result"] == "finished"


def test_revoked_requester_without_an_io_fails_the_turn(tmp_path, monkeypatch):
    """An HTTP turn has no interrupt mailbox; it must still not take another step."""
    build = LLMResponseBuilder
    routes, storage, ran, llm = hosted_turn(tmp_path, monkeypatch, [
        build.tool_call_response("first_step", {}, "call_1"),
        build.text_response("finished")])

    with pytest.raises(PermissionError, match="revoked"):
        routes["input"](storage, "do it", {"session_id": "s1"}, requester_address=CALLER)

    assert ran == ["first"]
    assert llm._call_count == 1


def test_a_shared_agent_gets_the_check_once(tmp_path, monkeypatch):
    """host(agent) reuses one Agent for every turn; the check must not pile up."""
    build = LLMResponseBuilder
    monkeypatch.chdir(tmp_path)
    co_dir = tmp_path / ".co"
    trust = TrustAgent("careful", co_dir=co_dir)
    agent = Agent("host", llm=MockLLM(responses=[build.text_response("one"), build.text_response("two")]),
                  co_dir=co_dir, log=False, quiet=True)
    routes = server._create_route_handlers(lambda: agent, {"name": "host", "address": HOST}, 3600, trust, {})
    storage = SessionStorage(co_dir / "sessions.jsonl")
    routes["ws_input"](storage, "first", WebSocketIO(), {"session_id": "s1"}, requester_address=CALLER)
    counts = {event: len(agent.events[event]) for event in ("before_llm", "before_each_tool")}
    routes["ws_input"](storage, "second", WebSocketIO(), {"session_id": "s2"}, requester_address=CALLER)
    assert {event: len(agent.events[event]) for event in counts} == counts
