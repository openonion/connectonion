"""Typed ACP client tool tests against a real stdio subprocess."""

from __future__ import annotations

import inspect
import json
import sys
import textwrap

import pytest

from connectonion.useful_tools.acp_agent import (
    ACPAgent,
    ENGINES,
    _engine_environment,
    acp_agent,
    engine_status,
)


FAKE_AGENT = textwrap.dedent(
    """
    import json
    import sys

    def send(message):
        sys.stdout.write(json.dumps(message) + "\\n")
        sys.stdout.flush()

    active_session = "sess-1"

    def update(value):
        send({"jsonrpc": "2.0", "method": "session/update",
              "params": {"sessionId": active_session, "update": value}})

    prompt_id = permission_id = None
    for line in sys.stdin:
        message = json.loads(line)
        method, message_id = message.get("method"), message.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": message_id, "result": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "agentInfo": {"name": "fixture", "version": "1"}}})
        elif method == "session/new":
            active_session = "sess-1"
            send({"jsonrpc": "2.0", "id": message_id,
                  "result": {"sessionId": "sess-1"}})
        elif method == "session/load":
            if message["params"]["sessionId"] == "sess-known":
                active_session = "sess-known"
                update({"sessionUpdate": "agent_message_chunk",
                        "messageId": "old-answer",
                        "content": {"type": "text", "text": "OLD"}})
                send({"jsonrpc": "2.0", "id": message_id, "result": {}})
            else:
                send({"jsonrpc": "2.0", "id": message_id,
                      "error": {"code": -32002, "message": "unknown session"}})
        elif method == "session/prompt":
            text = message["params"]["prompt"][0]["text"]
            if text == "hang":
                continue
            prompt_id = message_id
            update({"sessionUpdate": "agent_thought_chunk",
                    "messageId": "thought-1",
                    "content": {"type": "text", "text": "Checking"}})
            update({"sessionUpdate": "plan", "entries": [{
                "content": "Run the tests", "priority": "high",
                "status": "in_progress"}]})
            update({"sessionUpdate": "agent_message_chunk",
                    "messageId": "answer-1",
                    "content": {"type": "text", "text": "Fixing the tests"}})
            update({"sessionUpdate": "tool_call", "toolCallId": "call-1",
                    "title": "Run pytest", "kind": "execute",
                    "status": "pending", "rawInput": {"command": "pytest"}})
            permission_id = 900
            send({"jsonrpc": "2.0", "id": permission_id,
                  "method": "session/request_permission",
                  "params": {"sessionId": "sess-1",
                             "toolCall": {"toolCallId": "call-1",
                                          "title": "Run pytest"},
                             "options": [
                                 {"optionId": "ok", "name": "Allow",
                                  "kind": "allow_once"},
                                 {"optionId": "no", "name": "Reject",
                                  "kind": "reject_once"}]}})
        elif method is None and message_id == permission_id:
            allowed = (message.get("result", {}).get("outcome", {})
                       .get("optionId") == "ok")
            update({"sessionUpdate": "tool_call_update",
                    "toolCallId": "call-1",
                    "status": "completed" if allowed else "failed",
                    "rawOutput": {"allowed": allowed}})
            update({"sessionUpdate": "agent_message_chunk",
                    "messageId": "answer-1",
                    "content": {"type": "text", "text": " — done."}})
            send({"jsonrpc": "2.0", "id": prompt_id,
                  "result": {"stopReason": "end_turn"}})
    """
)


class RecordingIO:
    def __init__(self, approve: bool = True, cancelled: bool = False) -> None:
        self.approve = approve
        self.cancelled = cancelled
        self.events: list[dict] = []
        self.approvals: list[dict] = []

    def log(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})

    def request_approval(self, name: str, details: dict) -> bool:
        self.approvals.append({"name": name, **details})
        return self.approve

    def is_cancelled(self) -> bool:
        return self.cancelled


class FakeAgent:
    def __init__(self, io: RecordingIO) -> None:
        self.io = io
        self.current_session: dict = {}


@pytest.fixture
def fake_command(tmp_path):
    script = tmp_path / "fake_acp.py"
    script.write_text(FAKE_AGENT, encoding="utf-8")
    return [sys.executable, str(script)]


def runner(fake_command, *, approval="auto") -> ACPAgent:
    return ACPAgent(command=fake_command, name="fake", approval=approval)


class TestPublicBoundary:
    def test_model_can_pick_only_a_named_engine(self):
        parameters = inspect.signature(acp_agent).parameters
        assert "engine" in parameters
        assert "command" not in parameters
        assert "approval" not in parameters

    def test_node_adapters_are_exact_version_pins(self):
        claude = " ".join(ENGINES["claude-code"].command)
        codex = " ".join(ENGINES["codex"].command)
        assert "@agentclientprotocol/claude-agent-acp@0.66.0" in claude
        assert "@agentclientprotocol/codex-acp@1.1.14" in codex

    def test_custom_command_and_approval_are_operator_owned(self, fake_command):
        configured = ACPAgent(command=fake_command, name="private", approval="deny")
        parameters = inspect.signature(configured.acp_agent).parameters
        assert "command" not in parameters
        assert "approval" not in parameters

    def test_codex_manual_and_deny_start_below_workspace_write_authority(self):
        manual = _engine_environment("codex", "manual")
        deny = _engine_environment("codex", "deny")
        automatic = _engine_environment("codex", "auto")
        assert manual["INITIAL_AGENT_MODE"] == deny["INITIAL_AGENT_MODE"] == "read-only"
        assert automatic["INITIAL_AGENT_MODE"] == "agent"
        assert json.loads(manual["CODEX_CONFIG"])["approvals_reviewer"] == "user"


class TestTypedRun:
    def test_envelope_carries_result_and_session(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent("fix tests"))

        assert output.get("error") is None
        assert output == {
            "engine": "fake",
            "session_id": "sess-1",
            "resumed": False,
            "stop_reason": "end_turn",
            "result": "Fixing the tests — done.",
        }

    def test_typed_updates_cross_the_native_event_waist(self, fake_command):
        io = RecordingIO()
        runner(fake_command).acp_agent("fix", agent=FakeAgent(io))

        assert [event["type"] for event in io.events] == [
            "thinking", "plan", "tool_call", "tool_result", "thinking"
        ]
        thought, plan, call, result, finished_thought = io.events
        assert thought["id"] == finished_thought["id"] == "thought-1"
        assert thought["status"] == "running"
        assert finished_thought["status"] == "done"
        assert thought["content"] == finished_thought["content"] == "Checking"
        assert plan["entries"] == [{
            "content": "Run the tests", "priority": "high",
            "status": "in_progress",
        }]
        assert call["tool_id"] == result["tool_id"] == "call-1"
        assert call["args"] == {"command": "pytest"}
        assert result["status"] == "completed"
        assert result["result"] == {"allowed": True}

    def test_known_session_resumes(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent(
            "continue", session_id="sess-known"
        ))
        assert output["resumed"] is True
        assert output["session_id"] == "sess-known"
        assert output["result"] == "Fixing the tests — done."

    def test_failed_resume_does_not_silently_start_another_session(
        self, fake_command
    ):
        output = json.loads(runner(fake_command).acp_agent(
            "continue", session_id="sess-missing"
        ))
        assert output["session_id"] == "sess-missing"
        assert output["resumed"] is False
        assert "unknown session" in output["error"]


class TestPermissionBoundary:
    def test_manual_routes_through_operator_gate(self, fake_command):
        io = RecordingIO(approve=True)
        output = json.loads(runner(fake_command, approval="manual").acp_agent(
            "fix", agent=FakeAgent(io)
        ))

        assert output.get("error") is None
        assert io.approvals == [{
            "name": "acp_agent",
            "title": "Run pytest",
            "tool_call_id": "call-1",
        }]

    def test_operator_refusal_reaches_engine(self, fake_command):
        io = RecordingIO(approve=False)
        runner(fake_command, approval="manual").acp_agent(
            "fix", agent=FakeAgent(io)
        )
        result = next(event for event in io.events if event["type"] == "tool_result")
        assert result["status"] == "failed"

    def test_deny_never_asks_or_allows(self, fake_command):
        io = RecordingIO(approve=True)
        runner(fake_command, approval="deny").acp_agent(
            "fix", agent=FakeAgent(io)
        )
        assert io.approvals == []
        result = next(event for event in io.events if event["type"] == "tool_result")
        assert result["status"] == "failed"

    def test_non_admin_cannot_answer_manual_permission(self, fake_command):
        io = RecordingIO(approve=True)
        agent = FakeAgent(io)
        agent.current_session = {"requester": {"level": "guest"}}
        runner(fake_command, approval="manual").acp_agent("fix", agent=agent)
        assert io.approvals == []
        result = next(event for event in io.events if event["type"] == "tool_result")
        assert result["status"] == "failed"


class TestFailures:
    def test_unknown_engine(self):
        output = json.loads(acp_agent("hi", engine="not-an-engine"))
        assert "Unknown engine" in output["error"]

    @pytest.mark.parametrize("value", [0, -1, True, 1.5])
    def test_timeout_must_be_a_positive_integer(self, fake_command, value):
        output = json.loads(runner(fake_command).acp_agent("hi", timeout=value))
        assert "positive integer" in output["error"]

    def test_timeout_is_one_end_to_end_budget(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent("hang", timeout=1))
        assert "timed out" in output["error"]

    def test_cancelled_lease_stops_before_prompt_work(self, fake_command):
        io = RecordingIO(cancelled=True)
        output = json.loads(runner(fake_command).acp_agent(
            "hang", timeout=10, agent=FakeAgent(io)
        ))
        assert "interrupted" in output["error"]

    def test_working_directory_must_exist(self, fake_command, tmp_path):
        output = json.loads(runner(fake_command).acp_agent(
            "hi", cwd=str(tmp_path / "missing")
        ))
        assert "Working directory" in output["error"]


class TestEngineStatus:
    def test_reports_pins_and_honest_readiness_fields(self):
        rows = {row["engine"]: row for row in json.loads(engine_status())["engines"]}
        assert set(rows) >= {"claude-code", "codex", "gemini"}
        assert rows["claude-code"]["adapter_version"] == "0.66.0"
        assert rows["codex"]["adapter_version"] == "1.1.14"
        assert "launcher_available" in rows["gemini"]
        assert "authenticated_hint" in rows["gemini"]
