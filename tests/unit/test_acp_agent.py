"""One ACP client, every ACP engine — proven against a scripted fake agent.

The fake below is a real subprocess speaking real newline-delimited JSON-RPC,
not a mock of our own client class: what these tests pin is the wire behaviour
(initialize → session/new|load → session/prompt, streamed session/update,
the session/request_permission round-trip), which is exactly the part that
would break against a real `claude-agent-acp` or `codex-acp`.
"""

import json
import sys
import textwrap

import pytest

from connectonion.useful_tools.acp_agent import (
    ENGINES,
    _pick_option,
    acp_agent,
    engine_status,
)

# A scripted ACP agent: streams text + a tool call, asks permission, then
# finishes the tool and answers the prompt. Mirrors what codex-acp emits.
FAKE_AGENT = textwrap.dedent("""
    import json, sys

    def send(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()

    def update(u):
        send({"jsonrpc": "2.0", "method": "session/update",
              "params": {"sessionId": "sess-1", "update": u}})

    prompt_id = perm_id = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, msg_id = msg.get("method"), msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": 1, "agentCapabilities": {"loadSession": True}}})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": "sess-1"}})
        elif method == "session/load":
            if msg["params"]["sessionId"] == "sess-known":
                send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            else:
                send({"jsonrpc": "2.0", "id": msg_id,
                      "error": {"code": -32000, "message": "unknown session"}})
        elif method == "session/prompt":
            prompt_id = msg_id
            update({"sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Fixing the tests"}})
            update({"sessionUpdate": "tool_call", "toolCallId": "call-1",
                    "title": "Run pytest", "kind": "execute", "status": "pending"})
            perm_id = 900
            send({"jsonrpc": "2.0", "id": perm_id,
                  "method": "session/request_permission",
                  "params": {"sessionId": "sess-1",
                             "toolCall": {"toolCallId": "call-1", "title": "Run pytest"},
                             "options": [
                                 {"optionId": "ok", "name": "Allow", "kind": "allow_once"},
                                 {"optionId": "no", "name": "Reject", "kind": "reject_once"}]}})
        elif method is None and msg_id == perm_id:
            allowed = msg.get("result", {}).get("outcome", {}).get("optionId") == "ok"
            update({"sessionUpdate": "tool_call_update", "toolCallId": "call-1",
                    "status": "completed" if allowed else "failed"})
            update({"sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": " — done."}})
            send({"jsonrpc": "2.0", "id": prompt_id,
                  "result": {"stopReason": "end_turn"}})
""")


class RecordingIO:
    """The two io methods the tool touches, recording everything."""

    def __init__(self, approve=True):
        self.approve = approve
        self.events = []
        self.approvals = []

    def log(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def request_approval(self, name, details):
        self.approvals.append({"name": name, **details})
        return self.approve


class FakeAgent:
    def __init__(self, io):
        self.io = io
        self.current_session = {}


@pytest.fixture
def fake_engine(tmp_path):
    """An ENGINES entry that launches the scripted agent."""
    script = tmp_path / "fake_acp.py"
    script.write_text(FAKE_AGENT, encoding="utf-8")
    ENGINES["fake"] = {
        "command": [sys.executable, str(script)],
        "requires": sys.executable,
        "auth_hint": str(tmp_path / "absent-credentials.json"),
    }
    yield "fake"
    ENGINES.pop("fake", None)


class TestARunEndToEnd:

    def test_the_envelope_carries_the_result(self, fake_engine):
        out = json.loads(acp_agent("fix tests", engine=fake_engine,
                                   approval="auto"))

        assert out.get("error") is None
        assert out["engine"] == "fake"
        assert out["session_id"] == "sess-1"
        assert out["stop_reason"] == "end_turn"
        assert out["result"] == "Fixing the tests — done."

    def test_inner_steps_stream_as_native_tool_events(self, fake_engine):
        io = RecordingIO()
        acp_agent("fix tests", engine=fake_engine, approval="auto",
                  agent=FakeAgent(io))

        kinds = [e["type"] for e in io.events]
        assert kinds == ["tool_call", "tool_result"], io.events
        call, result = io.events
        assert call["tool_id"] == result["tool_id"] == "call-1"
        assert call["status"] == "in_progress"
        assert result["status"] == "completed"

    def test_resume_of_a_known_session(self, fake_engine):
        out = json.loads(acp_agent("continue", engine=fake_engine,
                                   session_id="sess-known", approval="auto"))

        assert out["resumed"] is True
        assert out["session_id"] == "sess-known"

    def test_resume_of_an_unknown_session_starts_fresh(self, fake_engine):
        out = json.loads(acp_agent("continue", engine=fake_engine,
                                   session_id="sess-gone", approval="auto"))

        assert out["resumed"] is False
        assert out["session_id"] == "sess-1", "fell back to a new session"


class TestApproval:

    def test_manual_routes_through_the_operator_gate(self, fake_engine):
        io = RecordingIO(approve=True)
        out = json.loads(acp_agent("fix", engine=fake_engine,
                                   approval="manual", agent=FakeAgent(io)))

        assert io.approvals == [{"name": "acp_agent", "title": "Run pytest",
                                 "tool_call_id": "call-1"}]
        assert out["stop_reason"] == "end_turn"

    def test_operator_refusal_reaches_the_engine(self, fake_engine):
        io = RecordingIO(approve=False)
        acp_agent("fix", engine=fake_engine, approval="manual",
                  agent=FakeAgent(io))

        assert io.events[-1]["status"] == "failed", (
            "the engine was told 'reject' and marked the tool failed")

    def test_deny_never_asks_and_never_allows(self, fake_engine):
        io = RecordingIO(approve=True)
        acp_agent("fix", engine=fake_engine, approval="deny",
                  agent=FakeAgent(io))

        assert io.approvals == [], "deny must not consult the operator"
        assert io.events[-1]["status"] == "failed"

    def test_a_non_admin_requester_cannot_approve(self, fake_engine):
        io = RecordingIO(approve=True)
        agent = FakeAgent(io)
        agent.current_session = {"requester": {"level": "guest"}}
        acp_agent("fix", engine=fake_engine, approval="manual", agent=agent)

        assert io.approvals == [], "hosted non-admin must fail closed"
        assert io.events[-1]["status"] == "failed"

    def test_malformed_options_grant_nothing(self):
        """None → the client answers `cancelled`, which grants nothing."""
        chosen = _pick_option({"title": "x"}, [{"optionId": "weird"}],
                              "auto", None)
        assert chosen is None, "no allow-kind option means nothing to grant"


class TestFailureShapes:
    """Errors return envelopes; the agent loop never sees an exception."""

    def test_unknown_engine(self):
        out = json.loads(acp_agent("hi", engine="no-such-engine"))
        assert "Unknown engine" in out["error"]

    def test_invalid_approval_mode(self):
        out = json.loads(acp_agent("hi", approval="yolo"))
        assert "Invalid approval" in out["error"]

    def test_a_dying_agent_fails_the_call_not_the_loop(self, tmp_path):
        script = tmp_path / "dies.py"
        script.write_text("import sys; sys.exit(1)", encoding="utf-8")
        ENGINES["dying"] = {"command": [sys.executable, str(script)],
                            "requires": sys.executable,
                            "auth_hint": str(tmp_path / "x")}
        try:
            out = json.loads(acp_agent("hi", engine="dying", timeout=5))
        finally:
            ENGINES.pop("dying", None)

        assert "exited" in out["error"], (
            "EOF must fail pending requests promptly, not wait out the timeout")


class TestEngineStatus:

    def test_reports_every_known_engine(self):
        rows = json.loads(engine_status())["engines"]
        assert {r["engine"] for r in rows} >= {"claude-code", "codex", "gemini"}

    def test_absent_launcher_reads_not_installed(self, fake_engine, tmp_path):
        ENGINES["ghost"] = {"command": ["definitely-not-a-binary-xyz"],
                            "requires": "definitely-not-a-binary-xyz",
                            "auth_hint": str(tmp_path / "x")}
        try:
            rows = {r["engine"]: r for r in json.loads(engine_status())["engines"]}
        finally:
            ENGINES.pop("ghost", None)

        assert rows["ghost"]["installed"] is False
        assert rows["ghost"]["authenticated"] is False
