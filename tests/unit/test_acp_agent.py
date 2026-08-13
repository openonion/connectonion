"""Typed ACP client tool tests against a real stdio subprocess."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
import textwrap
import threading
import time
from types import SimpleNamespace

import pytest
from acp.schema import (
    AgentMessageChunk,
    PermissionOption,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)

from connectonion.useful_tools import _acp_agent_client as acp_client
from connectonion.useful_tools._acp_agent_client import (
    ToolClient,
    engine_environment,
    required_mode,
    session_metadata,
)
from connectonion.useful_tools.acp_agent import ENGINES, ACPAgent, acp_agent, engine_status

acp_agent_module = importlib.import_module("connectonion.useful_tools.acp_agent")

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
                update({"sessionUpdate": "tool_call", "toolCallId": "old-call",
                        "title": "Old tool", "kind": "execute",
                        "status": "pending"})
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
            if text == "shadow update":
                send({"jsonrpc": "2.0", "method": "session/update",
                      "params": {
                          "sessionId": "visible-wrong-session",
                          "update": {"sessionUpdate": "agent_message_chunk",
                                     "messageId": "answer-1",
                                     "content": {"type": "text",
                                                 "text": "SHADOWED"}},
                          "_meta": {"session_id": active_session}}})
            update({"sessionUpdate": "tool_call", "toolCallId": "call-1",
                    "title": "Run pytest", "kind": "execute",
                    "status": "pending", "rawInput": {"command": "pytest"}})
            permission_id = 900
            permission_params = {
                "sessionId": "sess-1",
                "toolCall": {"toolCallId": "call-1", "title": "Run pytest"},
                "options": [
                    {"optionId": "ok", "name": "Allow", "kind": "allow_once"},
                    {"optionId": "no", "name": "Reject", "kind": "reject_once"}],
            }
            if text == "shadow permission":
                permission_params["sessionId"] = "visible-wrong-session"
                permission_params["_meta"] = {"session_id": active_session}
            send({"jsonrpc": "2.0", "id": permission_id,
                  "method": "session/request_permission",
                  "params": permission_params})
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
        self.revoked = threading.Event()

    def log(self, event_type: str, **fields) -> None:
        self.events.append({"type": event_type, **fields})

    def request_approval(self, name: str, details: dict) -> bool:
        self.approvals.append({"name": name, **details})
        return self.approve

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancel(self) -> None:
        self.revoked.set()


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
    def test_real_acp_claude_uses_macos_keychain_context(self):
        from tests.e2e.real_api.test_real_acp_agent import (
            _real_claude_auth_environment,
        )

        assert _real_claude_auth_environment("darwin", "/operator", None) == {
            "HOME": "/operator"
        }

    @pytest.mark.parametrize("platform", ["linux", "win32"])
    def test_real_acp_claude_uses_file_auth_off_macos(self, platform):
        from tests.e2e.real_api.test_real_acp_agent import (
            _real_claude_auth_environment,
        )

        assert _real_claude_auth_environment(platform, "/operator", None) == {
            "CLAUDE_CONFIG_DIR": "/operator/.claude"
        }

    def test_real_acp_claude_explicit_config_wins(self):
        from tests.e2e.real_api.test_real_acp_agent import (
            _real_claude_auth_environment,
        )

        assert _real_claude_auth_environment(
            "darwin", "/operator", "/accounts/work"
        ) == {"CLAUDE_CONFIG_DIR": "/accounts/work"}

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

    def test_gemini_cli_is_an_exact_version_pin_on_the_current_acp_flag(self):
        assert ENGINES["gemini"].command == (
            "npx",
            "--yes",
            "@google/gemini-cli@0.55.1",
            "--acp",
        )

    def test_custom_command_and_approval_are_operator_owned(self, fake_command):
        configured = ACPAgent(command=fake_command, name="private", approval="deny")
        parameters = inspect.signature(configured.acp_agent).parameters
        assert "command" not in parameters
        assert "approval" not in parameters
        assert "workspace" not in parameters

    def test_codex_auto_uses_the_adapter_workspace_mode(self):
        automatic = engine_environment("codex", "auto")
        assert automatic["INITIAL_AGENT_MODE"] == "agent"
        assert json.loads(automatic["CODEX_CONFIG"])["approvals_reviewer"] == "user"

    def test_codex_explicit_api_key_is_the_only_secret_forwarded(
        self, monkeypatch
    ):
        monkeypatch.setenv("CODEX_API_KEY", "codex-test-key")
        monkeypatch.setenv("UNRELATED_SECRET", "must-not-cross")

        environment = engine_environment("codex", "auto")

        assert environment["CODEX_API_KEY"] == "codex-test-key"
        assert "UNRELATED_SECRET" not in environment
        assert json.loads(environment["DEFAULT_AUTH_REQUEST"]) == {
            "methodId": "api-key"
        }

    def test_codex_explicit_home_is_forwarded_without_starting_auth(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        codex_home = tmp_path / "codex"
        monkeypatch.setenv("CODEX_HOME", str(codex_home))

        environment = engine_environment("codex", "auto")

        assert environment["CODEX_HOME"] == str(codex_home)
        assert "DEFAULT_AUTH_REQUEST" not in environment

    def test_codex_missing_credentials_do_not_start_an_auth_flow(
        self, monkeypatch
    ):
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CODEX_HOME", raising=False)

        assert "DEFAULT_AUTH_REQUEST" not in engine_environment("codex", "auto")

    def test_claude_explicit_auth_environment_is_narrowly_forwarded(
        self, monkeypatch, tmp_path
    ):
        config_dir = tmp_path / "claude"
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
        monkeypatch.setenv("UNRELATED_SECRET", "must-not-cross")

        assert engine_environment("claude-code", "manual") == {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "ANTHROPIC_API_KEY": "anthropic-test-key",
        }

    def test_gemini_explicit_auth_environment_is_narrowly_forwarded(
        self, monkeypatch, tmp_path
    ):
        credentials = tmp_path / "vertex-service-account.json"
        selected = {
            "GEMINI_API_KEY": "gemini-test-key",
            "GOOGLE_API_KEY": "vertex-test-key",
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_PROJECT_ID": "test-project-alias",
            "GOOGLE_CLOUD_LOCATION": "australia-southeast1",
            "GOOGLE_APPLICATION_CREDENTIALS": str(credentials),
        }
        for name, value in selected.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setenv("UNRELATED_SECRET", "must-not-cross")

        assert engine_environment("gemini", "manual") == {
            "NO_BROWSER": "1",
            **selected,
        }

    def test_public_tool_binds_the_agents_call_time_workspace(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        class FakeACPAgent:
            def __init__(self, *, workspace):
                captured["workspace"] = workspace

            def acp_agent(self, **kwargs):
                captured.update(kwargs)
                return "captured"

        monkeypatch.setattr(acp_agent_module, "ACPAgent", FakeACPAgent)
        agent = SimpleNamespace(_delegation_workspace=tmp_path)

        result = acp_agent_module.acp_agent(
            "inspect", engine="not-an-engine", agent=agent
        )

        assert result == "captured"
        assert captured["workspace"] == tmp_path
        assert captured["agent"] is agent

    def test_public_tool_without_an_agent_uses_the_call_time_cwd(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        class FakeACPAgent:
            def __init__(self, *, workspace):
                captured["workspace"] = workspace

            def acp_agent(self, **_kwargs):
                return "captured"

        monkeypatch.setattr(acp_agent_module, "ACPAgent", FakeACPAgent)
        monkeypatch.chdir(tmp_path)

        assert acp_agent_module.acp_agent(
            "inspect", engine="not-an-engine"
        ) == "captured"
        assert captured["workspace"] == tmp_path

    @pytest.mark.parametrize("approval", ["manual", "deny"])
    def test_codex_modes_the_adapter_cannot_enforce_fail_before_spawn(
        self, monkeypatch, tmp_path, approval
    ):
        spawned = False

        async def forbidden_spawn(*_args, **_kwargs):
            nonlocal spawned
            spawned = True
            raise AssertionError("unsupported Codex policy reached the launcher")

        monkeypatch.setattr(acp_agent_module, "run_agent", forbidden_spawn)
        output = json.loads(
            ACPAgent(approval=approval, workspace=tmp_path).acp_agent(
                "inspect", engine="codex"
            )
        )

        assert spawned is False
        assert "supports only operator-selected 'auto'" in output["error"]
        assert "native codex tool" in output["error"]

    def test_named_gemini_resume_fails_before_spawn(self, monkeypatch, tmp_path):
        spawned = False

        async def forbidden_spawn(*_args, **_kwargs):
            nonlocal spawned
            spawned = True
            raise AssertionError("unsupported Gemini resume reached the launcher")

        monkeypatch.setattr(acp_agent_module, "run_agent", forbidden_spawn)
        output = json.loads(
            ACPAgent(approval="manual", workspace=tmp_path).acp_agent(
                "continue", engine="gemini", session_id="ephemeral-session"
            )
        )

        assert spawned is False
        assert output["session_id"] == "ephemeral-session"
        assert "does not persist ACP sessions across child processes" in output["error"]
        assert "without session_id" in output["error"]

    def test_named_gemini_does_not_return_an_unusable_session_id(
        self, monkeypatch, tmp_path
    ):
        async def fake_run_agent(*_args, **_kwargs):
            return {
                "session_id": "child-process-only",
                "resumed": False,
                "stop_reason": "end_turn",
                "result": "GEMINI_OK",
            }

        monkeypatch.setattr(acp_agent_module, "run_agent", fake_run_agent)
        monkeypatch.setattr(acp_agent_module.shutil, "which", lambda _name: "/npx")

        output = json.loads(
            ACPAgent(approval="manual", workspace=tmp_path).acp_agent(
                "hi", engine="gemini"
            )
        )

        assert output == {
            "engine": "gemini",
            "session_id": "",
            "resumed": False,
            "stop_reason": "end_turn",
            "result": "GEMINI_OK",
        }

    def test_named_engines_enforce_permission_modes(self):
        assert required_mode("codex", "manual") == "read-only"
        assert required_mode("codex", "deny") == "read-only"
        assert required_mode("codex", "auto") == "agent"
        assert required_mode("claude-code", "manual") == "default"
        assert required_mode("claude-code", "deny") == "dontAsk"
        assert required_mode("gemini", "manual") == "default"
        assert required_mode("gemini", "deny") == "plan"
        assert required_mode("gemini", "auto") == "yolo"
        assert required_mode("custom", "manual") is None

    def test_claude_does_not_inherit_interactive_cli_allow_rules(self):
        assert session_metadata("claude-code") == {
            "claudeCode": {"options": {"settingSources": []}}
        }
        assert session_metadata("codex") == {}


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
            "tool_call", "tool_result"
        ]
        call, result = io.events
        assert call["tool_id"] == result["tool_id"] == "call-1"
        assert call["args"] == {}
        assert result["status"] == "completed"
        assert result["result"] == "Run pytest"

    def test_known_session_resumes(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent(
            "continue", session_id="sess-known"
        ))
        assert output["resumed"] is True
        assert output["session_id"] == "sess-known"
        assert output["result"] == "Fixing the tests — done."

    def test_child_meta_cannot_shadow_visible_update_session(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent("shadow update"))

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

    @pytest.mark.asyncio
    async def test_rpc_boundary_waits_for_scheduled_history_callbacks(self):
        client = ToolClient(None, "deny")
        client.observe_stream(SimpleNamespace(
            direction=SimpleNamespace(value="incoming"),
            message={"method": "session/update"},
        ))
        deadline = asyncio.get_running_loop().time() + 1
        barrier = asyncio.create_task(client.drain_updates(deadline, 1))
        await asyncio.sleep(0)
        assert not barrier.done()

        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text="OLD"),
            ),
        )
        await barrier
        client.begin_prompt()
        assert client.message_text() == ""


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
            "input_preview": "null",
        }]

    def test_child_meta_cannot_shadow_visible_permission_session(
        self, fake_command
    ):
        io = RecordingIO(approve=True)
        runner(fake_command, approval="manual").acp_agent(
            "shadow permission", agent=FakeAgent(io)
        )

        assert io.approvals == []
        result = next(event for event in io.events if event["type"] == "tool_result")
        assert result["status"] == "failed"

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

    def test_manual_gate_is_revoked_when_total_timeout_expires(self, fake_command):
        class BlockingIO(RecordingIO):
            def request_approval(self, name: str, details: dict) -> bool:
                self.approvals.append({"name": name, **details})
                self.revoked.wait(timeout=5)
                return True

        io = BlockingIO()
        started = time.monotonic()
        output = json.loads(runner(fake_command, approval="manual").acp_agent(
            "fix", timeout=1, agent=FakeAgent(io)
        ))
        assert "timed out" in output["error"]
        assert io.revoked.is_set()
        assert time.monotonic() - started < 3

    @pytest.mark.asyncio
    async def test_manual_never_persists_an_allow_always_choice(self):
        io = RecordingIO()
        client = ToolClient(FakeAgent(io), "manual")
        client.begin_prompt()
        response = await client.request_permission(
            "sess",
            ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id="call-1",
                title="Write",
            ),
            [
                PermissionOption(
                    option_id="forever", name="Always", kind="allow_always"
                ),
                PermissionOption(option_id="no", name="No", kind="reject_once"),
            ],
        )
        assert response.outcome.outcome == "cancelled"
        assert io.approvals == []


class TestDisclosureBounds:
    @pytest.mark.asyncio
    async def test_result_keeps_only_the_final_agent_message(self):
        client = ToolClient(None, "deny")
        client.begin_prompt()
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                message_id="startup-notice",
                content=TextContentBlock(
                    type="text", text="Skill descriptions were shortened.\n\n"
                ),
            ),
        )
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                message_id="final-answer",
                content=TextContentBlock(type="text", text="ACP_CODEX_OK"),
            ),
        )

        assert client.message_text() == "ACP_CODEX_OK"

    def test_error_envelope_is_bounded(self):
        output = json.loads(
            acp_client.envelope("custom", error="x" * 100_000)
        )
        assert len(output["error"].encode("utf-8")) <= 4 * 1024

    @pytest.mark.asyncio
    async def test_result_is_bounded_without_splitting_utf8(self):
        client = ToolClient(None, "deny")
        client.begin_prompt()
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(type="text", text="海" * 30_000),
            ),
        )
        result = client.message_text()
        assert result.endswith("... (ACP result truncated at 64 KiB)")
        assert len(result.encode("utf-8")) <= 64 * 1024

    @pytest.mark.asyncio
    async def test_oversized_message_ids_are_not_retained(self):
        client = ToolClient(None, "deny")
        client.begin_prompt()
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                message_id="x" * 10_000,
                content=TextContentBlock(type="text", text="answer"),
            ),
        )

        assert client._message_id.startswith("acp-")
        assert len(client._message_id) == 68

    @pytest.mark.asyncio
    async def test_new_message_ids_do_not_reset_the_turn_chunk_limit(self):
        client = ToolClient(None, "deny")
        client.begin_prompt()
        client._message_chunks = acp_client._MESSAGE_CHUNK_LIMIT - 1
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                message_id="notice",
                content=TextContentBlock(type="text", text="notice"),
            ),
        )
        await client.session_update(
            "sess",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                message_id="answer",
                content=TextContentBlock(type="text", text="final"),
            ),
        )

        assert "final" not in client.message_text()
        assert client.message_text().endswith(
            "... (ACP result truncated at 64 KiB)"
        )

    @pytest.mark.asyncio
    async def test_oversized_tool_ids_are_not_retained_as_internal_keys(self):
        io = RecordingIO()
        client = ToolClient(FakeAgent(io), "deny")
        client.begin_prompt()
        oversized_id = "x" * 10_000
        await client.session_update(
            "sess",
            ToolCallStart(
                session_update="tool_call",
                tool_call_id=oversized_id,
                title="Read",
                status="pending",
            ),
        )

        stored_id = next(iter(client._tool_titles))
        assert stored_id.startswith("acp-")
        assert len(stored_id) == 68
        assert io.events[0]["tool_id"] == stored_id

    @pytest.mark.asyncio
    async def test_tool_events_hide_raw_inputs_and_outputs(self):
        io = RecordingIO()
        client = ToolClient(FakeAgent(io), "deny")
        client.begin_prompt()
        await client.session_update(
            "sess",
            ToolCallStart(
                session_update="tool_call",
                tool_call_id="call-secret",
                title="Read config",
                status="pending",
                raw_input={"token": "secret"},
            ),
        )
        await client.session_update(
            "sess",
            ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id="call-secret",
                status="completed",
                raw_output={"token": "secret"},
            ),
        )
        assert io.events == [
            {"type": "tool_call", "tool_id": "call-secret", "name": "Read config", "args": {}, "status": "in_progress"},
            {"type": "tool_result", "tool_id": "call-secret", "status": "completed", "result": "Read config"},
        ]

    @pytest.mark.asyncio
    async def test_progress_delivery_failure_does_not_break_protocol_callback(self):
        class BrokenIO(RecordingIO):
            def log(self, event_type: str, **fields) -> None:
                raise RuntimeError("browser disconnected")

        client = ToolClient(FakeAgent(BrokenIO()), "deny")
        client.begin_prompt()
        await client.session_update(
            "sess",
            ToolCallStart(
                session_update="tool_call",
                tool_call_id="call-1",
                title="Read",
                status="pending",
            ),
        )
        await client.session_update(
            "sess",
            ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id="call-1",
                status="completed",
            ),
        )
        assert client._events_disabled is True


class TestFailures:
    def test_gemini_auth_startup_fails_fast_without_opening_login(
        self, monkeypatch, tmp_path
    ):
        script = tmp_path / "gemini_auth_hang.py"
        script.write_text(
            "import sys, time\n"
            "sys.stderr.write('Authentication required\\n')\n"
            "sys.stderr.flush()\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(acp_client, "_STARTUP_LIMIT", 0.1)
        started = time.monotonic()

        output = json.loads(
            ACPAgent(
                command=[sys.executable, str(script)],
                name="gemini",
                approval="manual",
                workspace=tmp_path,
            ).acp_agent("hi", engine="gemini", timeout=10)
        )

        assert "Authentication required" in output["error"]
        assert time.monotonic() - started < 4

    def test_gemini_auth_session_start_uses_the_same_bounded_gate(
        self, monkeypatch, tmp_path
    ):
        script = tmp_path / "gemini_session_auth_hang.py"
        script.write_text(
            textwrap.dedent(
                """
                import json
                import sys
                import time

                for line in sys.stdin:
                    message = json.loads(line)
                    if message.get("method") == "initialize":
                        sys.stdout.write(json.dumps({
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "result": {
                                "protocolVersion": 1,
                                "agentCapabilities": {"loadSession": True},
                            },
                        }) + "\\n")
                        sys.stdout.flush()
                    elif message.get("method") == "session/new":
                        sys.stderr.write("Authentication required\\n")
                        sys.stderr.flush()
                        time.sleep(60)
                """
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(acp_client, "_STARTUP_LIMIT", 0.1)
        started = time.monotonic()

        output = json.loads(
            ACPAgent(
                command=[sys.executable, str(script)],
                name="gemini",
                approval="manual",
                workspace=tmp_path,
            ).acp_agent("hi", engine="gemini", timeout=10)
        )

        assert "Authentication required" in output["error"]
        assert time.monotonic() - started < 4

    def test_unknown_engine(self):
        output = json.loads(acp_agent("hi", engine="not-an-engine"))
        assert "Unknown engine" in output["error"]

    @pytest.mark.parametrize("value", [0, -1, True, 1.5])
    def test_timeout_must_be_a_positive_integer(self, fake_command, value):
        output = json.loads(runner(fake_command).acp_agent("hi", timeout=value))
        assert "positive integer" in output["error"]

    def test_timeout_has_an_operator_bounded_maximum(self, fake_command):
        output = json.loads(runner(fake_command).acp_agent("hi", timeout=3601))
        assert "must not exceed 3600" in output["error"]

    @pytest.mark.parametrize("engine", [[], "x" * 65])
    def test_engine_must_be_a_bounded_string(self, engine):
        output = json.loads(acp_agent("hi", engine=engine))
        assert "Engine" in output["error"]

    def test_prompt_and_session_id_are_bounded(self, fake_command):
        prompt = json.loads(runner(fake_command).acp_agent("x" * (1024 * 1024 + 1)))
        session = json.loads(runner(fake_command).acp_agent("hi", session_id="s" * 513))
        assert "1 MiB" in prompt["error"]
        assert "Session ID is too long" in session["error"]

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
        output = json.loads(ACPAgent(
            command=fake_command, name="fake", workspace=tmp_path
        ).acp_agent(
            "hi", cwd=str(tmp_path / "missing")
        ))
        assert "Working directory" in output["error"]

    def test_model_cannot_leave_operator_workspace(self, fake_command, tmp_path):
        workspace = tmp_path / "workspace"
        outside = tmp_path / "outside"
        workspace.mkdir()
        outside.mkdir()
        output = json.loads(ACPAgent(
            command=fake_command, name="fake", workspace=workspace
        ).acp_agent("hi", cwd=str(outside)))
        assert "must stay inside workspace" in output["error"]

    def test_relative_cwd_is_resolved_from_operator_workspace(
        self, fake_command, tmp_path
    ):
        child = tmp_path / "child"
        child.mkdir()
        output = json.loads(ACPAgent(
            command=fake_command, name="fake", workspace=tmp_path
        ).acp_agent("hi", cwd="child"))
        assert output.get("error") is None


class TestEngineStatus:
    def test_reports_pins_and_honest_readiness_fields(self):
        rows = {row["engine"]: row for row in json.loads(engine_status())["engines"]}
        assert set(rows) >= {"claude-code", "codex", "gemini"}
        assert rows["claude-code"]["adapter_version"] == "0.66.0"
        assert rows["codex"]["adapter_version"] == "1.1.14"
        assert rows["gemini"]["adapter_version"] == "0.55.1"
        assert rows["claude-code"]["supports_resume"] is True
        assert rows["codex"]["supports_resume"] is True
        assert rows["gemini"]["supports_resume"] is False
        assert rows["codex"]["supported_approval_modes"] == ["auto"]
        assert rows["claude-code"]["supported_approval_modes"] == [
            "manual", "auto", "deny"
        ]
        assert "launcher_available" in rows["gemini"]
        assert rows["gemini"]["credential_file_present"] is False
        assert rows["gemini"]["supported_auth"] == [
            "Gemini API key", "Vertex AI", "enterprise Code Assist"
        ]
        assert "authenticated_hint" not in rows["gemini"]
