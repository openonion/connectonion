"""Unit tests for connectonion/useful_tools/codex_acp.py (ACP backend).

The ACPClient is replaced with a fake that drives the on_event / on_permission
callbacks, so these run without spawning codex-acp. A real-binary end-to-end
lives in prototypes/codex_acp/test_real_codex_acp.py and
tests/e2e/real_api/test_real_codex.py.
"""

import importlib
import json
from unittest.mock import patch

from connectonion.useful_tools import codex_acp as acp
from connectonion.useful_tools.codex import codex

ALLOW_REJECT = [
    {"optionId": "allow-1", "name": "Allow", "kind": "allow_once"},
    {"optionId": "reject-1", "name": "Reject", "kind": "reject_once"},
]


class FakeACPClient:
    """Stand-in ACPClient that simulates one codex-acp turn via callbacks."""
    last = None

    def __init__(self, command, cwd=None, on_event=None, on_permission=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_permission = on_permission
        self.calls = []
        self.permission_result = None
        FakeACPClient.last = self

    def start(self):
        self.calls.append("start")

    def close(self):
        self.calls.append("close")

    def initialize(self, timeout=60):
        return {"protocolVersion": 1, "agentInfo": {"name": "codex-acp"}}

    def new_session(self, timeout=60):
        self.calls.append("new_session")
        return "acp-sid-1"

    def load_session(self, session_id, timeout=60):
        self.calls.append(("load_session", session_id))
        return session_id

    def prompt(self, session_id, text, timeout=600):
        self.calls.append(("prompt", session_id, text))
        self.on_event({"acp_update": "agent_message_chunk", "text": "Hello "})
        self.on_event({"acp_update": "agent_thought_chunk", "text": "(thinking hard)"})
        self.on_event({"acp_update": "tool_call", "tool_kind": "execute", "title": "run pytest"})
        self.permission_result = self.on_permission({"title": "run pytest"}, ALLOW_REJECT)
        self.on_event({"acp_update": "agent_message_chunk", "text": "world"})
        return "end_turn"


class _IO:
    def __init__(self, approve=True):
        self.approve = approve
        self.events = []
        self.asked = []

    def log(self, event_type, **data):
        self.events.append((event_type, data))

    def request_approval(self, tool, arguments):
        self.asked.append((tool, arguments))
        return self.approve


class _Agent:
    def __init__(self, io):
        self.io = io


def _run(**kwargs):
    with patch.object(acp, "ACPClient", FakeACPClient), \
         patch.object(acp, "_base_command", return_value=["fake-codex-acp"]):
        return json.loads(acp.run_codex_acp(**kwargs))


class TestRunCodexAcp:
    def test_new_session_accumulates_message(self):
        agent = _Agent(_IO(approve=True))
        result = _run(prompt="fix", cwd=".", approval="auto", agent=agent)

        assert result["provider"] == "codex"
        assert result["session_id"] == "acp-sid-1"
        assert result["resumed"] is False
        assert result["last_message"] == "Hello world"
        assert result["exit_code"] == 0

    def test_resume_uses_load_session(self):
        agent = _Agent(_IO())
        result = _run(prompt="continue", session_id="prev-sid", approval="auto", agent=agent)

        assert result["resumed"] is True
        assert result["session_id"] == "prev-sid"
        assert ("load_session", "prev-sid") in FakeACPClient.last.calls

    def test_events_forwarded_as_codex_event(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)

        types = [d["codex_type"] for et, d in agent.io.events if et == "codex_event"]
        assert "agent_message_chunk" in types
        assert "tool_call" in types

    def test_thought_chunk_excluded_from_message_but_streamed(self):
        # Reasoning must not leak into last_message, but is still shown live.
        agent = _Agent(_IO())
        result = _run(prompt="fix", approval="auto", agent=agent)

        assert result["last_message"] == "Hello world"        # no "(thinking hard)"
        streamed = [d["codex_type"] for et, d in agent.io.events if et == "codex_event"]
        assert "agent_thought_chunk" in streamed              # but was streamed

    def test_missing_binary_errors(self):
        with patch.object(acp, "_base_command", return_value=None):
            result = json.loads(acp.run_codex_acp("fix"))
        assert "codex-acp not found" in result["error"]


class TestAcpPermission:
    def test_auto_approves(self):
        agent = _Agent(_IO(approve=False))  # io says no, but auto ignores io
        _run(prompt="fix", approval="auto", agent=agent)
        assert FakeACPClient.last.permission_result == "allow-1"
        assert agent.io.asked == []          # auto never asks the human

    def test_manual_approved_via_io(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeACPClient.last.permission_result == "allow-1"
        assert agent.io.asked and agent.io.asked[0][0] == "codex"

    def test_manual_rejected_via_io(self):
        agent = _Agent(_IO(approve=False))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeACPClient.last.permission_result == "reject-1"

    def test_manual_without_io_denies(self):
        result = acp._decide_permission({"title": "x"}, ALLOW_REJECT, "manual", agent=None)
        assert result == "reject-1"

    def test_permission_handler_exception_fails_safe_to_deny(self):
        # If on_permission raises, the client must still answer (deny) so the
        # agent's request isn't left hanging until timeout.
        sent = []

        class _Stdin:
            def write(self, s): sent.append(s)
            def flush(self): pass

        def boom(tool_call, options):
            raise RuntimeError("handler blew up")

        client = acp.ACPClient(command=["x"], on_permission=boom)
        client.proc = type("P", (), {"stdin": _Stdin()})()
        client._handle_server_request(
            7, "session/request_permission",
            {"toolCall": {"title": "rm -rf"}, "options": ALLOW_REJECT},
        )

        reply = json.loads(sent[0])
        assert reply["id"] == 7
        assert reply["result"]["outcome"]["optionId"] == "reject-1"


class TestPickOption:
    def test_option_id_matches_kind(self):
        assert acp._option_id(ALLOW_REJECT, "allow") == "allow-1"
        assert acp._option_id(ALLOW_REJECT, "reject") == "reject-1"

    def test_option_id_falls_back_to_first(self):
        opts = [{"optionId": "only", "kind": "something"}]
        assert acp._option_id(opts, "allow") == "only"


class TestBackendDispatch:
    def test_codex_dispatches_to_acp(self):
        with patch("connectonion.useful_tools.codex_acp.run_codex_acp",
                   return_value='{"ok": true}') as run:
            out = codex("fix", backend="acp", cwd="/repo")
        assert out == '{"ok": true}'
        assert run.call_args.kwargs["cwd"] == "/repo"

    def test_invalid_backend(self):
        result = json.loads(codex("fix", backend="grpc"))
        assert "Invalid backend" in result["error"]


if __name__ == "__main__":
    importlib.reload(acp)
